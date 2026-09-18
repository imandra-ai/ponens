#!/usr/bin/env python3
"""Every shipped trace declares the spec this release publishes.

A demo is the first thing a reader sees, and a stale one shows the tool failing rather than working.
`stripe_v1_1.json` sat at spec 1.8 while the spec was 1.13; it still VALIDATED - the format is
backward-compatible by design, which is exactly why nothing caught it - but every result came back
`grade: unranked` from `ponens trace symbols`, because grading reads an attribution block that 1.8
did not have. The demo page advertised an unranked record.

Validity was already checked. This checks CURRENCY, which is a different question:

  1. every trace under the scanned roots declares `spec_version` == the published spec, and
  2. the manifest's `spec` field for each sample agrees with that file's own `spec_version`
     (they had drifted: the manifest said 1.7 where the file said 1.8).

The published spec is read from the newest `spec/TRACE_SPEC_v*.md`, so a release that ships a new
spec and forgets the demos fails here rather than on someone's screen.

    python3 cli/tools/check_demo_spec.py [roots...]
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_ROOTS = ["examples", "cli/ponens/demos"]


def published_spec() -> str:
    """The newest `spec/TRACE_SPEC_v<major>_<minor>.md`, as `major.minor`."""
    vs = []
    for p in (ROOT / "spec").glob("TRACE_SPEC_v*.md"):
        m = re.match(r"TRACE_SPEC_v(\d+)_(\d+)\.md$", p.name)
        if m:
            vs.append((int(m.group(1)), int(m.group(2))))
    if not vs:
        raise SystemExit("no spec/TRACE_SPEC_v*.md found - cannot say what the published spec is")
    a, b = max(vs)
    return f"{a}.{b}"


def main(argv: list[str]) -> int:
    want = published_spec()
    roots = argv[1:] or DEFAULT_ROOTS
    bad: list[str] = []
    seen = 0

    for root in roots:
        base = ROOT / root
        if not base.exists():
            bad.append(f"{root}: no such directory - a check that scans nothing passes vacuously")
            continue
        for p in sorted(base.rglob("*.json")):
            if p.name == "manifest.json":
                continue
            try:
                trace = json.loads(p.read_text())
            except Exception as e:                      # noqa: BLE001 - report, never crash the run
                bad.append(f"{p.relative_to(ROOT)}: unreadable ({e})")
                continue
            if not isinstance(trace, dict) or "artifacts" not in trace:
                continue                                # not a trace; fixtures live here too
            seen += 1
            got = str(trace.get("spec_version") or "-")
            if got != want:
                bad.append(f"{p.relative_to(ROOT)}: spec_version {got}, published spec is {want}")

        # The manifest's own claim about each sample has to match the file it names.
        mf = base / "manifest.json"
        if mf.exists():
            m = json.loads(mf.read_text())
            for s in m.get("samples") or []:
                f = base / s["file"]
                if not f.exists():
                    bad.append(f"{mf.relative_to(ROOT)}: names a missing file {s['file']}")
                    continue
                actual = str(json.loads(f.read_text()).get("spec_version") or "-")
                claimed = str(s.get("spec") or "-")
                if claimed != "-" and claimed != actual:
                    bad.append(f"{mf.relative_to(ROOT)}: says {s['file']} is spec {claimed}, "
                               f"the file says {actual}")

    if not seen:
        print(f"no traces found under {roots} - refusing to pass vacuously")
        return 1
    for b in bad:
        print(f"  {b}")
    print(f"{'FAIL' if bad else 'OK'} - {seen} trace(s) checked against published spec {want}"
          + (f", {len(bad)} problem(s)" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

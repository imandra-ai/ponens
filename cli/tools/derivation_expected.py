#!/usr/bin/env python3
"""Generate the expected derivation for each fixture - the one answer three implementations must give.

The rule that decides whether a gap is open lives in three places now: `lineage.apply_resolutions`
(Python, what `ponens trace check` uses), `_applyResolutions` in the viewer (JavaScript), and
`residualsOf` in the agent (TypeScript). They were kept in step by writing the same code carefully
three times, which is not a mechanism. A viewer that shows a gap as open while `check` passes it - or
the reverse - is worse than either alone, because the disagreement is invisible to both.

Python is the reference; this writes what it derives, and the JS and TS suites assert the same.

    python3 cli/tools/derivation_expected.py [--check]
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli"))

from ponens import lineage  # noqa: E402

FIXTURES = ROOT / "cli/tests/fixtures/derivation"
EXPECTED = FIXTURES / "expected.json"

# The fields a consumer actually acts on. Comparing whole surfaces would make the check fail on
# incidental shape (which key order, which optional field a producer happened to include); these are
# the ones a disagreement would actually mislead someone about.
KEYS = ("residual_id", "status", "declared_status", "resolution_contested_by")


def derive(trace: dict) -> list[dict]:
    out = []
    for r in lineage.residual_surface(trace):
        row = {k: r.get(k) for k in KEYS if r.get(k) is not None}
        hist = r.get("resolutions") or []
        if hist:
            row["resolutions"] = [
                {"resolution_id": h.get("resolution_id"), "status": h.get("status"),
                 "contested_by": sorted(h.get("contested_by") or [])}
                for h in hist
            ]
        out.append(row)
    return sorted(out, key=lambda x: str(x["residual_id"]))


def main(argv: list[str]) -> int:
    got = {p.stem: derive(json.loads(p.read_text()))
           for p in sorted(FIXTURES.glob("*.json")) if p.name != "expected.json"}
    if "--check" in argv:
        if not EXPECTED.exists():
            print("no expected.json - run without --check first")
            return 1
        want = json.loads(EXPECTED.read_text())
        if want != got:
            for k in sorted(set(want) | set(got)):
                if want.get(k) != got.get(k):
                    print(f"  {k}:\n    expected {json.dumps(want.get(k))}\n    got      {json.dumps(got.get(k))}")
            return 1
        print(f"OK - {len(got)} fixture(s) derive as recorded")
        return 0
    EXPECTED.write_text(json.dumps(got, indent=2) + "\n")
    print(f"wrote {EXPECTED.relative_to(ROOT)} ({len(got)} fixtures)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

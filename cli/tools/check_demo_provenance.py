#!/usr/bin/env python3
"""Every residual a demo ships can name the step that surfaced it.

A residual states what the trace did NOT establish. In a record whose whole claim is attribution,
an unattributed gap is the one artifact that undercuts the claim: the reader is told a limitation
exists and given no way to ask when it was noticed or by what. The viewer now renders `surfaced by`
on every residual card, so a demo missing the field advertises the hole on the front page.

This is not validity - `introduced_by_action_id` is optional in the spec (§13.1), and traces without
it are well-formed. It is a standard for what WE ship, which is why it lives here rather than in the
validator. Five of the eight shipped residuals had no introducing action before this check existed.

Checked for each Residual artifact under the scanned roots:

  1. it names an introducing action, via `payload.introduced_by_action_id` or `producer_action_id`;
  2. the two agree when both are present (the viewer falls back from one to the other);
  3. the action it names exists in the trace; and
  4. every `derived_from` edge and artifact `target` points at an artifact that exists.

    python3 cli/tools/check_demo_provenance.py [roots...]
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

# `examples/` is the source; `cli/ponens/demos/` is a gitignored build copy of it (cli/Makefile), so
# checking the source checks the copy by construction.
DEFAULT_ROOTS = ["examples"]


def check_trace(trace: dict, where: str) -> list[str]:
    bad: list[str] = []
    arts = trace.get("artifacts") or []
    ids = {a.get("artifact_id") for a in arts if isinstance(a, dict)}
    ids |= {m.get("reference_model_id") for m in (trace.get("reference_models") or [])}
    actions = {a.get("id") for a in (trace.get("actions") or []) if isinstance(a, dict)}

    # The legacy top-level carrier is not produced any more; a demo still using it renders through a
    # migration path rather than natively, so say so here instead of letting it rot quietly.
    for r in trace.get("residuals") or []:
        bad.append(f"{where}: residual {r.get('residual_id')} is in the legacy top-level "
                   f"`residuals` list - residuals are artifacts (§13, v1.8)")

    for a in arts:
        if not isinstance(a, dict) or a.get("artifact_type") != "Residual":
            continue
        rid = a.get("artifact_id")
        p = a.get("payload") or {}
        intro = p.get("introduced_by_action_id")
        prod = a.get("producer_action_id")
        if intro is None and prod is None:
            bad.append(f"{where}: residual {rid} names no introducing action "
                       f"(payload.introduced_by_action_id / producer_action_id)")
        elif intro is not None and prod is not None and intro != prod:
            bad.append(f"{where}: residual {rid} disagrees with itself - "
                       f"introduced_by_action_id {intro}, producer_action_id {prod}")
        for got in (intro, prod):
            if got is not None and got not in actions:
                bad.append(f"{where}: residual {rid} names action #{got}, which is not in the trace")
        for pid in a.get("derived_from") or []:
            if pid not in ids:
                bad.append(f"{where}: residual {rid} derives from {pid}, which is not in the trace")
        t = p.get("target") or {}
        if t.get("target_type") == "artifact" and t.get("target_id") not in ids:
            bad.append(f"{where}: residual {rid} targets artifact {t.get('target_id')}, "
                       f"which is not in the trace")
        for k in a.get("related_artifact_ids") or p.get("related_artifact_ids") or []:
            if k not in ids:
                bad.append(f"{where}: residual {rid} relates to {k}, which is not in the trace")
    return bad


def main(argv: list[str]) -> int:
    roots = argv[1:] or DEFAULT_ROOTS
    bad: list[str] = []
    traces = residuals = 0

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
            # `.walk.json` companions are narrated walkthroughs, not traces: they carry a prose
            # `residuals` summary with no ids and no artifacts. `artifacts` is what makes it a trace.
            if not isinstance(trace, dict) or "artifacts" not in trace:
                continue
            traces += 1
            residuals += sum(1 for a in trace["artifacts"]
                             if isinstance(a, dict) and a.get("artifact_type") == "Residual")
            bad += check_trace(trace, str(p.relative_to(ROOT)))

    if not traces:
        print(f"no traces found under {roots} - refusing to pass vacuously")
        return 1
    for b in bad:
        print(f"  {b}")
    print(f"{'FAIL' if bad else 'OK'} - {residuals} residual(s) across {traces} trace(s)"
          + (f", {len(bad)} problem(s)" if bad else " can each name the step that surfaced them"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

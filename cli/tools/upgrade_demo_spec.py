#!/usr/bin/env python3
"""Bring a hand-authored demo trace up to the current spec, additively.

The demo set was written against 1.1-1.8 and every one of them still validates: the format is
backward-compatible by design. What they cannot do is ANSWER the questions the newer views ask. Every
result in `stripe_v1_1.json` came back `grade: unranked` from `ponens trace symbols`, because grading
reads the oracle attribution block (§10.12) that 1.12 introduced and a 1.8 trace has none. A demo that
shows the reader an unranked record is showing them the tool failing.

This adds only what is DERIVABLE from what the trace already says - it invents no evidence:

  * `payload.oracle` on each evidence payload, from the `engine` the result already names and the
    artifact type it already is. The strength is the one that artifact type carries by definition
    (a reasoner's verdict is `proof`, a test run is `tests`), never a judgement about this result.
  * `spec_version`, bumped to the version those fields belong to.

It does NOT touch statuses, add results, or fill gaps. A refuted result stays refuted; a trace with
three declared residuals keeps three.

    python3 cli/tools/upgrade_demo_spec.py cli/ponens/demos/*.json [--to 1.13] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ponens import oracles  # noqa: E402

# What each evidence-bearing artifact type is produced by, and the guarantee that KIND of output
# carries. Not a verdict about any particular result - `status` already says that.
BY_TYPE = {
    "VerificationResult": ("reasoner", "proof"),
    "StateSpaceAnalysisResult": ("reasoner", "proof"),
    "ConformanceResult": ("reasoner", "proof"),
    "CoSimulationResult": ("reasoner", "proof"),
    "TestResult": ("tester", "tests"),
    "GeneratedTests": ("tester", "tests"),
    "CommandResult": ("analyzer", "static_analysis"),
    "Observation": ("monitor", "attested"),
    "UserApproval": ("attestor", "attested"),
}


def upgrade(trace: dict, to: str) -> list[str]:
    """Mutate `trace` in place. Returns a line per change, for the caller to print."""
    notes: list[str] = []

    for a in trace.get("artifacts") or []:
        t = a.get("artifact_type")
        if t not in BY_TYPE:
            continue
        p = a.get("payload")
        if not isinstance(p, dict):
            continue
        # NOT `attribution_of`: that DERIVES a block from the legacy `engine` field, so a pre-1.12
        # payload looks attributed while carrying no strength - which is precisely why every result
        # graded `unranked`. The thing that is missing is the strength, so that is what to test for.
        if oracles.strength_of(p):
            continue
        otype, strength = BY_TYPE[t]
        derived = oracles.attribution_of(p) or {}
        block = dict(derived)
        block["oracle_type"] = derived.get("oracle_type") or otype
        block["evidence_strength"] = strength
        engine = derived.get("id") or p.get("engine") or trace.get("model")
        if engine:
            block["id"] = str(engine)
        p["oracle"] = block
        notes.append(f"  + {block['oracle_type']}/{strength} on {a.get('artifact_id')} [{t}]")

    was = trace.get("spec_version")
    if was != to:
        trace["spec_version"] = to
        notes.append(f"  spec_version {was} -> {to}")
    return notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--to", default="1.13")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    for f in args.files:
        path = pathlib.Path(f)
        if path.name == "manifest.json":
            continue
        trace = json.loads(path.read_text())
        notes = upgrade(trace, args.to)
        print(f"{path.name}: {len(notes)} change(s)")
        for n in notes[:4]:
            print(n)
        if len(notes) > 4:
            print(f"  … {len(notes) - 4} more")
        if not args.dry_run and notes:
            path.write_text(json.dumps(trace, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

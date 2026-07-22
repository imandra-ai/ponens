#!/usr/bin/env python3
"""Faithfulness parity harness: the goal-faithfulness verdict must be IDENTICAL across the two
implementations that compute it independently —

  * the CLI / enrich evaluator — cli/ponens/goals.py       `faithfulness_of`  (the oracle)
  * the viewer evaluator        — viewer/core/faithfulness.mjs  `goalFaithfulnessV`  (the display)

Both read the same §18 goal; they must never disagree on met / certified / weakly_specified /
uncovered_clauses. Each case in faithfulness_cases.json also carries an `expect`, which pins the
ABSOLUTE verdict — so the two agreeing on a *wrong* answer still fails (guards against joint drift).

Run: python3 parity/check_faithfulness_parity.py   (exits non-zero on any divergence or wrong verdict)
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "cli"))
CASES_PATH = os.path.join(HERE, "faithfulness_cases.json")

from ponens.goals import faithfulness_of  # noqa: E402

GREEN, RED, GRAY, BOLD, RST = "\033[32m", "\033[31m", "\033[90m", "\033[1m", "\033[0m"


def _norm(d):
    return {
        "met": bool(d["met"]),
        "certified": bool(d["certified"]),
        "weakly_specified": bool(d["weakly_specified"]),
        "uncovered_clauses": sorted(d.get("uncovered_clauses") or []),
    }


def js_results():
    proc = subprocess.run(
        ["node", os.path.join(HERE, "run_faithfulness_js.mjs"), CASES_PATH],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        sys.exit(f"JS runner failed (exit {proc.returncode})")
    return {r["name"]: r for r in json.loads(proc.stdout)}


def main():
    with open(CASES_PATH) as f:
        cases = json.load(f)["cases"]
    js = js_results()
    fails = []

    print(f"\n{BOLD}Faithfulness parity: viewer JS (goalFaithfulnessV) vs CLI Python (faithfulness_of) "
          f"— {len(cases)} cases{RST}\n")
    for c in cases:
        name = c["name"]
        py = _norm(faithfulness_of(c["goal"]))
        jsv = _norm(js[name])
        exp = _norm(c["expect"]) if "expect" in c else None

        if py != jsv:
            mark, note = f"{RED}FAIL{RST}", f"JS={jsv} != CLI={py}"
            fails.append((name, note))
        elif exp is not None and py != exp:
            mark, note = f"{RED}FAIL{RST}", f"both agree on {py} but expected {exp}"
            fails.append((name, note))
        else:
            mark, note = f"{GREEN}OK  {RST}", f"both {py}"
        print(f"  {mark}  {name}\n        {GRAY}{note}{RST}")

    print(f"\n{BOLD}Summary{RST}: {GREEN}{len(cases) - len(fails)} agree{RST}, {RED}{len(fails)} fail{RST}")
    if fails:
        print(f"\n{RED}Divergences (viewer JS and CLI Python must match — and match `expect`):{RST}")
        for name, why in fails:
            print(f"  - {name}: {why}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

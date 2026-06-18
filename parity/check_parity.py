#!/usr/bin/env python3
"""Cross-language parity harness for the ponens policy evaluators.

There are two independent implementations of the temporal/scoped policy
language:

  * the CLI runtime evaluator   — cli/ponens/trace.py        (the oracle;
                                   this is what `ponens trace check` runs)
  * the browser evaluator       — website/src/lib/ltl.mjs    (the playground)

They do not share a trace format or an implementation, so they can drift. The
playground's contract (stated at the top of ltl.mjs) is that it must *never
disagree* with `ponens trace check`: for any policy it either returns the same
verdict, or it abstains ({supported:false}) — it must never report a concrete
verdict the CLI would contradict.

This harness encodes that contract. Each case in cases.json is a (formula,
canonical trace) pair. The canonical trace is rendered into both engines'
shapes, both verdicts are computed, and we assert:

    JS is UNSUPPORTED, or JS.verdict == CLI.verdict

Cases flagged "divergent": true are known, documented disagreements; they are
reported but do not fail the build.

Run:  python3 parity/check_parity.py
Exit: 0 if the contract holds for every non-divergent case, 1 otherwise.
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CLI = os.path.join(REPO, "cli")
CASES_PATH = os.path.join(HERE, "cases.json")

sys.path.insert(0, CLI)
from ponens.trace import evaluate_policy  # noqa: E402


def to_py_action(a, idx):
    """Canonical action -> CLI runtime action dict.

    Ids are 1-based and ascending so list order == chronological order, matching
    real traces (next_action_id starts at 1). Status maps onto the fields the
    CLI evaluator actually reads: completed/failed -> result_summary substring,
    proved/refuted/sat -> vg_result.status. A canonical `target` becomes
    request.path (get_action_target's fallback). Lowercase `flags` have no first-
    class field in the CLI engine — there an unknown lowercase atom degrades to a
    keyword substring match against the action text — so we surface each flag word
    in `detail` to mirror the browser engine's flag-membership check.
    """
    out = {
        "id": idx + 1,
        "type": a["type"],
        "category": a.get("category", "activity"),
        "evidence": [],
        "inputs": [],
        "outputs": [],
        "label": "",
    }
    status = a.get("status")
    if status in ("completed", "failed"):
        out["result_summary"] = status
    elif status in ("proved", "refuted", "sat"):
        out["vg_result"] = {"status": status}
    else:
        out["result_summary"] = ""
    if a.get("target") is not None:
        out["request"] = {"path": a["target"]}
    # Flags stand in for the action's free text. A predicate name matches with
    # underscores read as spaces (keyword = name.replace('_', ' ')), so surface the
    # space form here — identical to what the browser's searchText() composes.
    out["detail"] = " ".join(f.replace("_", " ") for f in (a.get("flags") or []))
    out["rationale"] = "ok" if a.get("rationale") else ""
    return out


def to_py_trace(case):
    return {
        "actions": [to_py_action(a, i) for i, a in enumerate(case.get("trace", []))],
        "artifacts": [],
        "residuals": [],
        "trigger": case.get("trigger", {}),
        "outcome": case.get("outcome", {}),
    }


def py_verdict(case):
    """Run the CLI oracle. Returns (bool|None, detail)."""
    policy = {"name": case["name"], "formula": case["formula"], "severity": "error"}
    status, detail = evaluate_policy(policy, to_py_trace(case))
    return {"passed": True, "failed": False, "unknown": None}[status], detail


def js_verdicts():
    """Run the JS engine once over the whole corpus; return {name: result}."""
    proc = subprocess.run(
        ["node", os.path.join(HERE, "run_js.mjs"), CASES_PATH],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        sys.exit(f"JS runner failed:\n{proc.stderr}")
    return {r["name"]: r for r in json.loads(proc.stdout)}


GREEN, RED, YELLOW, GRAY, BOLD, RST = (
    ("\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[1m", "\033[0m")
    if sys.stdout.isatty() else ("", "", "", "", "", "")
)


def fmt(v):
    return {True: "true", False: "false", None: "unknown"}[v]


def main():
    with open(CASES_PATH) as f:
        cases = json.load(f)["cases"]
    js = js_verdicts()

    failures, divergences, abstains, agreements = [], [], [], []

    print(f"\n{BOLD}Parity: browser evaluator vs. `ponens trace check` ({len(cases)} cases){RST}\n")
    for c in cases:
        name = c["name"]
        j = js[name]
        pv, pdetail = py_verdict(c)
        expect_unsupported = c.get("unsupported", False)
        divergent = c.get("divergent", False)

        if j["kind"] == "error":
            failures.append((name, f"JS errored: {j['error']}"))
            mark, note = f"{RED}ERR {RST}", f"JS error: {j['error']}"
        elif j["kind"] == "unsupported":
            # JS abstaining always satisfies the contract — it never yields a
            # verdict the CLI could contradict. It is only a problem when the
            # case carries `expect`, i.e. the browser is supposed to support it
            # (a regression in the abstain logic).
            if "expect" in c:
                failures.append((name, f"JS unexpectedly abstained: {j['reason']}"))
                mark, note = f"{RED}FAIL{RST}", f"JS abstains ({j['reason']}); expected {fmt(c['expect'])}"
            elif divergent:
                divergences.append((name, "abstain", fmt(pv)))
                mark, note = f"{YELLOW}DIVG{RST}", f"JS abstains ({j['reason']}); CLI={fmt(pv)} (documented)"
            else:
                abstains.append(name)
                mark, note = f"{YELLOW}ABST{RST}", f"JS abstains ({j['reason']}); CLI={fmt(pv)}"
        else:
            jv = j["verdict"]
            # Lock the JS side against its intended verdict when given.
            if "expect" in c and jv != c["expect"]:
                failures.append((name, f"JS verdict {fmt(jv)} != expected {fmt(c['expect'])}"))
            if jv == pv:
                agreements.append(name)
                mark, note = f"{GREEN}OK  {RST}", f"both {fmt(jv)}"
            elif divergent:
                divergences.append((name, fmt(jv), fmt(pv)))
                mark, note = f"{YELLOW}DIVG{RST}", f"JS={fmt(jv)} CLI={fmt(pv)} (documented)"
            else:
                failures.append((name, f"disagree: JS={fmt(jv)} CLI={fmt(pv)}"))
                mark, note = f"{RED}FAIL{RST}", f"JS={fmt(jv)} CLI={fmt(pv)}"

        print(f"  {mark}  {name}\n        {GRAY}{note}{RST}")

    print(f"\n{BOLD}Summary{RST}")
    print(f"  {GREEN}{len(agreements)} agree{RST}, "
          f"{YELLOW}{len(abstains)} JS-abstain{RST}, "
          f"{YELLOW}{len(divergences)} documented-divergence{RST}, "
          f"{RED}{len(failures)} fail{RST}")

    if divergences:
        print(f"\n{YELLOW}Documented divergences (engines disagree, accepted):{RST}")
        for name, jv, pv in divergences:
            print(f"  - {name}: JS={jv} CLI={pv}")

    if failures:
        print(f"\n{RED}{BOLD}Contract violations:{RST}")
        for name, why in failures:
            print(f"  - {name}: {why}")
        return 1

    print(f"\n{GREEN}Parity contract holds.{RST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

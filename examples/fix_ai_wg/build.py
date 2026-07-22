#!/usr/bin/env python3
"""Build (and self-verify) the FIX AI WG "six points" demo traces.

For each of the FIX AI Working Group's six agentic-governance failure modes, we emit a PASS trace and
a FAIL trace, each a small but realistic execution workflow (actions + artifacts + `derived_from`
lineage, so the visualizer renders a real DAG) carrying the single agentic-ai-runtime-governance
policy that governs that point. Each trace is then checked with `ponens trace check --write`, which
proves the PASS/FAIL verdict AND stamps `policy_evaluations` (with evidence) into the file — so the
deck's examples and the visualizer are grounded in the real evaluator.

Run from anywhere:  python3 examples/fix_ai_wg/build.py
"""
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "examples", "fix_ai_wg")


def load_policy(pid):
    with open(os.path.join(ROOT, "gallery", "policies", f"{pid}.json")) as f:
        p = json.load(f)
    return {"policy_id": p["id"], "name": p["id"], "severity": p["severity"],
            "scope": "trace", "kind": "trace_invariant", "formula": p["formula"]}


def act(aid, atype, rationale, label="", result_summary="", inputs=None, outputs=None, agent=None):
    a = {"id": aid, "type": atype, "rationale": rationale}
    if label:
        a["label"] = label
    if result_summary:
        a["result_summary"] = result_summary
    if inputs is not None:
        a["inputs"] = inputs
    if outputs is not None:
        a["outputs"] = outputs
    if agent is not None:
        a["agent"] = agent
    return a


def art(aid, atype, name, producer, derived_from=None):
    a = {"artifact_id": aid, "artifact_type": atype, "name": name, "producer_action_id": producer}
    if derived_from:
        a["derived_from"] = derived_from
    return a


def trace(tid, policy, actions, artifacts):
    return {"trace_id": tid, "spec_version": "1.6", "trigger": {}, "outcome": {},
            "policies": [policy], "artifacts": artifacts, "actions": actions}


CASES = []

# 1 — Latency-induced stale decisions → retrieved_data_attributed
#     G(Retrieve → provenance_checked ∧ recency_checked)
p = load_policy("retrieved_data_attributed")
CASES.append((1, "stale_decisions", "retrieved_data_attributed",
    trace("fixwg-1-stale-pass", p, [
        act(1, "Retrieve", "pull the NBBO before sizing the child order",
            label="market data: NBBO for AAPL — provenance checked (source=SIP), recency checked (age 38ms < 250ms bound)",
            outputs=["snapshot"]),
        act(2, "Compute", "size the child order off a quote proven fresh",
            inputs=["snapshot"], outputs=["sizing-plan"]),
        act(3, "Decision", "set a limit price within the recency-checked spread",
            inputs=["sizing-plan"], outputs=["price-decision"]),
        act(4, "Release", "send the child order", inputs=["price-decision"], outputs=["child-order"]),
    ], [
        art("snapshot", "AnalysisNote", "NBBO snapshot (38ms)", 1),
        art("sizing-plan", "Plan", "child-order size", 2, ["snapshot"]),
        art("price-decision", "AnalysisNote", "limit price", 3, ["sizing-plan"]),
        art("child-order", "Commit", "AAPL child order", 4, ["price-decision"]),
    ]),
    trace("fixwg-1-stale-fail", p, [
        act(1, "Retrieve", "read a quote from the local cache to save a hop",
            label="market data: AAPL quote read from cache", outputs=["snapshot"]),  # no recency evidence
        act(2, "Compute", "size the child order", inputs=["snapshot"], outputs=["sizing-plan"]),
        act(3, "Decision", "set a limit price", inputs=["sizing-plan"], outputs=["price-decision"]),
        act(4, "Release", "send the child order", inputs=["price-decision"], outputs=["child-order"]),
    ], [
        art("snapshot", "AnalysisNote", "cached AAPL quote", 1),
        art("sizing-plan", "Plan", "child-order size", 2, ["snapshot"]),
        art("price-decision", "AnalysisNote", "limit price", 3, ["sizing-plan"]),
        art("child-order", "Commit", "AAPL child order", 4, ["price-decision"]),
    ])))

# 2 — Tool failures during execution → tool_calls_allowlisted
#     G(ToolCall → in_allowlist)   (failed tool + fallback are recorded actions)
p = load_policy("tool_calls_allowlisted")
CASES.append((2, "tool_failures", "tool_calls_allowlisted",
    trace("fixwg-2-tool-pass", p, [
        act(1, "Retrieve", "read the order book", outputs=["book"]),
        act(2, "Compute", "build the routing plan", inputs=["book"], outputs=["routing-plan"]),
        act(3, "ToolCall", "route via the certified smart-order-router",
            label="invoke SOR-v3 (in allowlist, tier-2 certified)", result_summary="timeout after 900ms — failed",
            inputs=["routing-plan"], outputs=["sor-result"]),
        act(4, "Compute", "SOR timed out; fall back to the certified TWAP scheduler",
            label="fallback: TWAP scheduler (in allowlist)", inputs=["sor-result"], outputs=["twap-plan"]),
        act(5, "Release", "execute the documented fallback schedule",
            inputs=["twap-plan"], outputs=["child-orders"]),
    ], [
        art("book", "AnalysisNote", "L2 order book", 1),
        art("routing-plan", "Plan", "route plan", 2, ["book"]),
        art("sor-result", "CommandResult", "SOR timeout", 3, ["routing-plan"]),
        art("twap-plan", "Plan", "TWAP fallback", 4, ["sor-result"]),
        art("child-orders", "Commit", "child orders", 5, ["twap-plan"]),
    ]),
    trace("fixwg-2-tool-fail", p, [
        act(1, "Retrieve", "read the order book", outputs=["book"]),
        act(2, "Compute", "build the routing plan", inputs=["book"], outputs=["routing-plan"]),
        act(3, "ToolCall", "reach for an external dark-pool connector to beat the clock",
            label="invoke uncertified dark-pool-connector", result_summary="returned malformed fill — failed",
            inputs=["routing-plan"], outputs=["dp-result"]),  # not allowlisted
        act(4, "Release", "send the order anyway", inputs=["dp-result"], outputs=["child-order"]),
    ], [
        art("book", "AnalysisNote", "L2 order book", 1),
        art("routing-plan", "Plan", "route plan", 2, ["book"]),
        art("dp-result", "CommandResult", "dark-pool fill", 3, ["routing-plan"]),
        art("child-order", "Commit", "child order", 4, ["dp-result"]),
    ])))

# 3 — Memory contamination → data_flow_integrity (structural lineage)
p = load_policy("data_flow_integrity")
CASES.append((3, "memory_contamination", "data_flow_integrity",
    trace("fixwg-3-memory-pass", p, [
        act(1, "Retrieve", "load THIS order's working memory", outputs=["mem-ctx-771"]),
        act(2, "Retrieve", "pull current market data", outputs=["market-771"]),
        act(3, "Compute", "size the order from context produced in this workflow",
            inputs=["mem-ctx-771", "market-771"], outputs=["sizing-plan"]),
        act(4, "Decision", "risk gate", inputs=["sizing-plan"], outputs=["risk-ok"]),
        act(5, "Release", "execute", inputs=["risk-ok"], outputs=["child-order"]),
    ], [
        art("mem-ctx-771", "AnalysisNote", "working memory (order 771)", 1),
        art("market-771", "AnalysisNote", "market snapshot", 2),
        art("sizing-plan", "Plan", "size plan", 3, ["mem-ctx-771", "market-771"]),
        art("risk-ok", "AnalysisNote", "risk cleared", 4, ["sizing-plan"]),
        art("child-order", "Commit", "child order", 5, ["risk-ok"]),
    ]),
    trace("fixwg-3-memory-fail", p, [
        act(1, "Retrieve", "load working memory", outputs=["mem-ctx-771"]),
        act(2, "Retrieve", "pull current market data", outputs=["market-771"]),
        act(3, "Compute", "size the order — but reuse context bled in from a different order's run",
            inputs=["mem-ctx-503-batch", "market-771"], outputs=["sizing-plan"]),  # foreign, no producer here
        act(4, "Decision", "risk gate", inputs=["sizing-plan"], outputs=["risk-ok"]),
        act(5, "Release", "execute", inputs=["risk-ok"], outputs=["child-order"]),
    ], [
        art("mem-ctx-771", "AnalysisNote", "working memory (order 771)", 1),
        art("market-771", "AnalysisNote", "market snapshot", 2),
        art("sizing-plan", "Plan", "size plan (contaminated)", 3, ["market-771"]),
        art("risk-ok", "AnalysisNote", "risk cleared", 4, ["sizing-plan"]),
        art("child-order", "Commit", "child order", 5, ["risk-ok"]),
    ])))

# 4 — Dynamic objective changes → execution_linked_to_intent
#     G(ToolCall ∨ Release ∨ Deploy → intent_resolved)
p = load_policy("execution_linked_to_intent")
CASES.append((4, "objective_change", "execution_linked_to_intent",
    trace("fixwg-4-intent-pass", p, [
        act(1, "Decision", "declare the execution objective: VWAP", label="intent declared: IntentID VWAP-770",
            outputs=["intent-vwap"]),
        act(2, "Retrieve", "observe realized volatility", outputs=["vol-obs"]),
        act(3, "Decision", "vol spiked 3x; revise objective VWAP → Implementation Shortfall",
            label="objective revised — new intent declared: IntentID IS-771 (max 8% ADV)",
            inputs=["intent-vwap", "vol-obs"], outputs=["intent-is"]),
        act(4, "Compute", "build the IS schedule", inputs=["intent-is"], outputs=["is-schedule"]),
        act(5, "Release", "execute against the newly declared objective",
            label="child order — intent resolved → IntentID IS-771", inputs=["is-schedule"], outputs=["child-orders"]),
    ], [
        art("intent-vwap", "Plan", "objective: VWAP-770", 1),
        art("vol-obs", "AnalysisNote", "volatility spike", 2),
        art("intent-is", "Plan", "objective: IS-771", 3, ["intent-vwap", "vol-obs"]),
        art("is-schedule", "Plan", "IS schedule", 4, ["intent-is"]),
        art("child-orders", "Commit", "child orders", 5, ["is-schedule"]),
    ]),
    trace("fixwg-4-intent-fail", p, [
        act(1, "Decision", "declare the execution objective: VWAP", label="objective: VWAP", outputs=["intent-vwap"]),
        act(2, "Retrieve", "observe realized volatility", outputs=["vol-obs"]),
        act(3, "Decision", "switch the objective to Implementation Shortfall",
            label="objective changed to IS", inputs=["intent-vwap", "vol-obs"], outputs=["intent-is"]),  # no re-declared IntentID
        act(4, "Compute", "build the schedule", inputs=["intent-is"], outputs=["is-schedule"]),
        act(5, "Release", "execute", label="child order sent", inputs=["is-schedule"], outputs=["child-orders"]),  # not linked to intent
    ], [
        art("intent-vwap", "Plan", "objective: VWAP", 1),
        art("vol-obs", "AnalysisNote", "volatility spike", 2),
        art("intent-is", "Plan", "objective: IS", 3, ["intent-vwap", "vol-obs"]),
        art("is-schedule", "Plan", "schedule", 4, ["intent-is"]),
        art("child-orders", "Commit", "child orders", 5, ["is-schedule"]),
    ])))

# 5 — Multi-agent responsibility → agent_identity_resolved
#     G(action → agent_id_resolved ∧ kya_valid)
p = load_policy("agent_identity_resolved")
CASES.append((5, "multi_agent", "agent_identity_resolved",
    trace("fixwg-5-agents-pass", p, [
        act(1, "Retrieve", "market-data agent pulls the book", agent="AGT-DATA",
            label="agent id resolved: AGT-DATA · kya valid (IAL2 principal)", outputs=["book"]),
        act(2, "Compute", "risk agent evaluates exposure", agent="AGT-RISK",
            label="agent id resolved: AGT-RISK · kya valid", inputs=["book"], outputs=["risk-report"]),
        act(3, "Compute", "execution agent builds the plan", agent="AGT-EXEC",
            label="agent id resolved: AGT-EXEC · kya valid", inputs=["risk-report"], outputs=["exec-plan"]),
        act(4, "Release", "supervisor approves and releases", agent="AGT-SUP",
            label="agent id resolved: AGT-SUP · kya valid", inputs=["exec-plan"], outputs=["child-order"]),
    ], [
        art("book", "AnalysisNote", "order book", 1),
        art("risk-report", "AnalysisNote", "risk report", 2, ["book"]),
        art("exec-plan", "Plan", "execution plan", 3, ["risk-report"]),
        art("child-order", "Commit", "child order", 4, ["exec-plan"]),
    ]),
    trace("fixwg-5-agents-fail", p, [
        act(1, "Retrieve", "market-data agent pulls the book", agent="AGT-DATA",
            label="agent id resolved: AGT-DATA · kya valid", outputs=["book"]),
        act(2, "Compute", "risk evaluated", inputs=["book"], outputs=["risk-report"]),  # unattributed
        act(3, "Compute", "execution agent builds the plan", agent="AGT-EXEC",
            label="agent id resolved: AGT-EXEC · kya valid", inputs=["risk-report"], outputs=["exec-plan"]),
        act(4, "Release", "supervisor releases", agent="AGT-SUP",
            label="agent id resolved: AGT-SUP · kya valid", inputs=["exec-plan"], outputs=["child-order"]),
    ], [
        art("book", "AnalysisNote", "order book", 1),
        art("risk-report", "AnalysisNote", "risk report", 2, ["book"]),
        art("exec-plan", "Plan", "execution plan", 3, ["risk-report"]),
        art("child-order", "Commit", "child order", 4, ["exec-plan"]),
    ])))

# 6 — Missing reasoning provenance → decision_path_reconstructable
#     G(Release ∨ Deploy → decision_path_present)
p = load_policy("decision_path_reconstructable")
CASES.append((6, "reasoning_provenance", "decision_path_reconstructable",
    trace("fixwg-6-provenance-pass", p, [
        act(1, "Retrieve", "gather venue stats (LIT-A, LIT-B, DARK-C)", outputs=["venue-stats"]),
        act(2, "Compute", "compare venues on fee / latency / toxicity",
            inputs=["venue-stats"], outputs=["venue-comparison"]),
        act(3, "Decision", "reject LIT-A (fee), reject DARK-C (toxicity), choose LIT-B",
            label="venue selection reasoning recorded", inputs=["venue-comparison"],
            outputs=["venue-choice", "rejected-LIT-A", "rejected-DARK-C"]),
        act(4, "Release", "execute on the chosen venue",
            label="child order — decision path present → DecisionPathID DP-903",
            inputs=["venue-choice"], outputs=["child-order"]),
    ], [
        art("venue-stats", "AnalysisNote", "venue stats", 1),
        art("venue-comparison", "AnalysisNote", "venue comparison", 2, ["venue-stats"]),
        art("venue-choice", "Plan", "chosen: LIT-B", 3, ["venue-comparison"]),
        art("rejected-LIT-A", "AnalysisNote", "rejected: LIT-A (fee)", 3, ["venue-comparison"]),
        art("rejected-DARK-C", "AnalysisNote", "rejected: DARK-C (toxicity)", 3, ["venue-comparison"]),
        art("child-order", "Commit", "child order", 4, ["venue-choice"]),
    ]),
    trace("fixwg-6-provenance-fail", p, [
        act(1, "Compute", "pick a venue", outputs=["venue-choice"]),
        act(2, "Release", "execute", label="child order sent to venue LIT-B",
            inputs=["venue-choice"], outputs=["child-order"]),  # outcome only, no decision path
    ], [
        art("venue-choice", "Plan", "venue: LIT-B", 1),
        art("child-order", "Commit", "child order", 2, ["venue-choice"]),
    ])))


# Curated narrative (meta-actions) per trace — the named phases the visualizer's Steps view groups by.
# (title, intent, [action_ids]); without these the viewer lumps every action under "Other".
METAS = {
    "fixwg-1-stale-pass": [("Retrieve fresh market data", "get a provenance- and recency-checked quote", [1]),
                           ("Size & price the order", "derive size and limit price from the fresh quote", [2, 3]),
                           ("Execute", "send the child order", [4])],
    "fixwg-2-tool-pass": [("Read the book & plan the route", "prepare the routing plan", [1, 2]),
                          ("Route — tool call + fallback", "call the SOR; on failure fall back to TWAP", [3, 4]),
                          ("Execute", "run the fallback schedule", [5])],
    "fixwg-2-tool-fail": [("Read the book & plan the route", "prepare the routing plan", [1, 2]),
                          ("Route via an external tool", "reach for an uncertified connector", [3]),
                          ("Execute", "send the order", [4])],
    "fixwg-3-memory-pass": [("Load context & market data", "gather this order's memory and market snapshot", [1, 2]),
                            ("Size & risk-gate", "size from in-workflow context and clear risk", [3, 4]),
                            ("Execute", "send the child order", [5])],
    "fixwg-4-intent-pass": [("Declare objective", "set the execution objective (VWAP)", [1]),
                            ("Revise objective on volatility", "switch VWAP → Implementation Shortfall with rationale", [2, 3]),
                            ("Schedule & execute", "build the IS schedule and execute", [4, 5])],
    "fixwg-5-agents-pass": [("Data agent gathers", "pull the order book", [1]),
                            ("Risk & execution agents plan", "evaluate risk and build the plan", [2, 3]),
                            ("Supervisor approves & releases", "sign off and release", [4])],
    "fixwg-6-provenance-pass": [("Compare venues", "gather stats and compare on fee/latency/toxicity", [1, 2]),
                                ("Select venue (reject alternatives)", "reject LIT-A and DARK-C, choose LIT-B", [3]),
                                ("Execute", "send the child order", [4])],
    "fixwg-6-provenance-fail": [("Pick a venue", "choose a venue", [1]), ("Execute", "send the order", [2])],
}
# fail traces that mirror their pass shape reuse the pass phases.
for _pid in ("fixwg-1-stale", "fixwg-3-memory", "fixwg-4-intent", "fixwg-5-agents"):
    METAS[f"{_pid}-fail"] = METAS[f"{_pid}-pass"]


def apply_metas(tr):
    """Attach meta_actions (and link each action's meta_action_id) so the Steps view names the phases."""
    spec = METAS.get(tr["trace_id"])
    if not spec:
        return tr
    metas = []
    for i, (title, intent, aids) in enumerate(spec, 1):
        mid = f"m{i}"
        metas.append({"id": mid, "title": title, "intent": intent, "action_ids": aids,
                      "status": "completed", "source": "plan_declared"})
        for a in tr["actions"]:
            if a["id"] in aids:
                a["meta_action_id"] = mid
    tr["meta_actions"] = metas
    return tr


def check_and_stamp(path, policy_id):
    """Stamp policy_evaluations (with evidence) into the trace and return the target status."""
    subprocess.run(["ponens", "trace", "check", path, "--write"], capture_output=True, text=True)
    tr = json.load(open(path))
    for e in tr.get("policy_evaluations", []):
        if e["policy_id"] == policy_id:
            return e["status"]
    return "(missing)"


def main():
    os.makedirs(OUT, exist_ok=True)
    manifest, ok = [], True
    for n, slug, pid, tpass, tfail in CASES:
        fp = os.path.join(OUT, f"case{n}_{slug}_pass.json")
        ff = os.path.join(OUT, f"case{n}_{slug}_fail.json")
        json.dump(apply_metas(tpass), open(fp, "w"), indent=2)
        json.dump(apply_metas(tfail), open(ff, "w"), indent=2)
        sp, sf = check_and_stamp(fp, pid), check_and_stamp(ff, pid)
        good = (sp == "passed" and sf == "failed")
        ok = ok and good
        print(f"  {'OK ' if good else 'XX '}case {n} [{pid}]  pass→{sp}  fail→{sf}")
        manifest.append({"case": n, "slug": slug, "policy": pid,
                         "pass_file": os.path.basename(fp), "fail_file": os.path.basename(ff),
                         "pass_status": sp, "fail_status": sf})
    json.dump({"description": "FIX AI WG six-points demo traces (pass/fail per governing policy).",
               "cases": manifest}, open(os.path.join(OUT, "manifest.json"), "w"), indent=2)
    print("\nAll pass/fail as expected." if ok else "\nSOME CASES DID NOT DISCRIMINATE — see XX above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

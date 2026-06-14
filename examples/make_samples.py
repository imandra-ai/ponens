#!/usr/bin/env python3
"""Generate rich sample traces (spec 1.6) that exercise every viewer surface:
the meta-action zoom, artifact lineage, formal reasoning, and policies.

Each sample follows the same backbone — research -> decide -> formalize & verify
-> implement -> test -> commit — so all structural checks (data_flow_integrity,
goals_reference_valid_artifacts, generated_tests_require_decomposition,
files_modified_consistent) pass, and the lineage DAG is well-formed.

Run:  python3 examples/make_samples.py   (writes examples/sample_*.json)
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def act(i, typ, label, rationale, cat="activity", inputs=None, outputs=None,
        detail=None, result=None, options=None, file_ref=None):
    a = {"id": i, "type": typ, "category": cat, "label": label, "rationale": rationale,
         "inputs": inputs or [], "outputs": outputs or [], "evidence": []}
    if detail:
        a["detail"] = detail
    if result:
        a["result_summary"] = result
    if options:
        a["options"] = options
    if file_ref:
        a["evidence"].append({"type": "FileRef", "ref": file_ref})
    return a


def art(aid, atype, name, producer, derived=None, payload=None, summary=None):
    o = {"artifact_id": aid, "artifact_type": atype, "name": name, "producer_action_id": producer}
    if derived:
        o["derived_from"] = derived
    if payload is not None:
        o["payload"] = payload
    if summary:
        o["summary"] = summary
    return o


def assemble(trace_id, title, trigger, outcome, actions, meta_actions, artifacts,
             policies, evals, residuals, files):
    by = {aid: m["id"] for m in meta_actions for aid in m["action_ids"]}
    for a in actions:
        if a["id"] in by:
            a["meta_action_id"] = by[a["id"]]
    return {
        "trace_id": trace_id, "spec_version": "1.6",
        "assistant": "ponens", "model": "example-model",
        "timestamp": "2026-06-14T12:00:00Z", "title": title,
        "trigger": {"type": "TaskReceived", "description": trigger},
        "actions": actions, "meta_actions": meta_actions,
        "outcome": {"type": "ProcessCompleted", "summary": outcome},
        "artifacts": artifacts, "policies": policies, "policy_evaluations": evals,
        "residuals": residuals, "files_modified": sorted(set(files)),
        "metrics": {"total_actions": len(actions), "meta_action_count": len(meta_actions)},
    }


def proved(props):
    return {"proved": {"proof_pp": f"All {len(props)} properties proved.",
                       "properties": [{"name": n, "status": "proved", "src": s} for n, s in props]}}


def vg_payload(gid, desc, target_iml, sym, props):
    return {"goal_id": gid, "kind": "verify", "description": desc,
            "target_artifact_id": target_iml, "target_symbol": sym,
            "properties": [{"name": n, "status": "pending", "src": s} for n, s in props]}


def pol(pid, name, desc, formula, scope="action", kind="trace_invariant", severity="warning"):
    return {"policy_id": pid, "name": name, "description": desc, "severity": severity,
            "scope": scope, "kind": kind, "formula": formula}


# ---------------------------------------------------------------------------
# Sample A — payments: prove capture can't double-charge, then implement
# ---------------------------------------------------------------------------
def sample_a():
    props = [("prop_capture_idempotent",
              "let prop_capture_idempotent (k:key) (o:order) =\n  captured o ==> capture k o = o"),
             ("prop_amount_preserved",
              "let prop_amount_preserved (k:key) (o:order) =\n  inv_amounts o ==> inv_amounts (capture k o)")]
    actions = [
        act(1, "ReadFile", "src/billing/payment.py", "Read the capture path before changing it.",
            outputs=["a1"]),
        act(2, "AnalyzeCode", "Capture path: 6 states, retried by the gateway",
            "The gateway retries capture on timeout, so a non-idempotent capture can double-charge.",
            inputs=["a1"], outputs=["a2"]),
        act(3, "ExclusiveDecision", "Idempotency strategy",
            "Dedupe on (charge_id, idempotency_key) vs a distributed lock — chose the key (no infra).",
            cat="gateway", options=[
                {"label": "Dedupe on (charge_id, idempotency_key)", "chosen": True},
                {"label": "Distributed lock in Redis", "chosen": False,
                 "rejected_because": "adds infra + a new failure mode"}]),
        act(4, "Formalize", "Formalize capture_payment -> IML",
            "Translate the capture transition into pure IML so the invariant is checkable.",
            cat="reasoning", inputs=["a2"], outputs=["a3"]),
        act(5, "DefineVG", "Goal: capture is idempotent and amount-preserving",
            "State the two properties a correct idempotent capture must satisfy.",
            cat="reasoning", inputs=["a3"], outputs=["a4"]),
        act(6, "Verify", "Verify capture idempotency",
            "Prove the two properties hold for all orders and keys.",
            cat="reasoning", inputs=["a4"], outputs=["a5"], result="proved: 2/2 properties"),
        act(7, "Decompose", "Decompose capture into 4 regions",
            "Region-split the input space to drive exhaustive test generation.",
            cat="reasoning", inputs=["a3"], outputs=["a6"]),
        act(8, "EditFile", "src/billing/payment.py",
            "Add the idempotency-key dedupe guard at the top of capture_payment.",
            inputs=["a5"], outputs=["a7"], file_ref="src/billing/payment.py"),
        act(9, "GenerateTests", "Generate idempotency tests from regions",
            "One test per decomposition region — covers the dedupe and the replay cases.",
            inputs=["a6"], outputs=["a8"]),
        act(10, "RunTests", "pytest tests/billing -q",
            "Run the generated suite plus the existing billing tests.",
            inputs=["a8"], outputs=["a9"], result="24 passed",
            detail="pytest tests/billing -q"),
        act(11, "GitCommit", "commit: idempotent capture",
            "Commit the verified change with the proof referenced in the message.",
            inputs=["a7"], detail="git commit -m 'billing: idempotent capture (proved)'"),
    ]
    artifacts = [
        art("a1", "SourceCode", "payment.py (original)", 1),
        art("a2", "AnalysisNote", "capture is retried, not idempotent", 2, ["a1"]),
        art("a3", "IMLModel", "capture_payment (IML)", 4, ["a2"], {
            "status": "proved", "src_lang": "python",
            "iml_code": "let capture (k:key) (o:order) =\n  if seen k o then o\n  else { o with captured = true; seen = add k o.seen }",
            "symbols": ["capture", "inv_amounts"]}),
        art("a4", "VerificationGoal", "idempotency goal", 5, ["a3"],
            vg_payload(1, "capture is idempotent and preserves amounts", "a3", "capture", props)),
        art("a5", "VerificationResult", "idempotency proved", 6, ["a4"], {
            "goal_id": 1, "goal_artifact_id": "a4", "status": "proved",
            "engine": "imandrax", "result": proved(props)}),
        art("a6", "Decomposition", "capture regions", 7, ["a3"], {
            "target_artifact_id": "a3", "target_function": "capture", "complete": True,
            "regions": [{"id": "r1", "constraint": "seen k o"}, {"id": "r2", "constraint": "not seen k o & captured o"},
                        {"id": "r3", "constraint": "not seen k o & not captured o"}, {"id": "r4", "constraint": "refunded o"}]}),
        art("a7", "Diff", "payment.py dedupe guard", 8, ["a5"]),
        art("a8", "GeneratedTests", "idempotency suite", 9, ["a6"], {
            "function": "capture", "language": "python", "source_decomposition_artifact_id": "a6",
            "tests": [{"name": "test_replayed_capture_noop"}, {"name": "test_first_capture_charges"},
                      {"name": "test_capture_after_refund_rejected"}, {"name": "test_amounts_preserved"}]}),
        art("a9", "CommandResult", "pytest: 24 passed", 10, ["a8"]),
    ]
    metas = [
        {"id": "m1", "title": "Understand the capture path", "intent": "See why retries can double-charge",
         "action_ids": [1, 2], "source": "plan_declared", "status": "completed", "produced_artifact_ids": ["a1", "a2"]},
        {"id": "m2", "title": "Choose an idempotency strategy", "intent": "Key-based dedupe vs a lock",
         "action_ids": [3], "source": "turn_segmented"},
        {"id": "m3", "title": "Formally verify no double-charge",
         "intent": "Prove capture is idempotent and amount-preserving", "action_ids": [4, 5, 6, 7],
         "source": "plan_declared", "status": "completed", "produced_artifact_ids": ["a3", "a4", "a5", "a6"],
         "residual_ids": ["r1"]},
        {"id": "m4", "title": "Implement and test", "intent": "Add the guard, generate + run tests",
         "action_ids": [8, 9, 10], "source": "plan_declared", "status": "completed",
         "produced_artifact_ids": ["a7", "a8", "a9"]},
        {"id": "m5", "title": "Commit", "intent": "Land the verified change",
         "action_ids": [11], "source": "turn_segmented"},
    ]
    policies = [
        pol("p1", "research_before_edit", "Every edit is preceded by research on the same file",
            "G(EditFile → P_target(ReadFile ∨ ReadDocumentation ∨ SearchCode ∨ AnalyzeCode))"),
        pol("p2", "all_decisions_justified", "Every decision records its rationale",
            "G(gateway → rationale ≠ ∅)"),
        pol("p3", "data_flow_integrity", "Every consumed artifact has a unique earlier producer",
            "data_flow_integrity", kind="structural", severity="error"),
        pol("p4", "generated_tests_require_decomposition",
            "Generated tests must derive from a decomposition", "generated_tests_require_decomposition",
            kind="structural"),
    ]
    evals = [
        {"policy_id": "p1", "status": "passed", "note": "edit #8 preceded by read #1 / analyze #2"},
        {"policy_id": "p2", "status": "passed", "note": "decision #3 records its rationale"},
        {"policy_id": "p3", "status": "passed", "note": "DAG well-formed"},
        {"policy_id": "p4", "status": "passed", "note": "a8 derives from decomposition a6"},
    ]
    residuals = [
        {"residual_id": "r1", "kind": "assumption", "severity": "high", "status": "acknowledged",
         "source": "agent_declared", "statement": "Assumes the gateway sends a stable idempotency key per logical charge.",
         "target": {"target_type": "artifact", "target_id": "a3"},
         "suggested_check": "Confirm the gateway's retry contract guarantees a stable key.", "introduced_by_action_id": 4},
        {"residual_id": "r2", "kind": "out_of_scope", "severity": "medium", "status": "open",
         "source": "agent_declared", "statement": "Concurrent capture+refund races are not modelled (single-threaded application only)."},
    ]
    return assemble("trace-sample-payment-idempotency",
                    "Make payment capture idempotent (proved)",
                    "capture is being double-charged on gateway retries — make it idempotent and prove it",
                    "Proved capture is idempotent and amount-preserving (2/2), implemented the key-based guard, 24 tests pass.",
                    actions, metas, artifacts, policies, evals, residuals, ["src/billing/payment.py"])


# ---------------------------------------------------------------------------
# Sample B — auth: model the state machine, prove every state reachable
# ---------------------------------------------------------------------------
def sample_b():
    props = [("prop_all_states_reachable",
              "let prop_all_states_reachable = forall s. exists path. reaches initial path s"),
             ("prop_no_orphan_authenticated",
              "let prop_no_orphan_authenticated (s:state) =\n  s = Authenticated ==> came_from [LoggingIn] s")]
    actions = [
        act(1, "ReadFile", "src/auth/machine.ts", "Read the existing ad-hoc auth booleans.", outputs=["a1"]),
        act(2, "AnalyzeCode", "5 boolean flags model 7 real states",
            "The boolean soup admits impossible states (e.g. loading && error).", inputs=["a1"], outputs=["a2"]),
        act(3, "ExclusiveDecision", "Model as an explicit state machine",
            "XState chart vs a hand-rolled reducer — chose XState for the reachability tooling.",
            cat="gateway",
            options=[{"label": "XState chart", "chosen": True},
                     {"label": "Hand-rolled reducer", "chosen": False, "rejected_because": "no reachability analysis"}]),
        act(4, "Formalize", "Formalize the chart -> IML transition function",
            "Encode states + transitions so reachability is decidable.", cat="reasoning",
            inputs=["a2"], outputs=["a3"]),
        act(5, "DefineVG", "Goal: every state reachable, no orphan Authenticated",
            "State the reachability + provenance properties.", cat="reasoning",
            inputs=["a3"], outputs=["a4"]),
        act(6, "Verify", "Verify reachability",
            "Prove all 7 states are reachable and Authenticated only follows LoggingIn.", cat="reasoning",
            inputs=["a4"], outputs=["a5"], result="proved: 2/2 properties"),
        act(7, "Decompose", "Decompose transitions by event",
            "Split by triggering event to generate one test per transition.", cat="reasoning",
            inputs=["a3"], outputs=["a6"]),
        act(8, "EditFile", "src/auth/machine.ts", "Replace the booleans with the XState machine.",
            inputs=["a5"], outputs=["a7"], file_ref="src/auth/machine.ts"),
        act(9, "GenerateTests", "Generate transition tests", "One test per event/transition region.",
            inputs=["a6"], outputs=["a8"]),
        act(10, "RunTests", "vitest run", "Run the transition suite.", inputs=["a8"], outputs=["a9"],
            result="31 passed", detail="vitest run"),
        act(11, "GitCommit", "commit: xstate auth machine", "Land the verified machine.",
            inputs=["a7"], detail="git commit -m 'auth: explicit state machine (reachability proved)'"),
    ]
    artifacts = [
        art("a1", "SourceCode", "machine.ts (booleans)", 1),
        art("a2", "AnalysisNote", "impossible states admitted", 2, ["a1"]),
        art("a3", "IMLModel", "auth machine (IML)", 4, ["a2"], {
            "status": "proved", "src_lang": "typescript",
            "iml_code": "type state = LoggedOut | LoggingIn | Authenticated | Refreshing | Error | Locked | Expired\nlet step (s:state) (e:event) = ...",
            "symbols": ["step", "reaches"]}),
        art("a4", "VerificationGoal", "reachability goal", 5, ["a3"],
            vg_payload(1, "every state reachable; no orphan Authenticated", "a3", "step", props)),
        art("a5", "VerificationResult", "reachability proved", 6, ["a4"], {
            "goal_id": 1, "goal_artifact_id": "a4", "status": "proved", "engine": "imandrax", "result": proved(props)}),
        art("a6", "Decomposition", "transition regions", 7, ["a3"], {
            "target_artifact_id": "a3", "target_function": "step", "complete": True,
            "regions": [{"id": "e1", "constraint": "event = LOGIN"}, {"id": "e2", "constraint": "event = SUCCESS"},
                        {"id": "e3", "constraint": "event = FAILURE"}, {"id": "e4", "constraint": "event = REFRESH"},
                        {"id": "e5", "constraint": "event = LOGOUT"}]}),
        art("a7", "Diff", "machine.ts rewrite", 8, ["a5"]),
        art("a8", "GeneratedTests", "transition suite", 9, ["a6"], {
            "function": "step", "language": "typescript", "source_decomposition_artifact_id": "a6",
            "tests": [{"name": "test_login_transitions"}, {"name": "test_success_authenticates"},
                      {"name": "test_failure_to_error"}, {"name": "test_refresh_keeps_auth"}, {"name": "test_logout_resets"}]}),
        art("a9", "CommandResult", "vitest: 31 passed", 10, ["a8"]),
    ]
    metas = [
        {"id": "m1", "title": "Audit the ad-hoc auth state", "intent": "Find the impossible states the booleans allow",
         "action_ids": [1, 2], "source": "plan_declared", "status": "completed", "produced_artifact_ids": ["a1", "a2"]},
        {"id": "m2", "title": "Decide on an explicit machine", "intent": "XState vs reducer",
         "action_ids": [3], "source": "turn_segmented"},
        {"id": "m3", "title": "Prove reachability", "intent": "Every state reachable; no orphan Authenticated",
         "action_ids": [4, 5, 6, 7], "source": "plan_declared", "status": "completed",
         "produced_artifact_ids": ["a3", "a4", "a5", "a6"], "residual_ids": ["r1"]},
        {"id": "m4", "title": "Implement and test", "intent": "Swap in the machine, generate + run transition tests",
         "action_ids": [8, 9, 10], "source": "plan_declared", "status": "completed",
         "produced_artifact_ids": ["a7", "a8", "a9"]},
        {"id": "m5", "title": "Commit", "intent": "Land the verified machine", "action_ids": [11], "source": "turn_segmented"},
    ]
    policies = [
        pol("p1", "research_before_edit", "Every edit is preceded by research",
            "G(EditFile → P_target(ReadFile ∨ ReadDocumentation ∨ SearchCode ∨ AnalyzeCode))"),
        pol("p2", "all_decisions_justified", "Every decision records its rationale",
            "G(gateway → rationale ≠ ∅)"),
        pol("p3", "goals_reference_valid_artifacts", "Every verification goal targets a real IML model",
            "goals_reference_valid_artifacts", kind="structural", severity="error"),
        pol("p4", "generated_tests_require_decomposition", "Generated tests derive from a decomposition",
            "generated_tests_require_decomposition", kind="structural"),
    ]
    evals = [
        {"policy_id": "p1", "status": "passed", "note": "edit #8 preceded by read #1 / analyze #2"},
        {"policy_id": "p2", "status": "passed", "note": "decision #3 records its rationale"},
        {"policy_id": "p3", "status": "passed", "note": "VG a4 targets IML a3"},
        {"policy_id": "p4", "status": "passed", "note": "a8 derives from decomposition a6"},
    ]
    residuals = [
        {"residual_id": "r1", "kind": "limitation", "severity": "medium", "status": "acknowledged",
         "source": "agent_declared", "statement": "Reachability is proved for the modelled events only; deep-link entry points are not in the chart.",
         "target": {"target_type": "artifact", "target_id": "a3"},
         "suggested_check": "Enumerate router entry points and confirm each maps to a modelled state.", "introduced_by_action_id": 5},
        {"residual_id": "r2", "kind": "open_question", "severity": "low", "status": "open",
         "source": "agent_declared", "statement": "Should a token refresh failure log the user out or move to Error? Left as Error for now."},
    ]
    return assemble("trace-sample-auth-xstate",
                    "Migrate auth to an explicit state machine (reachability proved)",
                    "the auth booleans admit impossible states — model it as a machine and prove every state is reachable",
                    "Modelled auth as a 7-state machine, proved reachability + no orphan Authenticated, 31 transition tests pass.",
                    actions, metas, artifacts, policies, evals, residuals, ["src/auth/machine.ts"])


# ---------------------------------------------------------------------------
# Sample C — data pipeline: refactor with lineage + a conformance check
# ---------------------------------------------------------------------------
def sample_c():
    actions = [
        act(1, "ReadFile", "etl/transform.py", "Read the CSV transform before splitting it.", outputs=["a1"]),
        act(2, "SearchCode", "callers of transform_rows", "Find every caller so the refactor is safe.",
            cat="reasoning", inputs=["a1"], outputs=["a2"]),
        act(3, "ExclusiveDecision", "Streaming vs batch rewrite",
            "Batch fits in memory for current volumes; chose batch for simplicity, noted the limit.",
            cat="gateway",
            options=[{"label": "Batch (current)", "chosen": True},
                     {"label": "Streaming", "chosen": False, "rejected_because": "premature for current volumes"}]),
        act(4, "EditFile", "etl/transform.py", "Split transform_rows into parse / normalize / emit.",
            inputs=["a2"], outputs=["a3"], file_ref="etl/transform.py"),
        act(5, "Decompose", "Decompose transform by column type",
            "Region-split inputs by column dtype to generate conformance tests.", cat="reasoning",
            inputs=["a3"], outputs=["a4"]),
        act(6, "GenerateTests", "Generate conformance tests", "One golden-row test per column-type region.",
            inputs=["a4"], outputs=["a5"]),
        act(7, "RunTests", "pytest etl -q", "Run the conformance suite against golden fixtures.",
            inputs=["a5"], outputs=["a6"], result="40 passed", detail="pytest etl -q"),
        act(8, "GitCommit", "commit: split transform_rows", "Land the refactor with conformance coverage.",
            inputs=["a3"], detail="git commit -m 'etl: split transform_rows + conformance tests'"),
    ]
    artifacts = [
        art("a1", "SourceCode", "transform.py (monolith)", 1),
        art("a2", "AnalysisNote", "3 callers, all batch", 2, ["a1"]),
        art("a3", "Diff", "split transform_rows", 4, ["a2"]),
        art("a4", "Decomposition", "column-type regions", 5, ["a3"], {
            "target_artifact_id": "a3", "target_function": "transform_rows", "complete": True,
            "regions": [{"id": "c1", "constraint": "dtype = int"}, {"id": "c2", "constraint": "dtype = str"},
                        {"id": "c3", "constraint": "dtype = date"}, {"id": "c4", "constraint": "null"}]}),
        art("a5", "GeneratedTests", "conformance suite", 6, ["a4"], {
            "function": "transform_rows", "language": "python", "source_decomposition_artifact_id": "a4",
            "tests": [{"name": "test_int_columns"}, {"name": "test_str_columns"},
                      {"name": "test_date_columns"}, {"name": "test_nulls_passthrough"}]}),
        art("a6", "CommandResult", "pytest: 40 passed", 7, ["a5"]),
    ]
    metas = [
        {"id": "m1", "title": "Map the transform and its callers",
         "intent": "Refactor safely — know every caller", "action_ids": [1, 2],
         "source": "plan_declared", "status": "completed", "produced_artifact_ids": ["a1", "a2"]},
        {"id": "m2", "title": "Choose batch over streaming", "intent": "Scope the rewrite to current volumes",
         "action_ids": [3], "source": "turn_segmented", "residual_ids": ["r1"]},
        {"id": "m3", "title": "Refactor and cover with conformance tests",
         "intent": "Split the function, generate golden-row tests per column type",
         "action_ids": [4, 5, 6, 7], "source": "plan_declared", "status": "completed",
         "produced_artifact_ids": ["a3", "a4", "a5", "a6"]},
        {"id": "m4", "title": "Commit", "intent": "Land the refactor", "action_ids": [8], "source": "turn_segmented"},
    ]
    policies = [
        pol("p1", "research_before_edit", "Every edit is preceded by research",
            "G(EditFile → P_target(ReadFile ∨ ReadDocumentation ∨ SearchCode ∨ AnalyzeCode))"),
        pol("p2", "all_decisions_justified", "Every decision records its rationale",
            "G(gateway → rationale ≠ ∅)"),
        pol("p3", "data_flow_integrity", "Every consumed artifact has a producer", "data_flow_integrity",
            kind="structural", severity="error"),
        pol("p4", "generated_tests_require_decomposition", "Generated tests derive from a decomposition",
            "generated_tests_require_decomposition", kind="structural"),
    ]
    evals = [
        {"policy_id": "p1", "status": "passed", "note": "edit #4 preceded by read #1 / search #2"},
        {"policy_id": "p2", "status": "passed", "note": "decision #3 records its rationale"},
        {"policy_id": "p3", "status": "passed", "note": "DAG well-formed"},
        {"policy_id": "p4", "status": "passed", "note": "a5 derives from decomposition a4"},
    ]
    residuals = [
        {"residual_id": "r1", "kind": "limitation", "severity": "medium", "status": "acknowledged",
         "source": "agent_declared", "statement": "Batch transform assumes the file fits in memory; will need streaming above ~2GB.",
         "target": {"target_type": "action", "target_id": 3},
         "suggested_check": "Add a size guard that fails fast above the batch threshold.", "introduced_by_action_id": 3},
        {"residual_id": "r2", "kind": "unverified", "severity": "low", "status": "open",
         "source": "agent_declared", "statement": "Timezone handling for date columns relies on the fixtures' implicit UTC; not asserted.",
         "suggested_check": "Add a test with a non-UTC date column."},
    ]
    return assemble("trace-sample-etl-refactor",
                    "Refactor the CSV transform with conformance coverage",
                    "split the monolithic transform_rows and add tests so the refactor is safe",
                    "Split transform_rows into parse/normalize/emit, generated conformance tests per column type, 40 pass.",
                    actions, metas, artifacts, policies, evals, residuals, ["etl/transform.py"])


def main():
    samples = {"sample_payment_idempotency.json": sample_a(),
               "sample_auth_xstate.json": sample_b(),
               "sample_etl_refactor.json": sample_c()}
    for fname, trace in samples.items():
        path = os.path.join(HERE, fname)
        with open(path, "w") as f:
            f.write(json.dumps(trace, indent=2) + "\n")
        print(f"wrote {fname}  ({len(trace['actions'])} actions, {len(trace['meta_actions'])} meta-actions, "
              f"{len(trace['artifacts'])} artifacts)")


if __name__ == "__main__":
    main()

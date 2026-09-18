"""`ponens trace next`: the ordered to-do list the enriched trace implies."""
import copy
from ponens import goals as G
from ponens import trace as T

REF = "ref:gallery:stripe/refunds@2024-06-20"


def _trace():
    t = T.create_empty_trace(model="m", assistant="t")
    t["reference_artifacts"] = [{"reference_artifact_id": REF, "artifact_type": "RefFormalModel", "version": "2024-06-20", "payload": {"checksum": "c1"}}]
    t["actions"] = [{"id": 1, "type": "RunTests", "category": "activity", "rationale": "r", "inputs": [REF], "outputs": ["c1"]},
                    {"id": 2, "type": "RunTests", "category": "activity", "rationale": "r", "inputs": [REF], "outputs": ["c2"]}]
    t["artifacts"] = [
        {"artifact_id": "c1", "artifact_type": "ConformanceResult", "derived_from": [REF], "producer_action_id": 1,
         "payload": {"reference_artifact_id": REF, "target_symbol": "can_refund", "entry_symbol": "refund_allowed", "status": "passed", "evidence_strength": "tests",
                     "oracle": {"id": "codelogician", "oracle_type": "tester", "evidence_strength": "tests"}, "reference_version": "2024-06-20", "reference_checksum": "c1"}},
        {"artifact_id": "c2", "artifact_type": "ConformanceResult", "derived_from": [REF], "producer_action_id": 2,
         "payload": {"reference_artifact_id": "ref:gallery:stripe/idempotency@2024-06-20", "target_symbol": "replay_or_conflict", "entry_symbol": "idempotency_outcome", "status": "failed", "evidence_strength": "tests",
                     "oracle": {"id": "codelogician", "oracle_type": "tester", "evidence_strength": "tests"}}},
    ]
    t["reference_artifacts"].append({"reference_artifact_id": "ref:gallery:stripe/idempotency@2024-06-20", "artifact_type": "RefFormalModel", "version": "2024-06-20"})
    t["residuals"] = [
        {"residual_id": "d1", "kind": "defeater", "defeater_kind": "rebuts", "severity": "critical", "status": "open", "statement": "does NOT conform", "target": {"target_type": "artifact", "target_id": "c2"}, "related_artifact_ids": ["c2"]},
        {"residual_id": "q1", "kind": "open_question", "severity": "high", "status": "open", "statement": "is the JPY path reachable?", "suggested_check": "call to_minor_units with a zero-decimal currency"},
        {"residual_id": "q2", "kind": "assumption", "severity": "low", "status": "waived", "statement": "settled", "suggested_check": "nothing"},
        {"residual_id": "a1", "kind": "assumption", "severity": "medium", "status": "open", "statement": "ints are unbounded", "suggested_check": "bound them"},
        {"residual_id": "a2", "kind": "assumption", "severity": "high", "status": "open", "statement": "calendar is current", "suggested_check": "re-fetch the calendar"},
    ]
    item = lambda bid, ref: {"id": "binding:%s:project" % bid, "kind": "conformance", "label": "the project conforms to %s" % ref, "required": True,
                             "evidence": {"artifact": "ConformanceResult"}, "reference": ref, "binding": {}}
    t["goals"] = [
        {"id": "binding:stripe-refunds", "intent": "i", "scope": [], "status": "active", "acceptance": [item("stripe-refunds", REF)]},
        {"id": "binding:stripe-idempotency", "intent": "i", "scope": [], "status": "active", "acceptance": [item("stripe-idempotency", "ref:gallery:stripe/idempotency@2024-06-20")]},
        {"id": "binding:stripe-webhooks", "intent": "i", "scope": [], "status": "active", "acceptance": [item("stripe-webhooks", "ref:gallery:stripe/webhooks@2024-06-20")]},
        {"id": "nice-to-have", "intent": "i", "scope": [], "status": "active", "acceptance": [dict(item("x", "ref:gallery:stripe/subscriptions"), required=False)]},
    ]
    t["outcome"] = {"type": "ProcessCompleted"}
    return t


def test_next_steps_orders_fix_then_establish_then_gaps_then_optional():
    steps = G.next_steps(_trace())
    assert [(s["kind"], s["goal_id"] or s["item_id"]) for s in steps] == [
        ("fix", "binding:stripe-idempotency"),
        ("establish", "binding:stripe-webhooks"),
        ("gap", "a2"),          # a HIGH assumption demands discharge (same severity as q1: ordered by id); the medium one (a1) is a standing boundary, not a step
        ("gap", "q1"),
        ("optional", "nice-to-have"),
    ]
    fix = steps[0]
    assert fix["evidence_ref"] == "c2" and "re-establish conformance against ref:gallery:stripe/idempotency@2024-06-20" in fix["suggested"]
    assert steps[1]["suggested"].startswith("establish conformance against ref:gallery:stripe/webhooks")
    assert steps[3]["suggested"] == "call to_minor_units with a zero-decimal currency" and steps[3]["why"] == "open open_question (high)"
    assert G.next_steps(_trace(), limit=2)[-1]["kind"] == "establish"


def test_next_steps_refresh_when_the_reference_moved_and_nothing_when_all_done():
    t = _trace()
    t["reference_artifacts"][0]["version"] = "2025-01-01"          # the catalogue moved past what c1 recorded
    steps = G.next_steps(t)
    ref = [s for s in steps if s["kind"] == "refresh"]
    assert ref and ref[0]["goal_id"] == "binding:stripe-refunds" and "Re-establish conformance" in ref[0]["suggested"]
    done = _trace()
    done["goals"] = [done["goals"][0]]
    done["residuals"] = []
    assert G.next_steps(done) == []
    assert G.render_next([]).startswith("Nothing to do")
    text = G.render_next(G.next_steps(_trace()))
    assert text.splitlines()[0] == "1. [FIX] the project conforms to ref:gallery:stripe/idempotency@2024-06-20  (binding:stripe-idempotency)"
    assert "     do:  " in text

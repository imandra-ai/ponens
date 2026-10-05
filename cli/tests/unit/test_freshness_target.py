"""The legacy freshness heuristic - a later change naming a result's symbol makes it stale - reads a Diff's
`target_symbol` when it has one, not words in its name or path: an edit to `refund_fee` in `src/refunds/fees.py` does
not name a result about `refunds`. A change naming no declaration keeps the conservative match on its name."""

from ponens.goals import stale_evidence


def _trace(diff):
    return {"trace_id": "t", "artifacts": [
        {"artifact_id": "vg1", "artifact_type": "VerificationGoal", "producer_action_id": 1, "payload": {"goal_id": "G", "target_symbol": "refunds", "description": "never refunds twice"}},
        {"artifact_id": "vr1", "artifact_type": "VerificationResult", "producer_action_id": 2, "derived_from": ["vg1"],
         "payload": {"goal_id": "G", "goal_artifact_id": "vg1", "status": "proved", "target_symbol": "refunds"}},
        {**diff, "artifact_type": "Diff", "producer_action_id": 3}]}


def _stale(trace):
    return [r["target"]["target_id"] for r in stale_evidence(trace) if r["kind"] == "stale_evidence"]


def test_a_targeted_edit_to_another_declaration_in_a_like_named_path_is_not_a_change_to_the_result():
    assert _stale(_trace({"artifact_id": "d1", "name": "Edit src/refunds/fees.py", "payload": {"file": "src/refunds/fees.py", "target_symbol": "refund_fee"}})) == []


def test_a_targeted_edit_to_the_result_s_own_symbol_is():
    assert _stale(_trace({"artifact_id": "d1", "name": "Edit src/x.py", "payload": {"file": "src/x.py", "target_symbol": "refunds"}})) == ["vr1"]


def test_an_untargeted_edit_keeps_the_conservative_match_on_its_name():
    assert _stale(_trace({"artifact_id": "d1", "name": "Edit src/refunds/fees.py", "payload": {"file": "src/refunds/fees.py"}})) == ["vr1"]

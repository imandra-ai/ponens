"""Goal resolution on a LIVE-shaped trace.

The reference-fixture test proves enrich resolves a hand-authored goal. This proves the SAME thing
for a trace shaped exactly as the CodeLogician exporter (`toPonensTrace`) emits it -- an IMLModel,
a VerificationGoal carrying `target_symbol`, and a VerificationResult deriving from it -- so a
`declare_goal` property item bound to that symbol resolves to its ImandraX verdict end to end.
"""
from ponens.goals import enrich


def _live_trace(vr_status, goal):
    """A minimal trace in the exporter's exact shape: Formalize -> DefineVG -> Verify for `refund`."""
    return {
        "trace_id": "fr-live",
        "spec_version": "1.1",
        "trigger": {"type": "TaskReceived", "description": "verify refund"},
        "outcome": {"type": "ProcessCompleted", "summary": "done"},
        "actions": [
            {"id": 1, "type": "Formalize", "rationale": "formalize", "inputs": [], "outputs": ["fr1-model"]},
            {"id": 2, "type": "DefineVG", "rationale": "goal", "inputs": ["fr1-model"], "outputs": ["fr1-goal-1"]},
            {"id": 3, "type": "Verify", "rationale": "verify", "inputs": ["fr1-goal-1"], "outputs": ["fr1-result-1"]},
        ],
        "artifacts": [
            {"artifact_id": "fr1-model", "artifact_type": "IMLModel", "producer_action_id": 1, "derived_from": [],
             "payload": {"symbols": ["refund"]}},
            {"artifact_id": "fr1-goal-1", "artifact_type": "VerificationGoal", "producer_action_id": 2,
             "derived_from": ["fr1-model"],
             "payload": {"goal_id": 1, "kind": "verify", "description": "amount invariant",
                         "target_artifact_id": "fr1-model", "target_symbol": "refund"}},
            {"artifact_id": "fr1-result-1", "artifact_type": "VerificationResult", "producer_action_id": 3,
             "derived_from": ["fr1-goal-1"],
             "payload": {"goal_id": 1, "goal_artifact_id": "fr1-goal-1", "status": vr_status, "engine": "imandrax"}},
        ],
        "residuals": [],
        "policies": [],
        "policy_evaluations": [],
        "goals": [goal],
    }


def _goal(status="todo"):
    return {
        "id": "session-goal",
        "intent": "Harden the refund flow",
        "scope": ["refund"],
        "status": "active",
        "acceptance": [
            {"id": "s1", "kind": "property", "label": "amount invariant holds",
             "binding": {"symbol": "refund", "property": "amount"}, "status": status, "required": True},
        ],
    }


def test_property_item_resolves_to_the_proved_result():
    e = enrich(_live_trace("proved", _goal()))
    g = e["goals"][0]
    s1 = g["acceptance"][0]
    assert s1["status"] == "done"
    assert s1["evidence"] == "fr1-result-1"   # bound to the actual ImandraX result
    assert g["progress"] == 1.0
    assert g["open_gaps"] == 0


def test_refuted_property_reads_blocked():
    e = enrich(_live_trace("refuted", _goal()))
    s1 = e["goals"][0]["acceptance"][0]
    assert s1["status"] == "blocked"          # evidence overrides the authored 'todo'
    assert e["goals"][0]["progress"] == 0.0


def test_authored_status_is_overridden_by_evidence():
    # Authored 'done' but the engine refuted -> enrich re-resolves to blocked (evidence decides).
    e = enrich(_live_trace("refuted", _goal(status="done")))
    assert e["goals"][0]["acceptance"][0]["status"] == "blocked"


def test_property_only_binding_resolves_without_target_symbol():
    """The ACTUAL live path: check_vg-recorded goals carry no target_symbol, only a rich description
    (e.g. 'amount_inv_preserved'). A property item bound by keyword alone still resolves."""
    tr = _live_trace("proved", {
        "id": "sg", "intent": "x", "scope": [], "status": "active",
        "acceptance": [{"id": "s1", "kind": "property", "label": "amount",
                        "binding": {"property": "amount"}, "status": "todo", "required": True}],
    })
    # Drop target_symbol and give the exporter's real description shape.
    vg = next(a for a in tr["artifacts"] if a["artifact_type"] == "VerificationGoal")
    vg["payload"].pop("target_symbol", None)
    vg["payload"]["description"] = "fun o a -> amount_inv_preserved o a"
    e = enrich(tr)
    s1 = e["goals"][0]["acceptance"][0]
    assert s1["status"] == "done"
    assert s1["evidence"] == "fr1-result-1"


def test_symbol_plus_property_still_resolves_when_target_symbol_absent():
    """The exact live failure: the agent bound {symbol:'refund', property:'amount'} but the check_vg
    goal has no target_symbol and description 'amount_inv'. The symbol must not disqualify the match
    when there is no target_symbol to check -- the property keyword pins it."""
    tr = _live_trace("proved", {
        "id": "sg", "intent": "x", "scope": [], "status": "active",
        "acceptance": [{"id": "s1", "kind": "property", "label": "amount",
                        "binding": {"symbol": "refund", "property": "amount"}, "status": "todo", "required": True}],
    })
    vg = next(a for a in tr["artifacts"] if a["artifact_type"] == "VerificationGoal")
    vg["payload"].pop("target_symbol", None)
    vg["payload"]["description"] = "amount_inv"
    assert enrich(tr)["goals"][0]["acceptance"][0]["status"] == "done"

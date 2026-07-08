"""Unit tests for goal operations over a trace (ponens.goals)."""

from ponens.goals import (
    resolve_item, progress_of, stale_evidence,
    goal_relevant_actions, unattributed_actions, goal_residuals, enrich,
)


def _trace():
    # A tiny trace: a property proved (vr1, from vg1), then a LATER edit to `foo` (d1) -> stale.
    return {
        "trace_id": "t",
        "actions": [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 9}],
        "artifacts": [
            {"artifact_id": "vg1", "artifact_type": "VerificationGoal", "producer_action_id": 1,
             "payload": {"goal_id": "G1", "target_symbol": "foo", "description": "amount invariant holds"}},
            {"artifact_id": "vr1", "artifact_type": "VerificationResult", "producer_action_id": 2,
             "derived_from": ["vg1"], "payload": {"goal_id": "G1", "goal_artifact_id": "vg1", "status": "proved"}},
            {"artifact_id": "d1", "artifact_type": "Diff", "producer_action_id": 3,
             "name": "edit foo", "summary": "changed foo"},
        ],
        "residuals": [{"residual_id": "r1", "status": "open", "severity": "high", "statement": "gap about foo"}],
        "policy_evaluations": [{"policy_id": "p1", "status": "passed"}],
        "goals": [{
            "id": "g", "intent": "do foo", "scope": ["foo"], "status": "active",
            "acceptance": [
                {"id": "a1", "kind": "property", "label": "amount", "status": "todo", "binding": {"property": "amount"}},
                {"id": "a2", "kind": "change", "label": "edit foo", "status": "todo", "binding": {"symbol": "foo"}},
                {"id": "a3", "kind": "gap", "label": "gap", "status": "todo", "binding": {"residual_id": "r1"}},
                {"id": "a4", "kind": "obligation", "label": "pol", "status": "todo", "binding": {"policy_id": "p1"}},
            ],
        }],
    }


def test_resolve_each_kind():
    t = _trace()
    items = {i["id"]: i for i in t["goals"][0]["acceptance"]}
    assert resolve_item(items["a1"], t)["status"] == "done"    # property proved
    assert resolve_item(items["a2"], t)["status"] == "done"    # change touched foo
    assert resolve_item(items["a3"], t)["status"] == "todo"    # gap residual still open
    assert resolve_item(items["a4"], t)["status"] == "done"    # obligation policy passed


def test_resolve_property_latest_result_wins():
    t = _trace()
    # add a LATER refuted result for the same goal -> latest wins, but here proved is at step 2;
    # add an even-later proved to confirm ordering picks the newest proved
    t["artifacts"].append({"artifact_id": "vr2", "artifact_type": "VerificationResult",
                           "producer_action_id": 8, "payload": {"goal_id": "G1", "goal_artifact_id": "vg1",
                                                                 "status": "refuted"}})
    item = t["goals"][0]["acceptance"][0]
    # newest result (step 8) is refuted -> blocked
    assert resolve_item(item, t)["status"] == "blocked"


def test_resolve_unbound_falls_back():
    t = _trace()
    r = resolve_item({"id": "x", "kind": "property", "status": "doing"}, t)  # no binding
    assert r == {"status": "doing", "from_trace": False, "evidence": None}


def test_progress():
    # a1 done, a2 done, a3 todo, a4 done -> 3/4
    t = _trace()
    items = [dict(i, status=resolve_item(i, t)["status"]) for i in t["goals"][0]["acceptance"]]
    assert progress_of(items) == 0.75


def test_stale_evidence_fires_on_later_edit():
    t = _trace()
    stale = stale_evidence(t)
    assert len(stale) == 1
    assert stale[0]["residual_id"] == "stale-vr1"
    assert stale[0]["derived"] is True
    assert stale[0]["target"]["target_id"] == "vr1"


def test_stale_evidence_none_when_no_later_edit():
    t = _trace()
    t["artifacts"][2]["producer_action_id"] = 1  # move the edit BEFORE the proof (step 2)
    assert stale_evidence(t) == []


def test_relevance_cone_and_exploration():
    t = _trace()
    cone = goal_relevant_actions(t["goals"][0], t)
    assert cone == {1, 2, 3}          # vg1(1), vr1(2), d1(3) via seeds + lineage
    assert unattributed_actions(t) == {9}  # action 9 produced nothing on-goal


def test_goal_residuals_declared_plus_derived():
    t = _trace()
    rs = goal_residuals(t["goals"][0], t)
    ids = {r["residual_id"] for r in rs}
    assert "r1" in ids and "stale-vr1" in ids  # declared (bound) + derived (in scope)


def test_enrich_end_to_end():
    t = _trace()
    e = enrich(t)
    g = e["goals"][0]
    assert g["progress"] == 0.75
    assert g["cone"] == [1, 2, 3]
    assert g["open_gaps"] == 2                      # r1 + stale-vr1
    assert e["exploration_actions"] == [9]
    assert any(r.get("derived") for r in e["residuals"])   # stale merged in
    assert e["summary"] == {"policy_violations": 0, "open_residuals": 2, "open_high": 1, "stale_evidence": 1}
    assert {i["id"]: i["status"] for i in g["acceptance"]} == {
        "a1": "done", "a2": "done", "a3": "todo", "a4": "done"}
    # source trace untouched
    assert "progress" not in t["goals"][0]

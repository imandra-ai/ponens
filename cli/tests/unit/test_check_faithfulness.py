"""The faithfulness gate in `ponens trace check` (_faithfulness_findings)."""

from ponens.trace import _faithfulness_findings


def _trace(goal):
    return {"trace_id": "t", "actions": [], "artifacts": [], "residuals": [], "goals": [goal]}


def test_no_goals_no_findings():
    assert _faithfulness_findings({"trace_id": "t"}) == ([], [], [])


def test_strong_certified_goal_has_no_fails():
    # a proved property, covering the sole clause, approved by a non-doer -> certified, no findings
    goal = {
        "id": "g", "intent": "i", "scope": [], "intent_clauses": ["c"],
        "criteria_review": {"reviewed_by": "reviewer", "verdict": "approved"},
        "acceptance": [{"id": "s1", "kind": "property", "label": "p", "status": "done",
                        "author": "agent", "covers": ["c"], "binding": {}}],
    }
    fails, warns, rows = _faithfulness_findings(_trace(goal))
    assert fails == [] and warns == []
    assert rows == ["    g: met, certified"]


def test_weak_and_uncovered_goal_produces_fails():
    goal = {
        "id": "g", "intent": "i", "scope": [], "intent_clauses": ["do X", "do Y"],
        "acceptance": [{"id": "s1", "kind": "change", "label": "edit", "status": "done",
                        "author": "agent", "covers": ["do X"], "binding": {}}],
    }
    fails, warns, rows = _faithfulness_findings(_trace(goal))
    # weakly specified (only a change) + one uncovered clause -> two gating failures
    assert any("weakly specified" in f for f in fails)
    assert any("do Y" in f for f in fails)
    assert len(fails) == 2
    # met but not certified -> an informational warning, never a hard failure
    assert any("not certified" in w for w in warns)
    assert rows == ["    g: met, uncertified"]

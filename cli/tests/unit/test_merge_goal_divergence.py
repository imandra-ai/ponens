"""The objective is the one thing a merge must not settle on a person's behalf.

Before this layer, `combine()` deep-copied OURS and overlaid only model artifacts, so a branch that
TIGHTENED a goal - broadened the intent, added a required criterion - had the tightening silently
discarded, and a goal the incoming branch introduced vanished. No residual, no report line: the
totality invariant covers `result_id` only, so nothing caught it.

The rule these tests pin is deliberately narrow. A field only ONE side moved is taken (that is what a
three-way merge IS). A goal only THEIRS has is taken (adding an obligation is the safe direction, and
dropping it is the data loss). A field BOTH sides moved differently is a conflict: the merge records
both readings, marks the goal contested and opens a residual - and picks nothing.
"""

import pytest

from ponens.merge import merge, combine, _goal_divergences


SRC = "let f x = x + 1"


def _trace(tid, goals):
    return {"trace_id": tid, "goals": goals,
            "artifacts": [{"artifact_id": "m1", "artifact_type": "IMLModel",
                           "producer_action_id": 1, "payload": {"iml_code": SRC}}],
            "actions": [{"id": 1, "type": "Formalize", "category": "reasoning", "label": "f"}]}


def _goal(intent="stay within the ceiling", acceptance=None, gid="g1", **kw):
    g = {"id": gid, "intent": intent, "status": "active", "scope": ["exposure.py"],
         "acceptance": acceptance if acceptance is not None else [
             {"id": "a1", "kind": "property", "label": "never exceeds", "required": True, "status": "done"}]}
    g.update(kw)
    return g


def _merged(ours_goals, theirs_goals, base_goals):
    return combine(_trace("o", ours_goals), _trace("t", theirs_goals), base=_trace("b", base_goals))


def _goal_of(trace, gid="g1"):
    return next(g for g in trace["goals"] if g["id"] == gid)


def _divergence_residuals(trace):
    return [r for r in trace.get("residuals") or [] if r.get("kind") == "goal_divergence"]


# ---- the silent-loss cases the layer exists to stop ------------------------

def test_a_goal_only_theirs_declares_is_not_dropped():
    m = _merged([_goal()], [_goal(), _goal(gid="g2", intent="refunds never exceed the charge")], [_goal()])
    assert {g["id"] for g in m["goals"]} == {"g1", "g2"}


def test_a_criterion_only_theirs_added_is_taken():
    theirs = _goal(acceptance=[
        {"id": "a1", "kind": "property", "label": "never exceeds", "required": True, "status": "done"},
        {"id": "a2", "kind": "property", "label": "never negative", "required": True, "status": "todo"}])
    m = _merged([_goal()], [theirs], [_goal()])
    assert [a["id"] for a in _goal_of(m)["acceptance"]] == ["a1", "a2"]
    # Only one side moved it, so this is not a conflict and nothing is asked of a person.
    assert _divergence_residuals(m) == []


def test_a_field_only_theirs_moved_is_taken_not_contested():
    m = _merged([_goal()], [_goal(intent="stay within the ceiling AND never negative")], [_goal()])
    assert _goal_of(m)["intent"] == "stay within the ceiling AND never negative"
    assert "contested" not in _goal_of(m)


def test_a_field_only_ours_moved_keeps_ours():
    m = _merged([_goal(intent="ours wording")], [_goal()], [_goal()])
    assert _goal_of(m)["intent"] == "ours wording"
    assert _divergence_residuals(m) == []


# ---- the conflict: the merge declines ------------------------------------

def test_both_sides_moved_the_same_field_is_a_conflict_and_nothing_is_chosen():
    m = _merged([_goal(intent="ours wording")], [_goal(intent="theirs wording")], [_goal()])
    g = _goal_of(m)
    # Ours stands as the PLACEHOLDER - not as a winner. Both readings are on the goal.
    assert g["intent"] == "ours wording"
    contested = g["contested"]
    assert [c["field"] for c in contested] == ["intent"]
    assert contested[0]["ours"] == "ours wording"
    assert contested[0]["theirs"] == "theirs wording"


def test_the_conflict_opens_a_residual_that_names_the_way_out():
    m = _merged([_goal(intent="ours wording")], [_goal(intent="theirs wording")], [_goal()])
    (r,) = _divergence_residuals(m)
    assert r["status"] == "open" and r["severity"] == "high"
    assert r["goal_id"] == "g1"
    assert "did not choose" in r["statement"]
    # An open obligation with no way to discharge it is a complaint, not a finding.
    assert "goal resolve" in r["suggested_check"]
    assert r["residual_id"] == _goal_of(m)["contested"][0]["residual_id"]


def test_no_base_means_the_merge_cannot_attribute_the_change_so_it_asks():
    # Without a common ancestor there is no way to tell who moved the field. Guessing here is exactly
    # the silent choice this layer exists to prevent.
    m = combine(_trace("o", [_goal(intent="ours")]), _trace("t", [_goal(intent="theirs")]))
    assert [c["field"] for c in _goal_of(m)["contested"]] == ["intent"]


def test_identical_edits_on_both_sides_are_not_a_conflict():
    same = "both branches wrote exactly this"
    m = _merged([_goal(intent=same)], [_goal(intent=same)], [_goal()])
    assert _goal_of(m)["intent"] == same
    assert _divergence_residuals(m) == []


# ---- the report channel ---------------------------------------------------

def test_the_report_carries_the_divergences_separately_from_results():
    rep = merge(_trace("o", [_goal(intent="ours")]), _trace("t", [_goal(intent="theirs")]),
                base=_trace("b", [_goal()]))
    (d,) = [x for x in rep["goal_divergences"] if x.get("kind") == "conflict"]
    assert d["goal_id"] == "g1" and d["field"] == "intent" and d["resolution_required"] is True


def test_resolved_fields_never_conflict():
    # status/progress/evidence are the resolver's projection, recomputed by enrich - only the
    # AUTHORED layer is a person's to reconcile.
    ours = _goal(); ours["progress"] = 0.5; ours["status"] = "active"
    theirs = _goal(); theirs["progress"] = 1.0; theirs["status"] = "done"
    m = _merged([ours], [theirs], [_goal()])
    assert "contested" not in _goal_of(m)


def test_a_trace_with_no_goals_is_unaffected():
    m = combine(_trace("o", []), _trace("t", []), base=_trace("b", []))
    assert _divergence_residuals(m) == []


# ---- the invariant the marker is for -------------------------------------

def test_a_contested_goal_cannot_be_reported_met():
    from ponens.goals import faithfulness_of
    g = _goal(acceptance=[{"id": "a1", "kind": "property", "label": "x", "required": True, "status": "done"}])
    assert faithfulness_of(g)["met"] is True
    g["contested"] = [{"field": "intent", "ours": "a", "theirs": "b", "residual_id": "r1"}]
    # Every criterion still resolves done - but under WHICH definition of done? Nobody has said.
    assert faithfulness_of(g)["met"] is False
    assert faithfulness_of(g)["contested_fields"] == ["intent"]

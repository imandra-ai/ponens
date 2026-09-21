"""Unit tests for `ponens trace goal` (set / accept / certify / ls) -- CLI parity with the desktop."""

import json
import types

from ponens.trace import cmd_goal_set, cmd_goal_accept, cmd_goal_certify, cmd_goal_ls


def _trace(tmp_path):
    f = tmp_path / "t.json"
    f.write_text(json.dumps({
        "trace_id": "t", "spec_version": "1.6", "assistant": "x", "model": "m",
        "timestamp": "2026-01-01T00:00:00Z", "trigger": {"type": "TaskReceived", "description": "d"},
        "actions": [], "artifacts": [], "outcome": {"type": "ProcessCompleted", "summary": "ok"},
    }))
    return f


def _goal(f):
    return json.loads(f.read_text())["goals"][0]


def _set_args(f, **kw):
    base = dict(trace_file=str(f), intent=None, scope=None, clause=None,
               intent_author="human", id="session-goal", json=None, reason=None, by=None)
    base.update(kw)
    return types.SimpleNamespace(**base)


def _accept_args(f, **kw):
    base = dict(trace_file=str(f), goal="session-goal", kind="change", label="l", symbol=None,
               property=None, policy_id=None, residual_id=None, file=None, covers=None,
               optional=False, author="agent", id=None)
    base.update(kw)
    return types.SimpleNamespace(**base)


def test_set_creates_snake_case_goal(tmp_path):
    f = _trace(tmp_path)
    assert cmd_goal_set(_set_args(f, intent="harden refund", scope="pay.py,refund",
                                  clause=["no over-refund", "amount invariant"])) == 0
    g = _goal(f)
    assert g["id"] == "session-goal" and g["intent"] == "harden refund"
    assert g["scope"] == ["pay.py", "refund"]
    assert g["intent_author"] == "human"                 # snake_case on the wire
    assert g["intent_clauses"] == ["no over-refund", "amount invariant"]
    assert g["acceptance"] == []
    # goals bump the trace to §18 / 1.7
    assert json.loads(f.read_text())["spec_version"] == "1.7"


def test_set_requires_intent_or_json(tmp_path):
    f = _trace(tmp_path)
    assert cmd_goal_set(_set_args(f)) == 1  # no intent, no --json


def test_accept_assigns_ids_and_binding(tmp_path):
    f = _trace(tmp_path)
    cmd_goal_set(_set_args(f, intent="i"))
    cmd_goal_accept(_accept_args(f, kind="property", label="proved", symbol="refund",
                                 property="amount", covers=["c1"]))
    cmd_goal_accept(_accept_args(f, kind="change", label="edited", symbol="refund", optional=True))
    acc = _goal(f)["acceptance"]
    assert [a["id"] for a in acc] == ["s1", "s2"]
    assert acc[0] == {"id": "s1", "kind": "property", "label": "proved",
                      "binding": {"symbol": "refund", "property": "amount"}, "status": "todo",
                      "required": True, "author": "agent", "authored_at": acc[0]["authored_at"],
                      "covers": ["c1"]}
    assert acc[1]["required"] is False           # --optional
    assert "authored_at" in acc[1]               # stamped


def test_accept_without_goal_errors(tmp_path):
    f = _trace(tmp_path)
    assert cmd_goal_accept(_accept_args(f, kind="change", label="l")) == 1


def test_certify_records_review_snake_case(tmp_path):
    f = _trace(tmp_path)
    cmd_goal_set(_set_args(f, intent="i"))
    args = types.SimpleNamespace(trace_file=str(f), goal="session-goal", by="reviewer",
                                 verdict="approved", note="faithful")
    assert cmd_goal_certify(args) == 0
    review = _goal(f)["criteria_review"]
    assert review["reviewed_by"] == "reviewer" and review["verdict"] == "approved"
    assert review["note"] == "faithful" and "at" in review


def test_ls_reports_met_vs_certified(tmp_path, capsys):
    f = _trace(tmp_path)
    cmd_goal_set(_set_args(f, intent="i", clause=["c1"]))
    cmd_goal_accept(_accept_args(f, kind="property", label="p", symbol="x", covers=["c1"]))
    cmd_goal_certify(types.SimpleNamespace(trace_file=str(f), goal="session-goal", by="reviewer",
                                           verdict="approved", note=None))
    cmd_goal_ls(types.SimpleNamespace(trace_file=str(f)))
    out = capsys.readouterr().out
    # definition is certified (non-doer approved, clause covered, has a property) but not met (todo)
    assert "CERTIFIED" in out and "not met" in out


def test_drop_withdraws_the_item_and_records_what_it_was(tmp_path):
    # Narrowing the bar is the one edit that makes a goal read met when it is not: delete the criteria
    # you have not met and progress goes to 100%. So the item leaves the definition of done and stays
    # in the record, with who withdrew it and why.
    from ponens import lineage
    f = _trace(tmp_path)
    cmd_goal_set(_set_args(f, intent="i"))
    cmd_goal_accept(_accept_args(f, label="a"))
    cmd_goal_accept(_accept_args(f, label="b"))
    args = types.SimpleNamespace(trace_file=str(f), goal="session-goal", item_id="s1",
                                 reason="duplicated by s2", by="eng-lead")
    from ponens.trace import cmd_goal_drop
    assert cmd_goal_drop(args) == 0
    assert [a["id"] for a in _goal(f)["acceptance"]] == ["s2"]

    t = json.loads(f.read_text())
    am = lineage.amendments_of(t, "session-goal")
    assert len(am) == 1
    assert am[0]["change"] == "item_withdrawn"
    assert am[0]["item_id"] == "s1"
    assert am[0]["reason"] == "duplicated by s2"
    assert am[0]["by"] == "eng-lead"
    assert am[0]["was"]["label"] == "a", "the criterion is kept verbatim, not merely named"
    act = next(a for a in t["actions"] if a["id"] == am[0]["action_id"])
    assert act["type"] == "Decision" and act["rationale"] == "duplicated by s2"

    args.item_id = "nope"
    assert cmd_goal_drop(args) == 1  # unknown item


def test_rm_withdraws_the_goal_and_keeps_what_it_asked_for(tmp_path):
    from ponens import lineage
    f = _trace(tmp_path)
    cmd_goal_set(_set_args(f, intent="i"))
    cmd_goal_accept(_accept_args(f, label="a"))
    from ponens.trace import cmd_goal_rm
    args = types.SimpleNamespace(trace_file=str(f), goal="session-goal",
                                 reason="superseded by the binding goals", by=None)
    assert cmd_goal_rm(args) == 0
    t = json.loads(f.read_text())
    assert t["goals"] == []
    am = lineage.amendments_of(t, "session-goal")
    assert am[0]["change"] == "goal_withdrawn"
    assert am[0]["was"]["intent"] == "i"
    assert [x["label"] for x in am[0]["was"]["acceptance"]] == ["a"]
    assert cmd_goal_rm(args) == 1  # already gone


def test_replacing_a_goal_needs_a_reason_and_keeps_the_previous_definition(tmp_path):
    from ponens import lineage
    f = _trace(tmp_path)
    cmd_goal_set(_set_args(f, intent="first"))
    cmd_goal_accept(_accept_args(f, label="a"))
    # Replacing without saying why is refused, and nothing is written.
    before = f.read_text()
    assert cmd_goal_set(_set_args(f, intent="second")) == 1
    assert f.read_text() == before
    assert cmd_goal_set(_set_args(f, intent="second", reason="scope changed after review")) == 0
    t = json.loads(f.read_text())
    assert _goal(f)["intent"] == "second"
    am = lineage.amendments_of(t, "session-goal")
    assert am[0]["change"] == "goal_replaced"
    assert am[0]["was"]["intent"] == "first"
    assert [x["label"] for x in am[0]["was"]["acceptance"]] == ["a"]


def test_a_second_criteria_review_supersedes_rather_than_erases(tmp_path):
    # A `changes-requested` verdict overwritten by an `approved` one used to leave nothing behind.
    from ponens import lineage
    from ponens.trace import cmd_goal_certify
    f = _trace(tmp_path)
    cmd_goal_set(_set_args(f, intent="i"))
    a = lambda v, note: types.SimpleNamespace(trace_file=str(f), goal="session-goal", by="reviewer",
                                              verdict=v, note=note)
    assert cmd_goal_certify(a("changes-requested", "the bar is too low")) == 0
    assert cmd_goal_certify(a("approved", "raised after discussion")) == 0
    t = json.loads(f.read_text())
    assert _goal(f)["criteria_review"]["verdict"] == "approved"      # current review, where consumers read it
    am = [x for x in lineage.amendments_of(t, "session-goal") if x["change"] == "criteria_reviewed"]
    assert len(am) == 2
    assert am[1]["was"]["verdict"] == "changes-requested", "the superseded verdict is still readable"


def test_roundtrip_author_enrich_check(tmp_path):
    """End-to-end contract: author a goal entirely via the CLI, `enrich` resolves each criterion from
    the trace's OWN evidence, faithfulness grades it, and the gate passes — authoring → resolution →
    gating in one flow, no hand-set statuses."""
    import copy
    from ponens.goals import enrich
    from ponens.trace import _faithfulness_findings
    f = tmp_path / "t.json"
    f.write_text(json.dumps({
        "trace_id": "t", "spec_version": "1.6", "assistant": "x", "model": "m",
        "timestamp": "2026-01-01T00:00:00Z", "trigger": {"type": "TaskReceived", "description": "d"},
        "actions": [{"id": 1, "type": "EditFile"}],
        "artifacts": [{"artifact_id": "d1", "artifact_type": "Diff", "producer_action_id": 1,
                       "name": "edit foo", "summary": "changed foo"}],
        "policies": [{"policy_id": "p1", "name": "tests_pass"}],
        "policy_evaluations": [{"policy_id": "p1", "status": "passed"}],
        "outcome": {"type": "ProcessCompleted", "summary": "ok"},
    }))
    cmd_goal_set(_set_args(f, intent="do foo", clause=["change foo", "policy passes"]))
    cmd_goal_accept(_accept_args(f, kind="change", label="edited foo", symbol="foo", covers=["change foo"]))
    cmd_goal_accept(_accept_args(f, kind="obligation", label="policy passes", policy_id="p1", covers=["policy passes"]))
    cmd_goal_certify(types.SimpleNamespace(trace_file=str(f), goal="session-goal", by="reviewer",
                                           verdict="approved", note=None))
    trace = json.loads(f.read_text())
    e = enrich(copy.deepcopy(trace))
    g = e["goals"][0]
    # both items resolved from evidence — NOT the todo we authored
    assert {a["id"]: a["status"] for a in g["acceptance"]} == {"s1": "done", "s2": "done"}
    assert g["acceptance"][0]["evidence"] == "d1" and g["acceptance"][1]["evidence"] == "p1"
    fa = g["faithfulness"]
    assert fa["met"] and fa["certified"] and fa["uncovered_clauses"] == []
    # the faithfulness gate passes cleanly (no goal-scoped policies → governed reads "no policy")
    fails, warns, rows = _faithfulness_findings(trace)
    assert fails == [] and rows == ["    session-goal: met, no policy, certified"]

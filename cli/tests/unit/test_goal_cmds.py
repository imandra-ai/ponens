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
               intent_author="human", id="session-goal", json=None)
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


def test_drop_removes_acceptance_item(tmp_path):
    f = _trace(tmp_path)
    cmd_goal_set(_set_args(f, intent="i"))
    cmd_goal_accept(_accept_args(f, label="a"))
    cmd_goal_accept(_accept_args(f, label="b"))
    args = types.SimpleNamespace(trace_file=str(f), goal="session-goal", item_id="s1")
    from ponens.trace import cmd_goal_drop
    assert cmd_goal_drop(args) == 0
    assert [a["id"] for a in _goal(f)["acceptance"]] == ["s2"]
    args.item_id = "nope"
    assert cmd_goal_drop(args) == 1  # unknown item


def test_rm_removes_goal(tmp_path):
    f = _trace(tmp_path)
    cmd_goal_set(_set_args(f, intent="i"))
    from ponens.trace import cmd_goal_rm
    args = types.SimpleNamespace(trace_file=str(f), goal="session-goal")
    assert cmd_goal_rm(args) == 0
    assert json.loads(f.read_text())["goals"] == []
    assert cmd_goal_rm(args) == 1  # already gone

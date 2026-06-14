"""Unit tests for trace structural validation (#6)."""

import json
import types

import pytest

from ponens.trace import validate_trace, cmd_check, cmd_validate, load_trace


def _trace(**over):
    t = {"trace_id": "t", "actions": [], "artifacts": [],
         "trigger": {"type": "TaskReceived"}, "outcome": {"type": "ProcessCompleted"}}
    t.update(over)
    return t


# --- meta-action overlay (§8.4) --------------------------------------------

def _meta_trace(metas, action_ids=(1, 2, 3)):
    acts = [{"id": i, "type": "EditFile", "rationale": "r" * 30} for i in action_ids]
    return _trace(actions=acts, meta_actions=metas)


def test_valid_meta_actions_no_errors():
    t = _meta_trace([{"id": "m1", "title": "x", "action_ids": [1, 2], "source": "turn_segmented"},
                     {"id": "m2", "title": "y", "action_ids": [3], "source": "plan_declared", "status": "completed"}])
    t["actions"][0]["meta_action_id"] = "m1"
    t["actions"][1]["meta_action_id"] = "m1"
    t["actions"][2]["meta_action_id"] = "m2"
    assert validate_trace(t)[0] == []


def test_meta_action_dangling_action_id():
    errs = validate_trace(_meta_trace([{"id": "m1", "action_ids": [1, 99]}]))[0]
    assert any("99 does not exist" in e for e in errs)


def test_meta_action_overlap_is_error():
    errs = validate_trace(_meta_trace([{"id": "m1", "action_ids": [1, 2]},
                                       {"id": "m2", "action_ids": [2, 3]}]))[0]
    assert any("two meta-actions" in e for e in errs)


def test_meta_action_invalid_source_and_status():
    errs = validate_trace(_meta_trace([{"id": "m1", "action_ids": [1], "source": "guessed", "status": "done"}]))[0]
    assert any("invalid source" in e for e in errs) and any("invalid status" in e for e in errs)


def test_meta_action_id_backref_mismatch():
    t = _meta_trace([{"id": "m1", "action_ids": [1]}])
    t["actions"][1]["meta_action_id"] = "m1"   # action 2 claims m1 but isn't a member
    assert any("disagrees with membership" in e for e in validate_trace(t)[0])


def test_dangling_parent_id():
    errs = validate_trace(_meta_trace([{"id": "m1", "action_ids": [1], "parent_id": "mX"}]))[0]
    assert any("parent_id 'mX' does not exist" in e for e in errs)


# --- structural errors ------------------------------------------------------

def test_valid_trace_has_no_errors():
    errors, _ = validate_trace(_trace(actions=[{"id": 1, "type": "ReadFile", "rationale": "r"}]))
    assert errors == []


def test_non_dict_is_error():
    errors, _ = validate_trace(["not", "a", "trace"])
    assert errors


def test_missing_trace_id():
    errors, _ = validate_trace(_trace(trace_id=""))
    assert any("trace_id" in e for e in errors)


def test_action_without_int_id():
    errors, _ = validate_trace(_trace(actions=[{"type": "ReadFile"}]))
    assert any("id" in e for e in errors)


def test_duplicate_action_ids():
    errors, _ = validate_trace(_trace(actions=[{"id": 1, "type": "A"}, {"id": 1, "type": "B"}]))
    assert any("duplicate" in e for e in errors)


def test_artifact_without_type():
    errors, _ = validate_trace(_trace(artifacts=[{"artifact_id": "a1"}]))
    assert any("artifact_type" in e for e in errors)


def test_invalid_residual_enum():
    errors, _ = validate_trace(_trace(residuals=[{"residual_id": "r1", "severity": "nope"}]))
    assert any("severity" in e for e in errors)


# --- warnings (incompleteness, not errors) ----------------------------------

def test_incomplete_trace_warns_not_errors():
    errors, warnings = validate_trace(_trace(trigger={}, outcome={}))
    assert errors == []
    assert any("trigger" in w for w in warnings)
    assert any("outcome" in w for w in warnings)


# --- command wiring ---------------------------------------------------------

def test_cmd_validate_returns_1_on_errors(tmp_path, capsys):
    f = tmp_path / "t.json"
    f.write_text(json.dumps(_trace(artifacts=[{"artifact_id": "a1"}])))
    assert cmd_validate(types.SimpleNamespace(trace_file=str(f))) == 1


def test_check_refuses_invalid_trace(tmp_path, capsys):
    f = tmp_path / "t.json"
    bad = _trace(actions=[{"type": "ReadFile"}],  # missing id
                 policies=[{"name": "x", "formula": "G(action)", "severity": "error"}])
    f.write_text(json.dumps(bad))
    rc = cmd_check(types.SimpleNamespace(trace_file=str(f), policy_file=None, strict=False))
    assert rc == 1
    assert "invalid trace" in capsys.readouterr().err


def test_load_trace_rejects_bad_json(tmp_path):
    f = tmp_path / "t.json"
    f.write_text("{ not valid json")
    with pytest.raises(SystemExit):
        load_trace(str(f))

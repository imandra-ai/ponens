"""Unit tests for `trace residual add` and `trace review-ready`."""

import json
import types

from ponens.trace import cmd_residual_add, cmd_review_ready


def _trace_file(tmp_path, **over):
    t = {"trace_id": "t", "spec_version": "1.1",
         "actions": [{"id": 1, "type": "EditFile", "rationale": "r"}],
         "artifacts": [], "outcome": {"type": "ProcessCompleted", "summary": "done"}}
    t.update(over)
    f = tmp_path / "t.json"
    f.write_text(json.dumps(t))
    return f


def _add_args(f, **over):
    a = dict(trace_file=str(f), kind="assumption", severity="medium", statement="assumes X",
             target_type=None, target_id=None, suggested_check=None, related=None,
             status="open", tag=None)
    a.update(over)
    return types.SimpleNamespace(**a)


# --- residual add -----------------------------------------------------------

def test_residual_add_appends_with_auto_id(tmp_path):
    f = _trace_file(tmp_path)
    cmd_residual_add(_add_args(f, statement="assumes upstream sorted"))
    r = json.loads(f.read_text())["residuals"]
    assert len(r) == 1
    assert r[0]["residual_id"] == "r1"
    assert r[0]["kind"] == "assumption" and r[0]["statement"] == "assumes upstream sorted"
    assert r[0]["source"] == "agent_declared"


def test_residual_add_second_increments_id(tmp_path):
    f = _trace_file(tmp_path)
    cmd_residual_add(_add_args(f))
    cmd_residual_add(_add_args(f, kind="unverified"))
    ids = [r["residual_id"] for r in json.loads(f.read_text())["residuals"]]
    assert ids == ["r1", "r2"]


def test_residual_add_with_target_and_check(tmp_path):
    f = _trace_file(tmp_path)
    cmd_residual_add(_add_args(f, target_type="artifact", target_id="a3",
                               suggested_check="add a test", tag=["concurrency"]))
    r = json.loads(f.read_text())["residuals"][0]
    assert r["target"] == {"target_type": "artifact", "target_id": "a3"}
    assert r["suggested_check"] == "add a test"
    assert r["tags"] == ["concurrency"]


def test_residual_add_bumps_spec_version(tmp_path):
    f = _trace_file(tmp_path)  # starts at 1.1
    cmd_residual_add(_add_args(f))
    assert json.loads(f.read_text())["spec_version"] == "1.5"


# --- review-ready -----------------------------------------------------------

def test_review_ready_fails_without_residuals(tmp_path):
    f = _trace_file(tmp_path)  # no residuals
    assert cmd_review_ready(types.SimpleNamespace(trace_file=str(f))) == 1


def test_review_ready_passes_when_complete(tmp_path):
    f = _trace_file(tmp_path)
    cmd_residual_add(_add_args(f))
    assert cmd_review_ready(types.SimpleNamespace(trace_file=str(f))) == 0


def test_review_ready_fails_without_outcome(tmp_path):
    f = _trace_file(tmp_path, outcome={})
    cmd_residual_add(_add_args(f))
    assert cmd_review_ready(types.SimpleNamespace(trace_file=str(f))) == 1


def test_review_ready_fails_missing_rationale(tmp_path):
    f = _trace_file(tmp_path, actions=[{"id": 1, "type": "EditFile"}])  # no rationale
    cmd_residual_add(_add_args(f))
    assert cmd_review_ready(types.SimpleNamespace(trace_file=str(f))) == 1

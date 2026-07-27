"""Unit tests for `trace residual add` and `trace review-ready`."""

import json
import types

from ponens import lineage
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

def test_residual_add_appends_as_residual_artifact(tmp_path):
    # v1.8: a residual is a first-class 'Residual' artifact; residuals[] is no longer written.
    f = _trace_file(tmp_path)
    cmd_residual_add(_add_args(f, statement="assumes upstream sorted"))
    saved = json.loads(f.read_text())
    assert saved.get("residuals", []) == []
    res_arts = [a for a in saved["artifacts"] if a["artifact_type"] == "Residual"]
    assert len(res_arts) == 1 and res_arts[0]["artifact_id"] == "r1"
    r = lineage.residual_surface(saved)
    assert len(r) == 1
    assert r[0]["residual_id"] == "r1"
    assert r[0]["kind"] == "assumption" and r[0]["statement"] == "assumes upstream sorted"
    assert r[0]["source"] == "agent_declared"


def test_residual_add_second_increments_id(tmp_path):
    f = _trace_file(tmp_path)
    cmd_residual_add(_add_args(f))
    cmd_residual_add(_add_args(f, kind="unverified"))
    ids = [r["residual_id"] for r in lineage.residual_surface(json.loads(f.read_text()))]
    assert ids == ["r1", "r2"]


def test_residual_add_with_target_and_check(tmp_path):
    f = _trace_file(tmp_path)
    cmd_residual_add(_add_args(f, target_type="artifact", target_id="a3",
                               suggested_check="add a test", tag=["concurrency"]))
    saved = json.loads(f.read_text())
    r = lineage.residual_surface(saved)[0]
    assert r["target"] == {"target_type": "artifact", "target_id": "a3"}
    assert r["suggested_check"] == "add a test"
    assert r["tags"] == ["concurrency"]
    # anchors into the lineage DAG via derived_from
    art = next(a for a in saved["artifacts"] if a["artifact_type"] == "Residual")
    assert art["derived_from"] == ["a3"]


def test_residual_add_bumps_spec_version(tmp_path):
    f = _trace_file(tmp_path)  # starts at 1.1
    cmd_residual_add(_add_args(f))
    assert json.loads(f.read_text())["spec_version"] == "1.8"


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

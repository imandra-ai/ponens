"""Unit tests for `ponens trace report` (PR-comment markdown) and `view --out`."""

import json
import types

from ponens.trace import cmd_report, cmd_view


def _trace(tmp_path, **over):
    t = {"trace_id": "t",
         "actions": [{"id": 1, "type": "EditFile", "rationale": "r" * 40}],
         "trigger": {"type": "TaskReceived", "description": "do a thing"},
         "outcome": {"type": "ProcessCompleted", "summary": "done"},
         "meta_actions": [{"id": "m1", "title": "Step", "action_ids": [1], "source": "turn_segmented"}],
         "residuals": [{"residual_id": "r1", "kind": "assumption", "severity": "high",
                        "statement": "assumed the API is sorted", "suggested_check": "confirm the contract"}]}
    t.update(over)
    f = tmp_path / "t.json"
    f.write_text(json.dumps(t))
    return f


def test_report_emits_markdown(tmp_path, capsys):
    assert cmd_report(types.SimpleNamespace(trace_file=str(_trace(tmp_path)))) == 0
    out = capsys.readouterr().out
    assert "Ponens reasoning trace" in out and "do a thing" in out
    assert "Grade" in out and "Scorecard" in out
    assert "🔴" in out and "assumed the API is sorted" in out and "*check:*" in out


def test_report_flags_missing_residuals(tmp_path, capsys):
    cmd_report(types.SimpleNamespace(trace_file=str(_trace(tmp_path, residuals=[]))))
    assert "No residuals declared" in capsys.readouterr().out


def test_view_out_writes_self_contained_html(tmp_path):
    out = tmp_path / "v.html"
    assert cmd_view(types.SimpleNamespace(trace_file=str(_trace(tmp_path)), out=str(out))) == 0
    html = out.read_text()
    assert "ponens-trace-data" in html   # the embedded trace block

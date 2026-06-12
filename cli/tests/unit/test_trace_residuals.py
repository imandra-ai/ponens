"""Unit tests for `ponens trace residuals` (cmd_residuals)."""

import json
import types

from ponens.trace import cmd_residuals


def _file(tmp_path, residuals):
    f = tmp_path / "t.json"
    f.write_text(json.dumps({"trace_id": "t", "residuals": residuals}))
    return types.SimpleNamespace(trace_file=str(f), json=False)


def test_residuals_json(tmp_path, capsys):
    args = _file(tmp_path, [{"residual_id": "r1", "kind": "limitation", "severity": "high", "status": "open"}])
    args.json = True
    cmd_residuals(args)
    out = json.loads(capsys.readouterr().out)
    assert out[0]["residual_id"] == "r1"


def test_residuals_empty(tmp_path, capsys):
    cmd_residuals(_file(tmp_path, []))
    assert "No residuals" in capsys.readouterr().out


def test_residuals_sorted_by_severity(tmp_path, capsys):
    args = _file(tmp_path, [
        {"residual_id": "zzz", "severity": "low", "kind": "x", "status": "open"},
        {"residual_id": "aaa", "severity": "critical", "kind": "y", "status": "open"},
    ])
    cmd_residuals(args)
    out = capsys.readouterr().out
    assert out.index("aaa") < out.index("zzz")  # critical printed before low

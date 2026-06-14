"""Unit tests for `ponens trace reproduce` — replay reproducible commands."""

import json
import types

from ponens.trace import _repro_safe, cmd_reproduce


def test_repro_safe_classification():
    assert _repro_safe("python -m pytest -q")
    assert _repro_safe("git status")
    assert _repro_safe("npm run build")
    assert not _repro_safe("rm -rf /")
    assert not _repro_safe("git commit -m x")
    assert not _repro_safe("git push origin main")
    assert not _repro_safe("echo hi")            # not a recognized safe verb
    assert not _repro_safe("pytest && rm x")     # safe verb but a danger token present


def _trace_with_cmd(tmp_path, cmd, expected, atype="RunTests"):
    t = {"trace_id": "t", "actions": [{
        "id": 1, "type": atype, "rationale": "r",
        "reproducibility": {"status": "reproducible", "reproduction_kind": "tool_reexecution",
                            "procedure": {"kind": "command", "command": cmd},
                            "expected_output": {"result_summary": expected}}}]}
    f = tmp_path / "t.json"
    f.write_text(json.dumps(t))
    return f


def test_reproduce_no_actions(tmp_path):
    f = tmp_path / "t.json"
    f.write_text(json.dumps({"trace_id": "t", "actions": [{"id": 1, "type": "EditFile", "rationale": "r"}]}))
    assert cmd_reproduce(types.SimpleNamespace(trace_file=str(f), run=False)) == 0


def test_reproduce_dry_run(tmp_path):
    f = _trace_with_cmd(tmp_path, "pytest -q", "6 passed")
    assert cmd_reproduce(types.SimpleNamespace(trace_file=str(f), run=False)) == 0


def test_reproduce_run_reports_divergence(tmp_path):
    # a safe, read-only command whose output cannot contain the bogus expected token
    f = _trace_with_cmd(tmp_path, "git status", "ZZZ_token_that_will_never_appear_ZZZ")
    assert cmd_reproduce(types.SimpleNamespace(trace_file=str(f), run=True)) == 1


def test_reproduce_skips_unsafe(tmp_path):
    # a dangerous command is never replayed (0 safe to replay) → no divergence, exit 0
    f = _trace_with_cmd(tmp_path, "rm -rf build", "done")
    assert cmd_reproduce(types.SimpleNamespace(trace_file=str(f), run=True)) == 0

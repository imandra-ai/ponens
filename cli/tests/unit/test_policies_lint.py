"""`ponens policies lint` — local policy validation (required fields + formula
syntax), the same oracle `trace check` applies before evaluating."""

import json
from argparse import Namespace

from ponens.registry import cmd_policies_lint

VALID = {
    "policy_id": "tests_before_commit",
    "name": "tests_before_commit",
    "severity": "error",
    "scope": "trace",
    "kind": "temporal",
    "formula": "G(GitCommit → P(RunTests ∧ completed))",
}


def _lint(tmp_path, payload, as_json=True):
    f = tmp_path / "policies.json"
    f.write_text(json.dumps(payload, ensure_ascii=False))
    return cmd_policies_lint(Namespace(policy_file=str(f), json=as_json))


def _records(capsys):
    return json.loads(capsys.readouterr().out)


def test_valid_policy_lints_valid(tmp_path, capsys):
    assert _lint(tmp_path, [VALID]) == 0
    (rec,) = _records(capsys)
    assert rec == {"policy_id": "tests_before_commit", "status": "valid"}


def test_wrapped_policies_key_is_accepted(tmp_path, capsys):
    assert _lint(tmp_path, {"policies": [VALID]}) == 0
    (rec,) = _records(capsys)
    assert rec["status"] == "valid"


def test_missing_scope_is_invalid_with_the_check_message(tmp_path, capsys):
    p = {k: v for k, v in VALID.items() if k != "scope"}
    assert _lint(tmp_path, [p]) == 0  # --json: verdicts in records, not the exit code
    (rec,) = _records(capsys)
    assert rec["status"] == "invalid"
    assert any("Missing required field 'scope'" in e["message"] for e in rec["errors"])


def test_formula_that_does_not_parse_is_invalid(tmp_path, capsys):
    p = dict(VALID, formula="G(GitCommit →")
    assert _lint(tmp_path, [p]) == 0
    (rec,) = _records(capsys)
    assert rec["status"] == "invalid"
    assert rec["errors"]


def test_missing_name_is_invalid_not_a_crash(tmp_path, capsys):
    p = {k: v for k, v in VALID.items() if k != "name"}
    assert _lint(tmp_path, [p]) == 0
    (rec,) = _records(capsys)
    assert rec["policy_id"] == "tests_before_commit"
    assert rec["status"] == "invalid"
    assert any("Missing required field 'name'" in e["message"] for e in rec["errors"])


def test_human_mode_exits_nonzero_on_invalid(tmp_path, capsys):
    p = {k: v for k, v in VALID.items() if k != "scope"}
    assert _lint(tmp_path, [p], as_json=False) == 1
    out = capsys.readouterr().out
    assert "INVALID" in out and "1 invalid" in out


def test_human_mode_exits_zero_when_all_valid(tmp_path, capsys):
    assert _lint(tmp_path, [VALID], as_json=False) == 0
    assert "0 invalid" in capsys.readouterr().out


def test_malformed_file_is_refused(tmp_path, capsys):
    f = tmp_path / "nope.json"
    f.write_text("{not json")
    assert cmd_policies_lint(Namespace(policy_file=str(f), json=True)) == 1
    captured = capsys.readouterr()
    assert captured.out == ""  # no records on refusal
    assert "cannot read policy file" in captured.err


def test_non_object_entries_are_refused(tmp_path, capsys):
    assert _lint(tmp_path, ["just a string"]) == 1
    assert "array of policy objects" in capsys.readouterr().err


def test_empty_list_lints_clean(tmp_path, capsys):
    assert _lint(tmp_path, []) == 0
    assert _records(capsys) == []

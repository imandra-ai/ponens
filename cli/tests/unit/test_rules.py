"""The validator has to say WHY, not only what.

"action 1 is in two meta-actions (m1 and t1)" is a statement about the author's data. It is not a
statement that nesting goes through `parent_id`, which is the belief they actually hold wrongly -
so an author who built a deliberate parent/child structure reads it as a description of what they
built and looks elsewhere. That happened; it cost an afternoon and shipped a run of invalid records.
"""
import json
import re
import types
from pathlib import Path

import pytest

from ponens import rules
from ponens.trace import validate_trace, cmd_validate, cmd_check, load_trace

SPEC = Path(__file__).resolve().parents[3] / "spec" / "TRACE_SPEC_v1_14.md"


def _write(tmp_path, trace):
    f = tmp_path / "t.json"
    f.write_text(json.dumps(trace))
    return f


# The defect that prompted all of this: one grouping nested inside another by repeating its members.
NESTED = {
    "trace_id": "t",
    "actions": [{"id": i, "type": "ReadFile", "rationale": "r"} for i in range(1, 13)],
    "artifacts": [],
    "meta_actions": [
        {"id": "m1", "action_ids": list(range(1, 13))},
        {"id": "t1", "action_ids": list(range(1, 13))},
    ],
}


def test_the_membership_error_names_the_rule_not_just_the_collision():
    errors, _ = validate_trace(NESTED)
    assert errors and all("is in two meta-actions" in e for e in errors)
    out = "\n".join(rules.render(errors))
    # The two things the bare message never said, and the author needed both.
    assert "parent_id" in out
    assert "at most one meta-action" in out


def test_one_mistake_is_explained_once_however_many_errors_it_made():
    errors, _ = validate_trace(NESTED)
    assert len(errors) == 12
    out = rules.render(errors)
    assert sum(1 for l in out if l.lstrip().startswith("rule:")) == 1


def test_errors_breaking_an_explained_rule_are_summarised_with_their_count():
    errors, _ = validate_trace(NESTED)
    out = "\n".join(rules.render(errors, limit=8))
    assert out.count("is in two meta-actions") == 8
    assert "and 4 more that break the same rule" in out
    # ... and nothing is hidden when the reader asks for all of it.
    assert "\n".join(rules.render(errors, show_all=True)).count("is in two meta-actions") == 12


def test_a_closed_vocabulary_says_what_was_allowed():
    errors, _ = validate_trace({"trace_id": "t", "actions": [], "artifacts": [],
                                "residuals": [{"residual_id": "r1", "kind": "bounded"}]})
    out = "\n".join(rules.render(errors))
    assert "assumption" in out and "out_of_scope" in out      # the permitted kinds, spelled out
    assert "severities:" not in out                            # but not the four the author did not trip


def test_a_vocabulary_error_cites_the_section_that_defines_THAT_vocabulary():
    # Citing oracle attribution at somebody whose residual severity is misspelled is worse than
    # citing nothing: it sends them to the wrong page.
    errors, _ = validate_trace({"trace_id": "t", "actions": [], "artifacts": [],
                                "residuals": [{"residual_id": "r1", "severity": "nope"}]})
    out = "\n".join(rules.render(errors))
    assert "Residual semantics" in out
    assert "Oracle attribution" not in out


def test_errors_no_rule_claims_are_never_summarised():
    # The unclaimed group is a mixed bag - "N more that break the same rule" would be false about
    # it, and what it hid would be exactly the errors nothing yet explains.
    unclaimed = [f"something nobody wrote a rule for, number {i}" for i in range(20)]
    out = "\n".join(rules.render(unclaimed, limit=3))
    assert out.count("something nobody wrote a rule for") == 20
    assert "break the same rule" not in out


@pytest.mark.parametrize("cite", sorted({r["cite"] for r in rules.RULES}
                                        | {v[2] for v in rules._vocab().values()}))
def test_every_citation_points_at_a_section_that_exists(cite):
    """A rotted citation is worse than none - it spends the reader's trust and their time."""
    text = SPEC.read_text()
    for sec in re.findall(r"§[\d.]+[a-z]?", cite):
        assert re.search(rf"^#+ {re.escape(sec[1:])} ", text, re.M), f"{sec} is not a section of {SPEC.name}"


def _emitted_error_messages():
    """Every error string the validator can produce, read out of its own source.

    A hand-written sample only ever covers the errors somebody thought of, which is the same
    weakness as the thing being tested. This walks `validate_trace` and `soundness_errors` for
    every append to their error list and renders each f-string with a placeholder, so a check
    added tomorrow shows up here whether or not anyone remembers this file.
    """
    import ast
    from ponens import trace as trace_mod
    tree = ast.parse(Path(trace_mod.__file__).read_text())

    def literal(n):
        if isinstance(n, ast.Constant):
            return str(n.value)
        if isinstance(n, ast.JoinedStr):
            return "".join(str(v.value) if isinstance(v, ast.Constant) else "X" for v in n.values)
        if isinstance(n, ast.BinOp):
            left, right = literal(n.left), literal(n.right)
            return (left or "") + (right or "") if (left or right) else None
        return None

    out = {}
    for fname in ("validate_trace", "soundness_errors"):
        fn = next(x for x in ast.walk(tree)
                  if isinstance(x, ast.FunctionDef) and x.name == fname)
        for n in ast.walk(fn):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr in ("append", "extend") and n.args):
                continue
            target = n.func.value
            # Only the ERROR sinks. Warnings are incompleteness while a trace is being authored;
            # they do not reject anything, so they do not owe the reader a rule.
            if not (isinstance(target, ast.Name) and target.id in ("errors", "errs")):
                continue
            msg = literal(n.args[0])
            if msg and len(msg) > 4:
                out.setdefault(msg, f"{trace_mod.__name__}:{n.lineno}")
    return out


def test_every_error_the_validator_can_emit_has_a_rule():
    """A rule table that only covers the errors it was written for is a table that goes stale.

    --strict was exactly that: ten of its fifteen messages went through the same renderer with
    nothing to explain them, because the table had been written against the plain validator.
    """
    msgs = _emitted_error_messages()
    assert len(msgs) > 40, f"only found {len(msgs)} error sites - has the extractor stopped working?"
    unexplained = {m: where for m, where in msgs.items() if rules.rule_for(m) is None}
    assert unexplained == {}, "no rule explains:\n" + "\n".join(
        f"  {w}  {m}" for m, w in sorted(unexplained.items(), key=lambda kv: kv[1]))


# --- the commands -----------------------------------------------------------

def test_validate_prints_the_rule(tmp_path, capsys):
    f = _write(tmp_path, NESTED)
    assert cmd_validate(types.SimpleNamespace(trace_file=str(f), strict=False, all=False)) == 1
    out = capsys.readouterr().out
    assert "rule:" in out and "parent_id" in out
    assert "Invalid trace: 12 error(s)" in out


def test_check_says_that_nothing_was_evaluated(tmp_path, capsys):
    # This is the message most authors hit: policy evaluation validates BEFORE it evaluates, so an
    # invalid trace means no policy ran at all - an absence that otherwise looks like a pass.
    f = _write(tmp_path, NESTED)
    rc = cmd_check(types.SimpleNamespace(trace_file=str(f), policy_file=None, strict=False))
    assert rc == 1
    err = capsys.readouterr().err
    assert "No policy was evaluated" in err
    assert "parent_id" in err


def test_a_valid_trace_is_unchanged(tmp_path, capsys):
    f = _write(tmp_path, {"trace_id": "t", "actions": [], "artifacts": [],
                          "trigger": {"type": "user"}, "outcome": {"type": "done"}})
    assert cmd_validate(types.SimpleNamespace(trace_file=str(f), strict=False, all=False)) == 0
    assert "Valid trace" in capsys.readouterr().out


# --- reading an invalid trace -----------------------------------------------

def test_every_read_of_an_invalid_trace_says_so(tmp_path, capsys):
    """`validate` and `check` refused it; every other command reported on it and exited 0.

    `overview` printed a gate verdict, `status` a summary, `residuals` a gap list - none of them
    mentioning that the record underneath had been rejected, so a reader got a confident report
    about a record nothing downstream would accept.
    """
    f = _write(tmp_path, NESTED)
    load_trace(str(f))
    err = capsys.readouterr().err
    assert "INVALID" in err
    assert "nothing below has been governed" in err
    assert "is in two meta-actions" in err


def test_the_warning_is_a_warning_not_a_refusal(tmp_path, capsys):
    # Diagnosing a broken record is exactly when you want to read it.
    f = _write(tmp_path, NESTED)
    assert load_trace(str(f))["trace_id"] == "t"


def test_a_valid_trace_reads_silently(tmp_path, capsys):
    f = _write(tmp_path, {"trace_id": "t", "actions": [], "artifacts": [],
                          "trigger": {"type": "user"}, "outcome": {"type": "done"}})
    load_trace(str(f))
    assert capsys.readouterr().err == ""


def test_validate_does_not_say_it_twice(tmp_path, capsys):
    f = _write(tmp_path, NESTED)
    cmd_validate(types.SimpleNamespace(trace_file=str(f), strict=False, all=False))
    captured = capsys.readouterr()
    assert "nothing below has been governed" not in captured.err + captured.out

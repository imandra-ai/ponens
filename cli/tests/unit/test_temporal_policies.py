"""Unit tests for the temporal/scoped LTL evaluator (cli/ponens/trace.py).

These drive the full path — tokenize -> parse -> evaluate — via evaluate_policy
over controlled traces, covering G/F/P/P_target, implication, negation,
field-emptiness, and the lifecycle predicates. No hub server required.
"""

import json
import os

from ponens.trace import evaluate_policy, normalize_trace

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def action(aid, atype, rationale="did a thing", result_summary="",
           evidence=None, inputs=None, outputs=None, category="activity"):
    return {"id": aid, "type": atype, "category": category, "rationale": rationale,
            "result_summary": result_summary, "evidence": evidence or [],
            "inputs": inputs or [], "outputs": outputs or []}


def trace(actions, trigger=None, outcome=None, artifacts=None):
    return {"actions": actions, "artifacts": artifacts or [],
            "trigger": trigger or {}, "outcome": outcome or {}}


def policy(name, formula):
    return {"name": name, "formula": formula, "severity": "error"}


def fileref(path):
    return [{"type": "FileRef", "ref": path}]


# ---------------------------------------------------------------------------
# G(GitCommit -> P(RunTests /\ completed))   — tests before commit
# ---------------------------------------------------------------------------

TESTS_BEFORE_COMMIT = policy("tests_before_commit", "G(GitCommit → P(RunTests ∧ completed))")


def test_tests_before_commit_passes():
    t = trace([action(1, "RunTests", result_summary="84/84 passed"),
               action(2, "GitCommit")])
    assert evaluate_policy(TESTS_BEFORE_COMMIT, t) == ("passed", None)


def test_tests_before_commit_fails_with_no_tests():
    t = trace([action(1, "EditFile"), action(2, "GitCommit")])
    assert evaluate_policy(TESTS_BEFORE_COMMIT, t)[0] == "failed"


def test_tests_before_commit_fails_when_tests_not_completed():
    # RunTests present but result_summary doesn't indicate completion
    t = trace([action(1, "RunTests", result_summary=""), action(2, "GitCommit")])
    assert evaluate_policy(TESTS_BEFORE_COMMIT, t)[0] == "failed"


def test_tests_before_commit_vacuous_without_commit():
    t = trace([action(1, "EditFile")])
    assert evaluate_policy(TESTS_BEFORE_COMMIT, t) == ("passed", None)


# ---------------------------------------------------------------------------
# G(action -> rationale != empty)
# ---------------------------------------------------------------------------

RATIONALE = policy("all_actions_have_rationale", "G(action → rationale ≠ ∅)")


def test_rationale_passes():
    t = trace([action(1, "ReadFile"), action(2, "EditFile")])
    assert evaluate_policy(RATIONALE, t) == ("passed", None)


def test_rationale_fails_on_empty():
    t = trace([action(1, "ReadFile", rationale=""), action(2, "EditFile")])
    assert evaluate_policy(RATIONALE, t)[0] == "failed"


# ---------------------------------------------------------------------------
# start_event /\ F(end_event)  — lifecycle
# ---------------------------------------------------------------------------

LIFECYCLE = policy("trace_has_proper_lifecycle", "start_event ∧ F(end_event)")


def test_lifecycle_passes():
    t = trace([action(1, "ReadFile")],
              trigger={"type": "TaskReceived"}, outcome={"type": "ProcessCompleted"})
    assert evaluate_policy(LIFECYCLE, t) == ("passed", None)


def test_lifecycle_fails_without_outcome():
    t = trace([action(1, "ReadFile")], trigger={"type": "TaskReceived"}, outcome={})
    assert evaluate_policy(LIFECYCLE, t)[0] == "failed"


def test_lifecycle_fails_without_trigger():
    t = trace([action(1, "ReadFile")], trigger={}, outcome={"type": "ProcessCompleted"})
    assert evaluate_policy(LIFECYCLE, t)[0] == "failed"


# ---------------------------------------------------------------------------
# G(EditFile -> P_target(ReadFile \/ ...))  — scoped: research before edit
# ---------------------------------------------------------------------------

RESEARCH = policy(
    "research_before_edit",
    "G(EditFile → P_target(ReadFile ∨ ReadDocumentation ∨ SearchCode ∨ AnalyzeCode))",
)


def test_research_before_edit_passes_same_target():
    t = trace([action(1, "ReadFile", evidence=fileref("foo.py")),
               action(2, "EditFile", evidence=fileref("foo.py"))])
    assert evaluate_policy(RESEARCH, t) == ("passed", None)


def test_research_before_edit_fails_without_research():
    t = trace([action(1, "EditFile", evidence=fileref("foo.py"))])
    assert evaluate_policy(RESEARCH, t)[0] == "failed"


# ---------------------------------------------------------------------------
# F and negation
# ---------------------------------------------------------------------------

def test_finally_finds_action():
    t = trace([action(1, "ReadFile"), action(2, "GitCommit")])
    assert evaluate_policy(policy("p", "F(GitCommit)"), t) == ("passed", None)


def test_globally_negation_no_delete_passes():
    t = trace([action(1, "ReadFile"), action(2, "EditFile")])
    assert evaluate_policy(policy("p", "G(¬ DeleteFile)"), t) == ("passed", None)


def test_globally_negation_no_delete_fails():
    t = trace([action(1, "DeleteFile")])
    assert evaluate_policy(policy("p", "G(¬ DeleteFile)"), t)[0] == "failed"


# ---------------------------------------------------------------------------
# parse errors degrade to 'unknown' (not a crash)
# ---------------------------------------------------------------------------

def test_unparseable_formula_is_unknown():
    status, note = evaluate_policy(policy("p", "G(((("), trace([action(1, "ReadFile")]))
    assert status == "unknown"


def test_missing_formula_is_unknown():
    status, _ = evaluate_policy({"name": "p", "formula": "", "severity": "error"},
                                trace([action(1, "ReadFile")]))
    assert status == "unknown"


# ---------------------------------------------------------------------------
# Integration: the real stripe example trace passes its temporal policies
# ---------------------------------------------------------------------------

def _stripe():
    with open(os.path.join(REPO, "examples", "stripe_v1_1.json")) as f:
        t = json.load(f)
    normalize_trace(t)
    return t


def _find_policy(t, name):
    return next(p for p in t["policies"] if p.get("name") == name)


def test_stripe_tests_before_commit_passes():
    t = _stripe()
    assert evaluate_policy(_find_policy(t, "tests_before_commit"), t) == ("passed", None)


def test_stripe_all_actions_have_rationale_passes():
    t = _stripe()
    assert evaluate_policy(_find_policy(t, "all_actions_have_rationale"), t) == ("passed", None)

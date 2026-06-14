"""Unit tests for the Until / Since / Next evaluators (#5).

Before the fix these operators parsed but fell through to the evaluator's default
`return True`, so any policy using U/S/X vacuously passed. These tests pin the
real semantics — and that they no longer no-op.
"""

from ponens.trace import evaluate_policy


def ev(formula, actions):
    pol = {"name": "x", "formula": formula, "severity": "error"}
    trace = {"actions": actions, "artifacts": [], "residuals": []}
    return evaluate_policy(pol, trace)[0]


def A(i, t):
    return {"id": i, "type": t, "rationale": "r"}


# --- Next (X) ---------------------------------------------------------------

def test_next_pass():
    assert ev("G(EditFile -> X GitCommit)", [A(1, "EditFile"), A(2, "GitCommit")]) == "passed"


def test_next_fail():
    assert ev("G(EditFile -> X GitCommit)", [A(1, "EditFile"), A(2, "ReadFile")]) == "failed"


def test_next_at_end_is_false():
    # strong next: X at the last position is false
    assert ev("G(GitCommit -> X ReadFile)", [A(1, "ReadFile"), A(2, "GitCommit")]) == "failed"


# --- Until (U) --------------------------------------------------------------

def test_until_pass():
    assert ev("RunTests U GitCommit",
              [A(1, "RunTests"), A(2, "RunTests"), A(3, "GitCommit")]) == "passed"


def test_until_fail_left_breaks():
    assert ev("RunTests U GitCommit",
              [A(1, "RunTests"), A(2, "EditFile"), A(3, "GitCommit")]) == "failed"


def test_until_fail_no_right():
    assert ev("RunTests U GitCommit", [A(1, "RunTests"), A(2, "RunTests")]) == "failed"


# --- Since (S) --------------------------------------------------------------

def test_since_pass():
    assert ev("EditFile S ReadFile",
              [A(1, "ReadFile"), A(2, "EditFile"), A(3, "EditFile")]) == "passed"


def test_since_fail_left_breaks():
    assert ev("EditFile S ReadFile",
              [A(1, "ReadFile"), A(2, "GitCommit"), A(3, "EditFile")]) == "failed"


# --- regression: no longer vacuously true ----------------------------------

def test_until_not_vacuously_true():
    # would have returned "passed" before the fix (default return True)
    assert ev("RunTests U GitCommit", [A(1, "EditFile")]) == "failed"

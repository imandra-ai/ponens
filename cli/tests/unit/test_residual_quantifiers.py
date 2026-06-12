"""Unit tests for the general residual-quantifier interpreter (#4).

These go through the real parse -> evaluate path (non-structural policy names),
exercising forall/exists/exists-unique over `residuals` with field access,
severity ordering, and empty comparisons.
"""

from ponens.trace import evaluate_policy


def ev(formula, residuals, actions=None):
    policy = {"name": "custom", "formula": formula, "severity": "error"}
    trace = {"actions": actions or [], "artifacts": [], "residuals": residuals}
    return evaluate_policy(policy, trace)


def status(formula, residuals, actions=None):
    return ev(formula, residuals, actions)[0]


# --- quantifier basics -----------------------------------------------------

def test_forall_over_empty_is_true():
    assert status("∀ r ∈ residuals . r.kind = Assumption", []) == "passed"


def test_exists_over_empty_is_false():
    assert status("∃ r ∈ residuals . r.kind = Assumption", []) == "failed"


def test_exists_finds_match():
    assert status("∃ r ∈ residuals . r.kind = Assumption",
                  [{"kind": "limitation"}, {"kind": "assumption"}]) == "passed"


def test_exists_no_match():
    assert status("∃ r ∈ residuals . r.kind = Assumption",
                  [{"kind": "limitation"}]) == "failed"


def test_forall_holds():
    assert status("∀ r ∈ residuals . r.status = Open",
                  [{"status": "open"}, {"status": "open"}]) == "passed"


def test_forall_fails():
    assert status("∀ r ∈ residuals . r.status = Open",
                  [{"status": "open"}, {"status": "waived"}]) == "failed"


def test_exists_unique():
    f = "∃!r ∈ residuals . r.severity = Critical"
    assert status(f, [{"severity": "critical"}, {"severity": "low"}]) == "passed"
    assert status(f, [{"severity": "critical"}, {"severity": "critical"}]) == "failed"
    assert status(f, [{"severity": "low"}]) == "failed"


# --- comparisons -----------------------------------------------------------

def test_enum_compare_is_case_insensitive():
    # formula uses Critical; data uses lowercase critical
    assert status("∃ r ∈ residuals . r.severity = Critical",
                  [{"severity": "critical"}]) == "passed"


def test_severity_ordering_ge():
    f = "∀ r ∈ residuals . r.severity ≥ High → r.status ≠ Open"
    assert status(f, [{"severity": "high", "status": "open"}]) == "failed"
    assert status(f, [{"severity": "high", "status": "acknowledged"}]) == "passed"
    assert status(f, [{"severity": "medium", "status": "open"}]) == "passed"  # medium < high


def test_ne_empty():
    f = "∀ r ∈ residuals . r.kind = Unverified → r.suggested_check ≠ ∅"
    assert status(f, [{"kind": "unverified", "suggested_check": "do x"}]) == "passed"
    assert status(f, [{"kind": "unverified"}]) == "failed"
    assert status(f, [{"kind": "unverified", "suggested_check": "  "}]) == "failed"


def test_eq_empty():
    f = "∃ r ∈ residuals . r.target = ∅"
    assert status(f, [{"target": {"target_id": "a3"}}]) == "failed"
    assert status(f, [{"target": {"target_id": "a3"}}, {"kind": "x"}]) == "passed"


def test_negated_exists():
    f = "¬∃ r ∈ residuals . r.severity = Critical ∧ r.status = Open"
    assert status(f, [{"severity": "critical", "status": "open"}]) == "failed"
    assert status(f, [{"severity": "critical", "status": "waived"}]) == "passed"


# --- composition with temporal operators -----------------------------------

def test_quantifier_under_temporal_trigger():
    f = "G(GitCommit → ∀ r ∈ residuals . r.severity ≥ High → r.status ≠ Open)"
    commit = [{"id": 1, "type": "GitCommit"}]
    assert status(f, [{"severity": "high", "status": "open"}], commit) == "failed"
    # no commit → vacuously satisfied
    assert status(f, [{"severity": "high", "status": "open"}], []) == "passed"


# --- the formula must actually parse (not fall back to 'unknown') ----------

def test_residual_formula_parses():
    st, note = ev("∀ r ∈ residuals . r.kind = Assumption → r.target ≠ ∅", [{"kind": "limitation"}])
    assert st == "passed" and note is None

"""Unit tests for the residual-surface policy evaluators (Trace Spec §13, Policy Spec §17.4).

These are pure functions over a trace dict — no hub server required.
"""

from ponens.trace import evaluate_structural, evaluate_policy


def trace(residuals, actions=None):
    return {
        "actions": actions or [],
        "artifacts": [],
        "residuals": residuals,
        "policies": [],
        "policy_evaluations": [],
    }


COMMIT = [{"id": 1, "type": "GitCommit", "label": "commit", "rationale": "ship"}]


# ---------------------------------------------------------------------------
# no_open_critical_residuals
# ---------------------------------------------------------------------------

def test_critical_open_fails():
    t = trace([{"kind": "limitation", "severity": "critical", "status": "open"}])
    assert evaluate_structural("no_open_critical_residuals", t) is False


def test_critical_waived_passes():
    t = trace([{"kind": "limitation", "severity": "critical", "status": "waived"}])
    assert evaluate_structural("no_open_critical_residuals", t) is True


def test_critical_missing_status_treated_as_open():
    t = trace([{"kind": "limitation", "severity": "critical"}])
    assert evaluate_structural("no_open_critical_residuals", t) is False


def test_no_critical_passes():
    t = trace([{"kind": "unverified", "severity": "high", "status": "open"}])
    assert evaluate_structural("no_open_critical_residuals", t) is True


def test_empty_residuals_passes():
    assert evaluate_structural("no_open_critical_residuals", trace([])) is True


# ---------------------------------------------------------------------------
# high_severity_residuals_acknowledged_before_commit
# ---------------------------------------------------------------------------

def test_commit_with_open_high_fails():
    t = trace([{"kind": "unverified", "severity": "high", "status": "open"}], actions=COMMIT)
    assert evaluate_structural("high_severity_residuals_acknowledged_before_commit", t) is False


def test_commit_with_acknowledged_high_passes():
    t = trace([{"kind": "unverified", "severity": "high", "status": "acknowledged"}], actions=COMMIT)
    assert evaluate_structural("high_severity_residuals_acknowledged_before_commit", t) is True


def test_no_commit_is_vacuously_true():
    t = trace([{"kind": "unverified", "severity": "critical", "status": "open"}])  # no commit action
    assert evaluate_structural("high_severity_residuals_acknowledged_before_commit", t) is True


def test_commit_with_open_medium_passes():
    t = trace([{"kind": "unverified", "severity": "medium", "status": "open"}], actions=COMMIT)
    assert evaluate_structural("high_severity_residuals_acknowledged_before_commit", t) is True


# ---------------------------------------------------------------------------
# unverified_residuals_have_suggested_check
# ---------------------------------------------------------------------------

def test_unverified_without_check_fails():
    t = trace([{"kind": "unverified", "severity": "low", "status": "open"}])
    assert evaluate_structural("unverified_residuals_have_suggested_check", t) is False


def test_unverified_blank_check_fails():
    t = trace([{"kind": "unverified", "suggested_check": "   "}])
    assert evaluate_structural("unverified_residuals_have_suggested_check", t) is False


def test_unverified_with_check_passes():
    t = trace([{"kind": "unverified", "suggested_check": "add a verification goal"}])
    assert evaluate_structural("unverified_residuals_have_suggested_check", t) is True


def test_non_unverified_without_check_passes():
    t = trace([{"kind": "assumption"}])
    assert evaluate_structural("unverified_residuals_have_suggested_check", t) is True


# ---------------------------------------------------------------------------
# assumptions_are_located
# ---------------------------------------------------------------------------

def test_assumption_unlocated_fails():
    t = trace([{"kind": "assumption", "statement": "upstream is sorted"}])
    assert evaluate_structural("assumptions_are_located", t) is False


def test_assumption_with_empty_related_fails():
    t = trace([{"kind": "assumption", "related_artifact_ids": []}])
    assert evaluate_structural("assumptions_are_located", t) is False


def test_assumption_with_target_passes():
    t = trace([{"kind": "assumption", "target": {"target_type": "artifact", "target_id": "a3"}}])
    assert evaluate_structural("assumptions_are_located", t) is True


def test_assumption_with_related_passes():
    t = trace([{"kind": "assumption", "related_artifact_ids": ["a3"]}])
    assert evaluate_structural("assumptions_are_located", t) is True


# ---------------------------------------------------------------------------
# evaluate_policy dispatch (routes structural policies by name)
# ---------------------------------------------------------------------------

def test_evaluate_policy_routes_structural_fail():
    policy = {"name": "no_open_critical_residuals", "formula": "...", "severity": "error"}
    t = trace([{"kind": "limitation", "severity": "critical", "status": "open"}])
    assert evaluate_policy(policy, t) == ("failed", None)


def test_evaluate_policy_routes_structural_pass():
    policy = {"name": "no_open_critical_residuals", "formula": "...", "severity": "error"}
    t = trace([{"kind": "limitation", "severity": "low", "status": "open"}])
    assert evaluate_policy(policy, t) == ("passed", None)

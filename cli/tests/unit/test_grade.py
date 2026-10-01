"""Unit tests for the trace quality rubric (grade_trace)."""

import json
import os

from ponens.trace import grade_trace

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _dim(g, name):
    return next(d for d in g["dimensions"] if d["name"] == name)


def test_overall_is_bounded_and_renormalizes_over_applicable():
    g = grade_trace({"trace_id": "t", "actions": []})
    assert 0 <= g["overall"] <= 100
    # no artifacts -> Lineage/integrity is N/A and excluded from the weighting
    assert _dim(g, "Lineage / integrity")["applicable"] is False
    applicable = [d for d in g["dimensions"] if d.get("applicable", True)]
    assert g["applicable_weight"] == sum(d["weight"] for d in applicable)


def test_stripe_grades_well_with_strong_evidence():
    stripe = json.load(open(os.path.join(REPO, "examples", "stripe_v1_1.json")))
    g = grade_trace(stripe)
    assert g["overall"] >= 70 and g["grade"] in ("A", "B", "C")
    assert _dim(g, "Verification evidence")["score"] >= 0.9   # proofs + tests present


def test_bare_trace_zero_negative_space_and_suggests_residuals():
    t = {"trace_id": "t",
         "actions": [{"id": 1, "type": "EditFile", "rationale": "a fairly substantive rationale here"}],
         "trigger": {"type": "TaskReceived"},
         "outcome": {"type": "ProcessCompleted", "summary": "did the thing well enough to ship"}}
    g = grade_trace(t)
    assert _dim(g, "Negative space")["score"] == 0.0
    assert any("residual" in s for s in g["suggestions"])


def test_declaring_residuals_improves_grade():
    base = {"trace_id": "t",
            "actions": [{"id": 1, "type": "EditFile", "rationale": "x" * 40}],
            "trigger": {"type": "T"}, "outcome": {"type": "P", "summary": "y" * 30}}
    g0 = grade_trace(base)["overall"]
    with_r = dict(base, residuals=[{"residual_id": "r1", "kind": "unverified", "severity": "medium",
                                    "suggested_check": "c", "target": {"target_type": "artifact", "target_id": "a1"}}])
    assert grade_trace(with_r)["overall"] > g0


def test_structural_errors_tank_structure():
    g = grade_trace({"trace_id": "", "actions": [{"type": "X"}]})  # missing trace_id + action id
    assert _dim(g, "Structure")["score"] < 0.5


def test_evidence_rewards_verification_results():
    no_proof = {"trace_id": "t", "actions": [], "artifacts": [{"artifact_id": "a1", "artifact_type": "Diff"}]}
    proof = {"trace_id": "t", "actions": [],
             "artifacts": [{"artifact_id": "a1", "artifact_type": "VerificationResult"}]}
    assert _dim(grade_trace(proof), "Verification evidence")["score"] > \
           _dim(grade_trace(no_proof), "Verification evidence")["score"]


# --- lineage / integrity (structural checks, run) ---------------------------

def test_lineage_na_without_artifacts():
    g = grade_trace({"trace_id": "t", "actions": [{"id": 1, "type": "EditFile", "rationale": "r" * 40}]})
    assert _dim(g, "Lineage / integrity")["applicable"] is False


def test_lineage_scored_on_stripe():
    stripe = json.load(open(os.path.join(REPO, "examples", "stripe_v1_1.json")))
    d = _dim(grade_trace(stripe), "Lineage / integrity")
    assert d["applicable"] is True and d["score"] >= 0.99   # well-formed DAG


def test_broken_lineage_is_penalized():
    # action consumes an artifact that no earlier action produced -> data_flow_integrity fails
    broken = {"trace_id": "t",
              "actions": [{"id": 1, "type": "Verify", "rationale": "r" * 40,
                           "inputs": ["ghost"], "outputs": []}],
              "artifacts": [{"artifact_id": "a1", "artifact_type": "IMLModel"}]}
    assert _dim(grade_trace(broken), "Lineage / integrity")["score"] < 1.0


# --- policy compliance (separate axis) --------------------------------------

def test_compliance_not_applicable_without_policies():
    g = grade_trace({"trace_id": "t", "actions": []})
    assert g["compliance"]["applicable"] is False


def test_compliance_runs_attached_policies():
    # a trivially-true structural policy attached -> compliance reports it, separately
    t = {"trace_id": "t", "actions": [], "artifacts": [],
         "policies": [{"name": "data_flow_integrity", "policy_id": "data_flow_integrity",
                       "formula": "data_flow_integrity"}]}
    g = grade_trace(t)
    assert g["compliance"]["applicable"] is True
    assert g["compliance"]["total"] == 1
    # compliance is reported but does NOT appear as a quality dimension
    assert all(d["name"] != "Policy compliance" for d in g["dimensions"])


def test_a_warning_severity_violation_is_advisory_not_a_failed_gate():
    """`grade` and `overview` must not contradict each other about the same trace.

    Compliance ignored severity, so a warning-severity violation was rendered as a failed governance
    gate - while `trace overview` reported `Gate: pass` on that very trace and `trace check` exited 0.
    `failed` stays the union of every violation; `blocking` is the subset that actually stops anything.
    """
    pol = lambda n, f, sev: {"name": n, "policy_id": n, "formula": f, "severity": sev}
    t = {"trace_id": "t", "actions": [], "artifacts": [],
         "policies": [pol("ok", "¬data_flow_integrity", "error"),
                      pol("advises", "data_flow_integrity", "warning")]}

    c = grade_trace(t)["compliance"]
    assert c["advisory"] == ["advises"], "the warning is recorded"
    assert c["blocking"] == [], "and it blocks nothing"
    assert c["failed"] == ["advises"], "while `failed` still names every violation"


def test_an_error_severity_violation_still_blocks():
    pol = lambda n, f, sev: {"name": n, "policy_id": n, "formula": f, "severity": sev}
    t = {"trace_id": "t", "actions": [], "artifacts": [],
         "policies": [pol("blocks", "data_flow_integrity", "error")]}
    c = grade_trace(t)["compliance"]
    assert c["blocking"] == ["blocks"] and c["advisory"] == []


def _run(aid, typ, cmd=None):
    a = {"id": aid, "type": typ, "rationale": "r" * 40}
    if cmd:
        a["reproducibility"] = {"status": "reproducible", "reproduction_kind": "tool_reexecution",
                                "procedure": {"kind": "command", "command": cmd}}
    return a


def test_reproducibility_a_commit_is_reproduced_by_binding_not_by_running_it_again():
    # Every run recorded, a commit made: full marks once bound - the commit is not a command to replay.
    t = {"trace_id": "t", "commit_sha": "abc123", "reproducibility": {"status": "partially_reproducible"},
         "actions": [_run(1, "RunTests", "pytest -q"), _run(2, "GitCommit")]}
    assert _dim(grade_trace(t), "Reproducibility")["score"] == 1.0
    # Unbound, the same trace loses exactly the binding.
    del t["commit_sha"]
    assert _dim(grade_trace(t), "Reproducibility")["score"] == 0.75


def test_reproducibility_counts_a_command_the_replayer_will_not_run_as_half():
    # Recorded but not re-checkable here (an unknown runner): half the credit of one it will replay.
    t = {"trace_id": "t", "commit_sha": "abc123", "reproducibility": {"status": "partially_reproducible"},
         "actions": [_run(1, "RunTests", "pytest -q"), _run(2, "RunTests", "./run-my-suite.sh")]}
    d = _dim(grade_trace(t), "Reproducibility")
    assert d["score"] == 0.5 * 0.75 + 0.5
    assert "1 safe to replay" in d["note"]


def test_stripe_is_reproducible_as_far_as_an_unbound_sample_can_be():
    stripe = json.load(open(os.path.join(REPO, "examples", "stripe_v1_1.json")))
    d = _dim(grade_trace(stripe), "Reproducibility")
    assert d["score"] == 0.75 and "not bound to a commit" in d["note"]


def test_reproducibility_region_tests_are_test_runs():
    # A record whose only test run is its region tests (a ConformanceCheck) has something to re-run.
    t = {"trace_id": "t", "commit_sha": "abc123", "reproducibility": {"status": "partially_reproducible"},
         "actions": [_run(1, "ConformanceCheck", "node --test region.test.mjs")]}
    assert _dim(grade_trace(t), "Reproducibility")["score"] == 1.0
    # A command on a step that is not a run is not counted as one.
    t["actions"] = [_run(1, "RunTests", "pytest -q"), _run(2, "Analyze", "pytest -q")]
    assert "1 replayable action(s)" in _dim(grade_trace(t), "Reproducibility")["note"]

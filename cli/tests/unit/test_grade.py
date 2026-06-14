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

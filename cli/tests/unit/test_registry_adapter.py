"""Unit tests for the gallery->trace policy schema adapter (registry.py)."""

from ponens.registry import gallery_to_trace_policy
from ponens.policy_compiler import STRUCTURAL_POLICIES


def test_maps_id_to_policy_id_and_name():
    gp = {"id": "tests_before_commit", "name": "Tests Before Commit",
          "severity": "error", "formula": "G(GitCommit -> P(RunTests))"}
    p = gallery_to_trace_policy(gp)
    assert p["policy_id"] == "tests_before_commit"
    # snake_case id becomes `name` so structural policies match the compiler registry
    assert p["name"] == "tests_before_commit"
    assert p["display_name"] == "Tests Before Commit"
    assert p["formula"] == "G(GitCommit -> P(RunTests))"
    assert p["severity"] == "error"


def test_defaults_scope_and_kind():
    p = gallery_to_trace_policy({"id": "x", "name": "X", "severity": "warning", "formula": "f"})
    assert p["scope"] == "trace"
    assert p["kind"] == "trace_invariant"


def test_structural_id_preserved_as_name():
    gp = {"id": "no_open_critical_residuals", "name": "No Open Critical Residuals",
          "severity": "error", "formula": "..."}
    p = gallery_to_trace_policy(gp)
    assert p["name"] in STRUCTURAL_POLICIES


def test_ltl_formula_fallback():
    p = gallery_to_trace_policy({"id": "y", "name": "Y", "severity": "info", "ltl_formula": "G(a)"})
    assert p["formula"] == "G(a)"


def test_provenance_records_source_and_hash():
    gp = {"id": "z", "name": "Z", "severity": "info", "formula": "f"}
    entry = {"hash": "sha256:abc", "version": "1.0.0"}
    p = gallery_to_trace_policy(gp, "acme", entry)
    assert p["source"]["source"] == "acme"
    assert p["source"]["id"] == "z"
    assert p["source"]["hash"] == "sha256:abc"


def test_provenance_defaults_to_community():
    p = gallery_to_trace_policy({"id": "z", "name": "Z", "severity": "info", "formula": "f"})
    assert p["source"]["source"] == "community"


def test_applies_when_passed_through():
    gp = {"id": "w", "name": "W", "severity": "info", "formula": "f",
          "applies_when": {"action_type": "EditFile"}}
    p = gallery_to_trace_policy(gp)
    assert p["applies_when"] == {"action_type": "EditFile"}

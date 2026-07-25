"""Unit tests for artifact lineage / provenance (ponens.lineage)."""

from ponens.lineage import (
    ancestor_ids, lineage_artifacts, lineage_types, source_symbols,
    roots_in_component, autoformalized, decomposition_backed, provenance,
)


def _trace():
    # Mirrors a real CodeLogician chain:
    #   src → IMLModel(autoformalize settle,fee_tier) → VG(target settle) → VerificationResult(proved)
    #   and a Tests artifact generated from a Decomp of fee_tier.
    return {
        "artifacts": [
            {"artifact_id": "a1", "artifact_type": "SourceCode", "name": "src", "derived_from": None},
            {"artifact_id": "a2", "artifact_type": "IMLModel", "name": "model", "derived_from": ["a1"],
             "payload": {"symbols": ["settle", "fee_tier"]}},
            {"artifact_id": "a3", "artifact_type": "VerificationGoal", "derived_from": ["a2"],
             "payload": {"target_symbol": "settle", "description": "money conserved"}},
            {"artifact_id": "a4", "artifact_type": "VerificationResult", "derived_from": ["a3"],
             "payload": {"status": "proved"}},
            {"artifact_id": "d1", "artifact_type": "Decomp", "derived_from": ["a2"],
             "payload": {"target_symbol": "fee_tier"}},
            {"artifact_id": "t1", "artifact_type": "Tests", "derived_from": ["d1"], "payload": {}},
            # An ad-hoc test suite: straight off the model, NOT via a decomposition.
            {"artifact_id": "t2", "artifact_type": "Tests", "derived_from": ["a2"], "payload": {}},
        ]
    }


def test_ancestors_transitive_closure():
    assert ancestor_ids("a4", _trace()) == {"a3", "a2", "a1"}
    assert ancestor_ids("a1", _trace()) == set()


def test_ancestors_cycle_safe():
    t = {"artifacts": [
        {"artifact_id": "x", "derived_from": ["y"]},
        {"artifact_id": "y", "derived_from": ["x"]},
    ]}
    assert ancestor_ids("x", t) == {"x", "y"}  # terminates


def test_lineage_types():
    assert lineage_types("a4", _trace()) == {"VerificationResult", "VerificationGoal", "IMLModel", "SourceCode"}


def test_source_symbols_from_structured_fields():
    syms = source_symbols("a4", _trace())
    assert "settle" in syms          # VG target_symbol
    assert "fee_tier" in syms         # IMLModel payload.symbols


def test_roots_in_component():
    t = _trace()
    assert roots_in_component("a4", "settle", t)
    assert not roots_in_component("a4", "refund", t)


def test_autoformalized():
    assert autoformalized("a4", _trace())       # IMLModel in lineage
    # A bare artifact with no model ancestor is not autoformalized.
    assert not autoformalized("a1", _trace())


def test_decomposition_backed():
    t = _trace()
    assert decomposition_backed("t1", t)         # Tests ← Decomp
    assert not decomposition_backed("t2", t)      # Tests ← model directly (ad hoc)


def test_provenance_summary():
    p = provenance("a4", _trace())
    assert p["artifact_type"] == "VerificationResult"
    assert p["autoformalized"] is True
    assert "settle" in p["source_symbols"]
    assert set(p["ancestor_ids"]) == {"a1", "a2", "a3"}
    assert provenance("missing", _trace()) is None

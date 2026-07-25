"""Effective-policy resolution — pack/policy-name refs → evaluable dicts (Goal Contract v0.1 §5).

The registry is mocked so these run offline and deterministically; the guard path is exercised too."""

import ponens.registry as reg
from ponens import goals


def _mock_registry(monkeypatch, catalog):
    """Wire a fake registry: each source name → the given catalog of policy entries; every policy has a
    formula so it's evaluable."""
    monkeypatch.setattr(reg, "get_source", lambda name: {"name": name})
    monkeypatch.setattr(reg, "source_catalog", lambda src: {"policies": catalog})
    monkeypatch.setattr(reg, "fetch_policy_from",
                        lambda src, pid, h=None, refresh=False: {"id": pid, "formula": "F", "severity": "error"})
    monkeypatch.setattr(reg, "gallery_to_trace_policy",
                        lambda gp, name, entry: {"policy_id": gp["id"], "name": gp["id"],
                                                 "formula": gp["formula"], "severity": gp["severity"]})
    monkeypatch.setattr(reg, "resolve", lambda ref: ({"name": "src"}, {"id": ref}))


def test_pack_expands_to_all_its_policies(monkeypatch):
    goals._POLICY_CACHE.clear()
    _mock_registry(monkeypatch, [{"id": "p1", "hash": "h1"}, {"id": "p2", "hash": "h2"}])
    eff = goals._effective_policies({"policies": {"packs": ["apply_formal_methods"]}})
    assert {p["policy_id"] for p in eff} == {"p1", "p2"}


def test_inline_plus_pack_plus_policy_ref_deduped(monkeypatch):
    goals._POLICY_CACHE.clear()
    _mock_registry(monkeypatch, [{"id": "p1"}])
    goal = {"policies": {
        "policies": [{"name": "inline", "formula": "X", "severity": "warning"}, "p9"],
        "packs": ["pk"],
    }}
    eff = goals._effective_policies(goal)
    ids = {(p.get("policy_id") or p.get("name")) for p in eff}
    assert ids == {"inline", "p9", "p1"}


def test_dedup_across_pack_and_explicit_ref(monkeypatch):
    goals._POLICY_CACHE.clear()
    _mock_registry(monkeypatch, [{"id": "p1"}])
    # "p1" both in the pack and named explicitly → appears once.
    eff = goals._effective_policies({"policies": {"policies": ["p1"], "packs": ["pk"]}})
    assert [p.get("policy_id") for p in eff].count("p1") == 1


def test_registry_failure_is_guarded(monkeypatch):
    goals._POLICY_CACHE.clear()

    def boom(*a, **k):
        raise SystemExit("source not available")

    monkeypatch.setattr(reg, "get_source", boom)
    # A missing/uncached pack yields nothing — enrich must not crash or hang.
    assert goals._effective_policies({"policies": {"packs": ["missing"]}}) == []


def test_policies_without_a_formula_are_skipped(monkeypatch):
    goals._POLICY_CACHE.clear()
    monkeypatch.setattr(reg, "get_source", lambda name: {"name": name})
    monkeypatch.setattr(reg, "source_catalog", lambda src: {"policies": [{"id": "nf"}]})
    monkeypatch.setattr(reg, "fetch_policy_from", lambda *a, **k: {"id": "nf"})  # no formula
    monkeypatch.setattr(reg, "gallery_to_trace_policy",
                        lambda gp, name, entry: {"policy_id": gp["id"], "formula": gp.get("formula", ""), "severity": "error"})
    assert goals._effective_policies({"policies": {"packs": ["pk"]}}) == []


def test_memoized_resolution(monkeypatch):
    goals._POLICY_CACHE.clear()
    calls = {"n": 0}

    def counting_catalog(src):
        calls["n"] += 1
        return {"policies": [{"id": "p1"}]}

    monkeypatch.setattr(reg, "get_source", lambda name: {"name": name})
    monkeypatch.setattr(reg, "source_catalog", counting_catalog)
    monkeypatch.setattr(reg, "fetch_policy_from", lambda *a, **k: {"id": "p1", "formula": "F", "severity": "error"})
    monkeypatch.setattr(reg, "gallery_to_trace_policy",
                        lambda gp, name, entry: {"policy_id": gp["id"], "formula": gp["formula"], "severity": gp["severity"]})
    goals._effective_policies({"policies": {"packs": ["pk"]}})
    goals._effective_policies({"policies": {"packs": ["pk"]}})
    assert calls["n"] == 1  # resolved once, memoized for the hot path

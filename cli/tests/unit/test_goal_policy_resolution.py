"""Effective-policy resolution — pack/policy-name refs → evaluable dicts (Goal Contract v0.2 §5).

A PACK is the set of policies whose `pack` is that id - a gallery grouping - not a policy SOURCE. The
resolver used to look a pack name up as a source, so a real pack id (`apply-formal-methods`) found no
source and expanded to nothing, silently; these tests pinned that behaviour by mocking `get_source` to
accept any name. They now mock only the configured sources and their catalogs, and exercise the real
pack lookup: membership, snake_case names, qualification, ambiguity, and what happens to a ref that
does not resolve.

The registry is mocked so these run offline and deterministically."""

import os

import ponens.registry as reg
from ponens import goals


def _catalogs(monkeypatch, by_source):
    """Wire fake sources: {source name: [catalog policy entries]}. Every fetched policy has a formula."""
    goals._POLICY_CACHE.clear()
    goals._UNRESOLVED.clear()
    monkeypatch.setattr(reg, "load_sources", lambda: [{"name": n} for n in by_source])
    monkeypatch.setattr(reg, "source_catalog", lambda src: {"policies": by_source[src["name"]]})
    monkeypatch.setattr(reg, "fetch_policy_from",
                        lambda src, pid, h=None, refresh=False: {"id": pid, "formula": "F", "severity": "error"})
    monkeypatch.setattr(reg, "gallery_to_trace_policy",
                        lambda gp, name, entry: {"policy_id": gp["id"], "name": gp["id"],
                                                 "formula": gp["formula"], "severity": gp["severity"]})


AFM = [{"id": "p1", "pack": "apply-formal-methods"}, {"id": "p2", "pack": "apply-formal-methods"},
       {"id": "other", "pack": "misra-c"}, {"id": "loose"}]


def test_pack_expands_to_exactly_its_policies(monkeypatch):
    _catalogs(monkeypatch, {"community": AFM})
    eff = goals._effective_policies({"policies": {"packs": ["apply-formal-methods"]}})
    assert {p["policy_id"] for p in eff} == {"p1", "p2"}


def test_snake_case_pack_names_the_same_pack(monkeypatch):
    # The Goal Contract spec and the agent guide wrote `apply_formal_methods`; the gallery id is kebab.
    _catalogs(monkeypatch, {"community": AFM})
    eff = goals._effective_policies({"policies": {"packs": ["apply_formal_methods"]}})
    assert {p["policy_id"] for p in eff} == {"p1", "p2"}


def test_a_source_name_is_not_a_pack(monkeypatch):
    # The old resolver expanded a SOURCE: `packs: ["community"]` pulled in every policy it holds.
    _catalogs(monkeypatch, {"community": AFM})
    goal = {"policies": {"packs": ["community"]}}
    assert goals._effective_policies(goal) == []
    assert goals.unresolved_refs(goal)[0]["ref"] == "community"


def test_qualified_pack_and_ambiguity(monkeypatch):
    _catalogs(monkeypatch, {"community": AFM, "acme": [{"id": "a1", "pack": "apply-formal-methods"}]})
    ambiguous = {"policies": {"packs": ["apply-formal-methods"]}}
    assert goals._effective_policies(ambiguous) == []
    assert "qualify it" in goals.unresolved_refs(ambiguous)[0]["reason"]
    eff = goals._effective_policies({"policies": {"packs": ["acme/apply-formal-methods"]}})
    assert [p["policy_id"] for p in eff] == ["a1"]


def test_inline_plus_pack_plus_policy_ref_deduped(monkeypatch):
    _catalogs(monkeypatch, {"community": AFM + [{"id": "p9"}]})
    goal = {"policies": {
        "policies": [{"name": "inline", "formula": "X", "severity": "warning"}, "p9"],
        "packs": ["apply-formal-methods"],
    }}
    ids = {(p.get("policy_id") or p.get("name")) for p in goals._effective_policies(goal)}
    assert ids == {"inline", "p9", "p1", "p2"}


def test_dedup_across_pack_and_explicit_ref(monkeypatch):
    _catalogs(monkeypatch, {"community": AFM})
    eff = goals._effective_policies({"policies": {"policies": ["p1"], "packs": ["apply-formal-methods"]}})
    assert [p.get("policy_id") for p in eff].count("p1") == 1


def test_an_unknown_ref_is_reported_not_silent(monkeypatch):
    _catalogs(monkeypatch, {"community": AFM})
    goal = {"policies": {"packs": ["no-such-pack"], "policies": ["no_such_policy"]}}
    assert goals._effective_policies(goal) == []
    got = {(u["kind"], u["ref"]): u["reason"] for u in goals.unresolved_refs(goal)}
    assert "not found" in got[("pack", "no-such-pack")]
    assert "not found" in got[("policy", "no_such_policy")]


def test_registry_failure_is_guarded_and_reported(monkeypatch):
    goals._POLICY_CACHE.clear()
    goals._UNRESOLVED.clear()

    def boom():
        raise SystemExit("sources unreadable")

    monkeypatch.setattr(reg, "load_sources", boom)
    goal = {"policies": {"packs": ["apply-formal-methods"]}}
    # Enrich must not crash or hang on a broken registry - and must not pretend nothing was declared.
    assert goals._effective_policies(goal) == []
    assert goals.unresolved_refs(goal)[0]["kind"] == "pack"


def test_policies_without_a_formula_are_skipped(monkeypatch):
    _catalogs(monkeypatch, {"community": AFM})
    monkeypatch.setattr(reg, "fetch_policy_from", lambda *a, **k: {"id": "nf"})  # no formula
    monkeypatch.setattr(reg, "gallery_to_trace_policy",
                        lambda gp, name, entry: {"policy_id": gp["id"], "formula": gp.get("formula", ""), "severity": "error"})
    assert goals._effective_policies({"policies": {"packs": ["apply-formal-methods"]}}) == []


def test_memoized_resolution(monkeypatch):
    _catalogs(monkeypatch, {"community": AFM})
    calls = {"n": 0}
    real = reg.source_catalog

    def counting(src):
        calls["n"] += 1
        return real(src)

    monkeypatch.setattr(reg, "source_catalog", counting)
    goals._effective_policies({"policies": {"packs": ["apply-formal-methods"]}})
    goals._effective_policies({"policies": {"packs": ["apply-formal-methods"]}})
    assert calls["n"] == 1  # resolved once, memoized for the hot path


def test_enrich_marks_a_goal_with_unresolved_governance_as_not_governed(monkeypatch):
    _catalogs(monkeypatch, {"community": AFM})
    trace = {"actions": [], "artifacts": [],
             "goals": [{"id": "g", "intent": "i", "acceptance": [],
                        "policies": {"packs": ["no-such-pack"]}}]}
    g = goals.enrich(trace)["goals"][0]
    assert g["governed"] is False
    assert g["governance_unresolved"][0]["ref"] == "no-such-pack"


def test_local_source_entries_carry_their_pack(tmp_path):
    # A local source's catalog is built from its files; without `pack` on each entry its packs could
    # be listed but never resolved.
    (tmp_path / "p1.json").write_text('{"id": "p1", "name": "P1", "severity": "error", "pack": "mine"}')
    cat = reg._local_catalog({"name": "local", "type": "local", "path": str(tmp_path)})
    assert cat["policies"][0]["pack"] == "mine"


def test_check_strict_gates_a_goal_without_trace_level_policies(monkeypatch, tmp_path, capsys):
    # `check` returned "No policies to check." before looking at goals whenever the record carried
    # no trace-level policies, so a goal whose declared pack did not resolve passed `--strict`.
    import argparse
    import json
    from ponens.trace import cmd_check
    _catalogs(monkeypatch, {"community": AFM})
    fx = os.path.join(os.path.dirname(__file__), "..", "fixtures", "stripe-demo-trace.json")
    t = json.load(open(fx))
    t["policies"] = []
    t["goals"] = [{"id": "g", "intent": "i", "acceptance": [], "policies": {"packs": ["no-such-pack"]}}]
    f = tmp_path / "t.json"
    f.write_text(json.dumps(t))
    args = argparse.Namespace(trace_file=str(f), policy_file=None, strict=True, json=False, write=False)
    assert cmd_check(args) == 1
    assert "no-such-pack' could not be resolved" in capsys.readouterr().out

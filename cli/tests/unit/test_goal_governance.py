"""The GOVERNED axis — policies over a goal's cone (Goal Contract v0.1 §5-6, ponens.goals).

`governance_of`'s composition (severity blocking, disabled overrides) is tested against a patched
`evaluate_policy` — the DSL evaluator has its own tests; here we pin the goal-scoped logic."""

import ponens.trace as traceops
from ponens.goals import cone_trace, governance_of, enrich


def _trace():
    return {
        "actions": [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 99}],  # 99 is outside the goal's cone
        "high_stakes_paths": ["settle"],
        "artifacts": [
            {"artifact_id": "src", "artifact_type": "SourceCode", "producer_action_id": 1, "derived_from": None},
            {"artifact_id": "model", "artifact_type": "IMLModel", "producer_action_id": 2, "derived_from": ["src"],
             "payload": {"symbols": ["settle"]}},
            {"artifact_id": "vr", "artifact_type": "VerificationResult", "producer_action_id": 3, "derived_from": ["model"],
             "payload": {"status": "proved"}},
            {"artifact_id": "unrelated", "artifact_type": "Diff", "producer_action_id": 99, "derived_from": None},
        ],
    }


def _goal():
    # An acceptance item already resolved to `vr` (as enrich sets it) — this seeds the cone.
    return {"id": "g", "scope": [], "acceptance": [{"id": "c1", "component": {"function": "settle"}, "evidence": "vr"}]}


def test_cone_trace_projects_to_the_goal_cone():
    ct = cone_trace(_goal(), _trace())
    ids = {a["artifact_id"] for a in ct["artifacts"]}
    assert ids == {"vr", "model", "src"}              # evidence + its lineage
    assert "unrelated" not in ids                       # an unrelated component is excluded
    assert {a["id"] for a in ct["actions"]} == {1, 2, 3}
    assert ct.get("high_stakes_paths") == ["settle"]   # trace-level context preserved


def test_error_failure_blocks_done(monkeypatch):
    monkeypatch.setattr(traceops, "evaluate_policy",
                        lambda pol, tr: (("failed", None) if pol["name"] == "bad" else ("passed", None)))
    r = governance_of(_goal(), _trace(), [
        {"name": "bad", "severity": "error", "formula": "x"},
        {"name": "ok", "severity": "warning", "formula": "y"},
    ])
    assert r["governed"] is False
    assert r["blocking"] == ["bad"]


def test_warning_failure_does_not_block(monkeypatch):
    monkeypatch.setattr(traceops, "evaluate_policy", lambda pol, tr: ("failed", None))
    r = governance_of(_goal(), _trace(), [{"name": "w", "severity": "warning", "formula": "x"}])
    assert r["governed"] is True
    assert r["blocking"] == []


def test_disabled_policy_recorded_but_not_evaluated(monkeypatch):
    monkeypatch.setattr(traceops, "evaluate_policy", lambda pol, tr: ("failed", None))  # would block if run
    g = _goal()
    g["policies"] = {"disabled": ["bad"]}
    r = governance_of(g, _trace(), [{"name": "bad", "severity": "error", "formula": "x"}])
    assert r["governed"] is True                        # disabled → not blocking
    assert r["evaluations"][0]["status"] == "disabled"


def test_all_pass_is_governed(monkeypatch):
    monkeypatch.setattr(traceops, "evaluate_policy", lambda pol, tr: ("passed", None))
    r = governance_of(_goal(), _trace(), [{"name": "ok", "severity": "error", "formula": "x"}])
    assert r["governed"] is True


def test_enrich_attaches_governed(monkeypatch):
    monkeypatch.setattr(traceops, "evaluate_policy", lambda pol, tr: ("failed", None))
    t = _trace()
    t["goals"] = [{
        "id": "g", "scope": [],
        "acceptance": [{"id": "c1", "component": {"function": "settle"},
                        "evidence": {"kind": "verification", "property": "money_conserved", "expect": "proved"}}],
        "policies": {"policies": [{"name": "bad", "severity": "error", "formula": "x"}]},
    }]
    e = enrich(t)
    g = e["goals"][0]
    assert "governed" in g          # governed axis attached from declared policies
    assert g["governed"] is False   # an error policy fails → not governed
    assert g["governance"][0]["severity"] == "error"


def test_enrich_no_policies_no_governed_field():
    t = _trace()
    t["goals"] = [{"id": "g", "scope": [], "acceptance": []}]
    g = enrich(t)["goals"][0]
    assert "governed" not in g      # nothing declared → axis absent (not vacuously true/false)

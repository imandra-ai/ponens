"""Unit tests for goal operations over a trace (ponens.goals)."""

from ponens.goals import (
    resolve_item, progress_of, stale_evidence,
    goal_relevant_actions, unattributed_actions, goal_residuals, enrich, faithfulness_of,
)


def _trace():
    # A tiny trace: a property proved (vr1, from vg1), then a LATER edit to `foo` (d1) -> stale.
    return {
        "trace_id": "t",
        "actions": [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 9}],
        "artifacts": [
            {"artifact_id": "vg1", "artifact_type": "VerificationGoal", "producer_action_id": 1,
             "payload": {"goal_id": "G1", "target_symbol": "foo", "description": "amount invariant holds"}},
            {"artifact_id": "vr1", "artifact_type": "VerificationResult", "producer_action_id": 2,
             "derived_from": ["vg1"], "payload": {"goal_id": "G1", "goal_artifact_id": "vg1", "status": "proved"}},
            {"artifact_id": "d1", "artifact_type": "Diff", "producer_action_id": 3,
             "name": "edit foo", "summary": "changed foo"},
        ],
        "residuals": [{"residual_id": "r1", "status": "open", "severity": "high", "statement": "gap about foo"}],
        "policy_evaluations": [{"policy_id": "p1", "status": "passed"}],
        "goals": [{
            "id": "g", "intent": "do foo", "scope": ["foo"], "status": "active",
            "acceptance": [
                {"id": "a1", "kind": "property", "label": "amount", "status": "todo", "binding": {"property": "amount"}},
                {"id": "a2", "kind": "change", "label": "edit foo", "status": "todo", "binding": {"symbol": "foo"}},
                {"id": "a3", "kind": "gap", "label": "gap", "status": "todo", "binding": {"residual_id": "r1"}},
                {"id": "a4", "kind": "obligation", "label": "pol", "status": "todo", "binding": {"policy_id": "p1"}},
            ],
        }],
    }


def test_resolve_each_kind():
    t = _trace()
    items = {i["id"]: i for i in t["goals"][0]["acceptance"]}
    assert resolve_item(items["a1"], t)["status"] == "done"    # property proved
    assert resolve_item(items["a2"], t)["status"] == "done"    # change touched foo
    assert resolve_item(items["a3"], t)["status"] == "todo"    # gap residual still open
    assert resolve_item(items["a4"], t)["status"] == "done"    # obligation policy passed


def test_resolve_property_latest_result_wins():
    t = _trace()
    # add a LATER refuted result for the same goal -> latest wins, but here proved is at step 2;
    # add an even-later proved to confirm ordering picks the newest proved
    t["artifacts"].append({"artifact_id": "vr2", "artifact_type": "VerificationResult",
                           "producer_action_id": 8, "payload": {"goal_id": "G1", "goal_artifact_id": "vg1",
                                                                 "status": "refuted"}})
    item = t["goals"][0]["acceptance"][0]
    # newest result (step 8) is refuted -> blocked
    assert resolve_item(item, t)["status"] == "blocked"


def test_resolve_unbound_falls_back():
    t = _trace()
    r = resolve_item({"id": "x", "kind": "property", "status": "doing"}, t)  # no binding
    assert r == {"status": "doing", "from_trace": False, "evidence": None}


def test_progress():
    # a1 done, a2 done, a3 todo, a4 done -> 3/4
    t = _trace()
    items = [dict(i, status=resolve_item(i, t)["status"]) for i in t["goals"][0]["acceptance"]]
    assert progress_of(items) == 0.75


def test_stale_evidence_fires_on_later_edit():
    t = _trace()
    stale = stale_evidence(t)
    assert len(stale) == 1
    assert stale[0]["residual_id"] == "stale-vr1"
    assert stale[0]["derived"] is True
    assert stale[0]["target"]["target_id"] == "vr1"


def test_stale_evidence_none_when_no_later_edit():
    t = _trace()
    t["artifacts"][2]["producer_action_id"] = 1  # move the edit BEFORE the proof (step 2)
    assert stale_evidence(t) == []


def test_enrich_flags_met_but_stale_criterion_at_risk():
    # Living goal guard (Phase 1): a1 is proved (met) but its symbol `foo` changed after the proof,
    # so enrich marks it AT RISK — still `done`, but the guarantee no longer reflects the code.
    t = enrich(_trace())
    g = t["goals"][0]
    a1 = next(i for i in g["acceptance"] if i["id"] == "a1")
    assert a1["status"] == "done"                       # still met — the evidence exists
    assert a1.get("at_risk") is True                    # but the proof is stale
    assert "stale" in (a1.get("at_risk_reason") or "").lower()
    assert a1.get("at_risk_residual_id") == "stale-vr1"  # links to the derived residual
    # The change criterion a2 (evidence is a Diff, not a proof) is NOT at risk — only proofs go stale here.
    a2 = next(i for i in g["acceptance"] if i["id"] == "a2")
    assert a2["status"] == "done" and not a2.get("at_risk")
    assert g["at_risk"] == 1
    assert t["summary"]["goals_at_risk"] == 1
    assert t["summary"]["criteria_at_risk"] == 1


def test_enrich_no_at_risk_when_evidence_is_fresh():
    t = _trace()
    t["artifacts"][2]["producer_action_id"] = 1  # edit BEFORE the proof -> proof is fresh, not stale
    t = enrich(t)
    g = t["goals"][0]
    a1 = next(i for i in g["acceptance"] if i["id"] == "a1")
    assert a1["status"] == "done" and not a1.get("at_risk")
    assert g["at_risk"] == 0
    assert t["summary"]["goals_at_risk"] == 0
    assert t["summary"]["criteria_at_risk"] == 0


def _reprove(t, status, step=5):
    """Simulate the user kicking off a MANUAL re-verify: a fresh result of `foo` lands after the edit."""
    t["actions"].append({"id": step})
    t["artifacts"].append({"artifact_id": "vr2", "artifact_type": "VerificationResult",
                           "producer_action_id": step, "derived_from": ["vg1"],
                           "payload": {"goal_id": "G1", "goal_artifact_id": "vg1", "status": status}})
    return t


def test_manual_reprove_heals_at_risk():
    # Start stale (a1 at risk), then the user re-verifies and it PROVES against the current code.
    assert enrich(_trace())["goals"][0]["acceptance"][0]["at_risk"] is True  # precondition
    e = enrich(_reprove(_trace(), "proved"))
    g = e["goals"][0]
    a1 = next(i for i in g["acceptance"] if i["id"] == "a1")
    assert a1["status"] == "done" and not a1.get("at_risk")   # healed — guarantee restored
    assert g["at_risk"] == 0
    assert e["summary"]["criteria_at_risk"] == 0
    assert not any(r.get("residual_id") == "stale-vr1" for r in e["residuals"])  # superseded proof gone


def test_at_risk_from_hash_freshness_external_edit():
    # An EXTERNAL on-disk edit leaves no Diff on the trace, so structural stale_evidence can't see it —
    # but the extension stamps `artifact_freshness` (store-ref -> stale). enrich must map the criterion's
    # evidence (vr1, exported id) back to its store ref and flag at_risk. Move the edit before the proof
    # so the ONLY staleness signal is freshness, not stale_evidence.
    t = _trace()
    t["artifacts"][2]["producer_action_id"] = 1  # kill structural staleness (edit precedes proof)
    t["artifact_freshness"] = {"vr1": "stale"}    # extension re-hashed the source: proof is stale
    e = enrich(t)
    a1 = next(i for i in e["goals"][0]["acceptance"] if i["id"] == "a1")
    assert a1["status"] == "done" and a1.get("at_risk") is True
    assert "changed" in (a1.get("at_risk_reason") or "").lower()
    assert e["summary"]["criteria_at_risk"] == 1


def test_at_risk_from_freshness_prefix_mapping():
    # Freshness is keyed by the STORE ref (`fr1`); the exported VR id is `fr1-result-3`. The prefix map
    # must resolve it. (Rename vr1 -> fr1-result-3 and key freshness on the ref.)
    t = _trace()
    t["artifacts"][2]["producer_action_id"] = 1
    t["artifacts"][1]["artifact_id"] = "fr1-result-3"  # exported-style id
    # a1 (property) resolves to the latest matching VR by goal — still this one.
    t["artifact_freshness"] = {"fr1": "gone"}
    e = enrich(t)
    a1 = next(i for i in e["goals"][0]["acceptance"] if i["id"] == "a1")
    assert a1.get("at_risk") is True
    assert "removed" in (a1.get("at_risk_reason") or "").lower()  # 'gone' -> removed


def test_manual_reprove_that_refutes_becomes_issue_not_at_risk():
    # The re-verify against the changed code REFUTES: the criterion is a live ISSUE (blocked), not "at risk".
    e = enrich(_reprove(_trace(), "refuted"))
    g = e["goals"][0]
    a1 = next(i for i in g["acceptance"] if i["id"] == "a1")
    assert a1["status"] == "blocked"      # broken — the fresh check refutes
    assert not a1.get("at_risk")          # not "at risk"; it's a live issue now
    assert g["at_risk"] == 0


def test_relevance_cone_and_exploration():
    t = _trace()
    cone = goal_relevant_actions(t["goals"][0], t)
    assert cone == {1, 2, 3}          # vg1(1), vr1(2), d1(3) via seeds + lineage
    assert unattributed_actions(t) == {9}  # action 9 produced nothing on-goal


def test_goal_residuals_declared_plus_derived():
    t = _trace()
    rs = goal_residuals(t["goals"][0], t)
    ids = {r["residual_id"] for r in rs}
    assert "r1" in ids and "stale-vr1" in ids  # declared (bound) + derived (in scope)


def test_enrich_end_to_end():
    t = _trace()
    e = enrich(t)
    g = e["goals"][0]
    assert g["progress"] == 0.75
    assert g["cone"] == [1, 2, 3]
    assert g["open_gaps"] == 2                      # r1 + stale-vr1
    assert e["exploration_actions"] == [9]
    assert any(r.get("derived") for r in e["residuals"])   # stale merged in
    assert e["summary"] == {
        "policy_violations": 0, "open_residuals": 2, "open_high": 1, "stale_evidence": 1,
        "goals_total": 1, "goals_met": 0, "goals_governed": 0, "goals_certified": 0,
        "goals_at_risk": 1, "criteria_at_risk": 1}
    assert {i["id"]: i["status"] for i in g["acceptance"]} == {
        "a1": "done", "a2": "done", "a3": "todo", "a4": "done"}
    # source trace untouched
    assert "progress" not in t["goals"][0]


# ---- faithfulness: is the definition of done RIGHT, not just met? -------------------------------

def _fgoal(acceptance, **kw):
    return {"id": "g", "intent": "i", "scope": [], "acceptance": acceptance, **kw}


def test_faithfulness_met_over_required_items():
    done = {"id": "a", "kind": "property", "status": "done"}
    todo = {"id": "b", "kind": "property", "status": "todo"}
    opt = {"id": "c", "kind": "change", "status": "todo", "required": False}
    assert faithfulness_of(_fgoal([done]))["met"] is True
    assert faithfulness_of(_fgoal([done, todo]))["met"] is False
    # a non-required undone item does not block `met`
    assert faithfulness_of(_fgoal([done, opt]))["met"] is True
    assert faithfulness_of(_fgoal([]))["met"] is False


def test_faithfulness_no_longer_grades_strength():
    # Strength ("is a diff enough vs a proof?") is a POLICY judgment now — faithfulness no longer
    # reports weakly_specified at all, regardless of the evidence mix.
    f = faithfulness_of(_fgoal([{"kind": "change", "status": "done"}]))
    assert "weakly_specified" not in f
    assert set(f) == {"met", "certified", "uncovered_clauses"}


def test_faithfulness_uncovered_clauses():
    g = _fgoal([{"kind": "property", "status": "done", "covers": ["a"]}], intent_clauses=["a", "b"])
    assert faithfulness_of(g)["uncovered_clauses"] == ["b"]


def test_faithfulness_certified_gate():
    acc = [{"kind": "property", "status": "done", "author": "agent", "covers": ["a"]}]
    ok = {"reviewed_by": "reviewer", "verdict": "approved"}
    assert faithfulness_of(_fgoal(acc, intent_clauses=["a"], criteria_review=ok))["certified"] is True
    # the doer cannot certify their own bar
    self_rev = {"reviewed_by": "agent", "verdict": "approved"}
    assert faithfulness_of(_fgoal(acc, intent_clauses=["a"], criteria_review=self_rev))["certified"] is False
    # an uncovered clause can never be certified
    assert faithfulness_of(_fgoal(acc, intent_clauses=["a", "b"], criteria_review=ok))["certified"] is False
    # strength no longer gates certified — a change-backed goal, reviewed and covered, IS certified
    # (whether a diff is ENOUGH is a policy/governed judgment, not a faithfulness one)
    change = [{"kind": "change", "status": "done", "author": "agent", "covers": ["a"]}]
    assert faithfulness_of(_fgoal(change, intent_clauses=["a"], criteria_review=ok))["certified"] is True
    # no review -> not certified (orthogonal to met)
    assert faithfulness_of(_fgoal(acc, intent_clauses=["a"]))["certified"] is False


def test_enrich_grades_faithfulness_orthogonal_to_met():
    t = _trace()
    g = t["goals"][0]
    g["intent_clauses"] = ["amount holds"]
    for a in g["acceptance"]:
        a["author"] = "agent"
    g["acceptance"][0]["covers"] = ["amount holds"]
    g["criteria_review"] = {"reviewed_by": "reviewer", "verdict": "approved"}
    e = enrich(t)
    fa = e["goals"][0]["faithfulness"]
    # a3 (gap) is still open -> not met, but the DEFINITION is certified (right, if not yet done)
    assert fa["met"] is False
    assert fa["certified"] is True
    assert fa["uncovered_clauses"] == []
    assert e["summary"]["goals_total"] == 1 and e["summary"]["goals_certified"] == 1
    assert e["summary"]["goals_met"] == 0


# ── Freshness via dependency-closure checksum + Detached (TRACE_SPEC §18.3) ──────

def _fp_trace(models):
    """A trace with a proved result for `f` (step 2) plus the given FormalModel artifacts."""
    return {
        "trace_id": "t", "actions": [{"id": i} for i in (1, 2, 3)],
        "artifacts": [
            {"artifact_id": "vg1", "artifact_type": "VerificationGoal", "producer_action_id": 1,
             "payload": {"goal_id": "G1", "target_symbol": "f", "description": "f invariant"}},
            {"artifact_id": "vr1", "artifact_type": "VerificationResult", "producer_action_id": 2,
             "derived_from": ["vg1"], "payload": {"goal_id": "G1", "goal_artifact_id": "vg1", "status": "proved"}},
        ] + models,
    }


def _model(aid, step, code, syms):
    return {"artifact_id": aid, "artifact_type": "FormalModel", "producer_action_id": step,
            "payload": {"formal_code": code, "symbols": syms}}


def test_closure_stale_on_dependency_change():
    # f uses g; a LATER model changes g's body (f's own text is untouched). Closure of f = {f, g},
    # so the checksum moves -> stale. (The old substring heuristic would MISS this.)
    t = _fp_trace([
        _model("m0", 1, "let g x = x + 1\nlet f x = g x", ["f", "g"]),
        _model("m2", 3, "let g x = x + 2\nlet f x = g x", ["f", "g"]),
    ])
    stale = stale_evidence(t)
    assert [r["residual_id"] for r in stale] == ["stale-vr1"]
    assert stale[0]["kind"] == "stale_evidence"


def test_closure_fresh_on_unrelated_change():
    # A later model changes h only; f's closure ({f, g}) is unchanged -> fresh, no residual.
    t = _fp_trace([
        _model("m0", 1, "let g x = x + 1\nlet f x = g x\nlet h x = x - 1", ["f", "g", "h"]),
        _model("m2", 3, "let g x = x + 1\nlet f x = g x\nlet h x = x - 99", ["f", "g", "h"]),
    ])
    assert stale_evidence(t) == []


def test_detached_when_symbol_removed_from_model():
    # The current model no longer declares f -> the proof is Detached, not merely stale.
    t = _fp_trace([
        _model("m0", 1, "let g x = x + 1\nlet f x = g x", ["f", "g"]),
        _model("m2", 3, "let g x = x + 2", ["g"]),
    ])
    stale = stale_evidence(t)
    assert [r["residual_id"] for r in stale] == ["detached-vr1"]
    assert stale[0]["kind"] == "detached_evidence"
    assert stale[0]["severity"] == "high"


def test_explicit_producer_fingerprint_is_honored():
    # The result carries a producer fingerprint whose task_checksum won't match the current model's
    # closure checksum -> stale, without reconstructing the prior model.
    t = _fp_trace([_model("m2", 3, "let g x = x + 2\nlet f x = g x", ["f", "g"])])
    t["artifacts"][1]["payload"]["fingerprint"] = {"task_checksum": "sha256:stale-value"}
    stale = stale_evidence(t)
    assert [r["residual_id"] for r in stale] == ["stale-vr1"]


def _iml_model(aid, step, code, syms, src="src1"):
    """A producer-shaped model: IMLModel, inline source under `iml_code`, derived from a source node."""
    return {"artifact_id": aid, "artifact_type": "IMLModel", "producer_action_id": step,
            "derived_from": [src], "payload": {"iml_code": code, "symbols": syms}}


def test_freshness_reads_producer_iml_code_field():
    # The producer inlines the model as `iml_code` (not the spec's `formal_code`); freshness must still
    # fire — a change in f's dependency g marks the proof stale, via the SAME closure logic.
    t = _fp_trace([
        _iml_model("m0", 1, "let g x = x + 1\nlet f x = g x", ["f", "g"]),
        _iml_model("m2", 3, "let g x = x + 2\nlet f x = g x", ["f", "g"]),
    ])
    assert [r["residual_id"] for r in stale_evidence(t)] == ["stale-vr1"]


def test_no_false_detached_across_focused_per_file_models():
    # The producer emits ONE model per formalization run (per file). A later focused model for a
    # DIFFERENT file (different source line) must NOT mark f's proof detached — f was never in it.
    t = _fp_trace([
        _iml_model("mA", 1, "let f x = x + 1", ["f"], src="srcA"),
        _iml_model("mB", 5, "let tax y = y * 2", ["tax"], src="srcB"),
    ])
    assert stale_evidence(t) == []


def test_freshness_is_generic_state_space_analysis_goes_stale():
    # Generic (TRACE_SPEC §18.3): a region decomposition (StateSpaceAnalysisResult) — not just a proof
    # — goes stale when the model it ran on changes (here `g`, in `f`'s dependency closure).
    t = {
        "trace_id": "t", "actions": [{"id": i} for i in (1, 2, 3)],
        "artifacts": [
            {"artifact_id": "ssa1", "artifact_type": "StateSpaceAnalysisResult", "producer_action_id": 2,
             "payload": {"target_symbol": "f", "analysis_kind": "region_decomposition"}},
            _model("m0", 1, "let g x = x + 1\nlet f x = g x", ["f", "g"]),
            _model("m2", 3, "let g x = x + 2\nlet f x = g x", ["f", "g"]),
        ],
    }
    stale = stale_evidence(t)
    assert [r["residual_id"] for r in stale] == ["stale-ssa1"]
    assert stale[0]["kind"] == "stale_evidence"
    assert "state-space analysis" in stale[0]["statement"].lower()


def test_freshness_generic_detached_state_space_analysis():
    # And Detached applies too: the decomposition's target is gone from the current model.
    t = {
        "trace_id": "t", "actions": [{"id": i} for i in (1, 2, 3)],
        "artifacts": [
            {"artifact_id": "ssa1", "artifact_type": "StateSpaceAnalysisResult", "producer_action_id": 2,
             "payload": {"target_symbol": "f", "analysis_kind": "region_decomposition"}},
            _model("m0", 1, "let f x = x", ["f"]),
            _model("m2", 3, "let g x = x", ["g"]),
        ],
    }
    stale = stale_evidence(t)
    assert [r["residual_id"] for r in stale] == ["detached-ssa1"]
    assert stale[0]["kind"] == "detached_evidence"


# ── Counter-evidence: an open Defeater contests a proof (TRACE_SPEC §13 / §18.2) ──

def _defeater_art(rid, target_id, status="open", dkind="rebuts"):
    from ponens import lineage
    return lineage.residual_to_artifact({
        "residual_id": rid, "kind": "defeater", "defeater_kind": dkind,
        "statement": "counter-evidence", "status": status,
        "target": {"target_type": "artifact", "target_id": target_id}})


def test_open_defeater_blocks_proved_property():
    t = _trace()
    items = {i["id"]: i for i in t["goals"][0]["acceptance"]}
    assert resolve_item(items["a1"], t)["status"] == "done"       # proved, uncontested
    t["artifacts"].append(_defeater_art("rd1", "vr1"))            # open rebuttal of the result
    assert resolve_item(items["a1"], t)["status"] == "blocked"    # now contested


def test_addressed_defeater_does_not_block():
    t = _trace()
    items = {i["id"]: i for i in t["goals"][0]["acceptance"]}
    t["artifacts"].append(_defeater_art("rd1", "vr1", status="addressed"))
    assert resolve_item(items["a1"], t)["status"] == "done"       # resolved defeater no longer blocks


def test_defeater_kind_carried_through_surface():
    from ponens import lineage
    art = lineage.residual_to_artifact({"residual_id": "x", "kind": "defeater",
        "defeater_kind": "undermines", "statement": "model != code", "status": "open"})
    r = lineage.artifact_to_residual(art)
    assert r["kind"] == "defeater" and r["defeater_kind"] == "undermines"

"""Typed acceptance criteria resolved by lineage — Goal Contract v0.1 §4 (ponens.goals).

A criterion is `component` + `evidence: {artifact: <type>}`. It is MET when an artifact of that TYPE
roots in the component's lineage — nothing more. Whether the evidence was derived CORRECTLY (proved,
autoformalized, tests pass, enough regions) is a POLICY judgment (the governed axis), NOT decided here.
"""

from ponens.goals import resolve_item


def _trace():
    # src → IMLModel(settle, fee_tier, refund) → VGs/Decomp → results/tests, plus a bare Diff.
    return {
        "actions": [{"id": i} for i in range(1, 20)],
        "artifacts": [
            {"artifact_id": "src", "artifact_type": "SourceCode", "derived_from": None, "producer_action_id": 1},
            {"artifact_id": "model", "artifact_type": "IMLModel", "derived_from": ["src"], "producer_action_id": 2,
             "payload": {"symbols": ["settle", "fee_tier", "refund"]}},
            # settle: money_conserved PROVED
            {"artifact_id": "vg1", "artifact_type": "VerificationGoal", "derived_from": ["model"], "producer_action_id": 3,
             "payload": {"goal_id": "g1", "target_symbol": "settle", "property_name": "money_conserved"}},
            {"artifact_id": "vr1", "artifact_type": "VerificationResult", "derived_from": ["vg1"], "producer_action_id": 4,
             "payload": {"goal_id": "g1", "goal_artifact_id": "vg1", "status": "proved"}},
            # refund: refund_nonneg REFUTED (quality is a policy concern — met still holds)
            {"artifact_id": "vg2", "artifact_type": "VerificationGoal", "derived_from": ["model"], "producer_action_id": 5,
             "payload": {"goal_id": "g2", "target_symbol": "refund", "property_name": "refund_nonneg"}},
            {"artifact_id": "vr2", "artifact_type": "VerificationResult", "derived_from": ["vg2"], "producer_action_id": 6,
             "payload": {"goal_id": "g2", "goal_artifact_id": "vg2", "status": "refuted"}},
            # fee_tier: a decomposition + a test suite generated FROM it
            {"artifact_id": "dec", "artifact_type": "Decomp", "derived_from": ["model"], "producer_action_id": 7,
             "payload": {"target_symbol": "fee_tier", "region_count": 5}},
            {"artifact_id": "tests", "artifact_type": "Tests", "derived_from": ["dec"], "producer_action_id": 8,
             "payload": {"count": 12, "failing": 0}},
            # settle also has a bare Diff (informal evidence)
            {"artifact_id": "diff1", "artifact_type": "Diff", "derived_from": ["src"], "producer_action_id": 9,
             "payload": {"target_symbol": "settle"}},
        ],
    }


def crit(component, artifact):
    return {"id": "c", "component": {"function": component}, "evidence": {"artifact": artifact}}


# --- MET = the required artifact type is present in the component's lineage -----------------

def test_verification_result_present_is_met():
    r = resolve_item(crit("settle", "VerificationResult"), _trace())
    assert r["status"] == "done"
    assert r["evidence"] == "vr1"


def test_met_does_not_judge_quality_refuted_still_met():
    # A refuted result still satisfies "settle has a VerificationResult" — quality is the governed axis.
    r = resolve_item(crit("refund", "VerificationResult"), _trace())
    assert r["status"] == "done"
    assert r["evidence"] == "vr2"


def test_tests_artifact_present_is_met():
    r = resolve_item(crit("fee_tier", "Tests"), _trace())
    assert r["status"] == "done"
    assert r["evidence"] == "tests"


def test_decomposition_artifact_present_is_met():
    r = resolve_item(crit("fee_tier", "Decomp"), _trace())
    assert r["status"] == "done"
    assert r["evidence"] == "dec"


def test_informal_diff_artifact_is_met():
    # Evidence need not be formal — a plain Diff over the component counts as met.
    r = resolve_item(crit("settle", "Diff"), _trace())
    assert r["status"] == "done"
    assert r["evidence"] == "diff1"


def test_artifact_type_is_case_insensitive():
    r = resolve_item(crit("settle", "verificationresult"), _trace())
    assert r["status"] == "done"


# --- Not met -------------------------------------------------------------------------------

def test_missing_artifact_type_stays_todo():
    # settle has no Decomp in its lineage.
    r = resolve_item(crit("settle", "Decomp"), _trace())
    assert r == {"status": "todo", "from_trace": False, "evidence": None}


def test_wrong_component_stays_todo():
    r = resolve_item(crit("nonexistent", "VerificationResult"), _trace())
    assert r == {"status": "todo", "from_trace": False, "evidence": None}


# --- Symbol alias: the engine renamed the symbol out from under the source name ------------
# A criterion may name the source `function` (author's name, for display) AND a formal `symbol` —
# the name the engine actually gave the formalization (e.g. source `money_transfer` proved as
# `settle`). The attribution reconciler stamps `component.symbol` when the two diverge; resolution
# then binds on EITHER, so the criterion resolves without discarding the human-authored name.

def test_component_symbol_alias_resolves_when_function_name_differs():
    item = {"id": "c", "component": {"function": "money_transfer", "symbol": "settle"},
            "evidence": {"artifact": "VerificationResult"}}
    r = resolve_item(item, _trace())
    assert r["status"] == "done"
    assert r["evidence"] == "vr1"


def test_component_symbol_alias_still_todo_when_neither_name_matches():
    item = {"id": "c", "component": {"function": "money_transfer", "symbol": "also_wrong"},
            "evidence": {"artifact": "VerificationResult"}}
    r = resolve_item(item, _trace())
    assert r == {"status": "todo", "from_trace": False, "evidence": None}


def test_component_function_alone_still_resolves_unchanged():
    # The common case (only `function`, no `symbol`) must be untouched by the alias support.
    r = resolve_item(crit("settle", "VerificationResult"), _trace())
    assert r["status"] == "done" and r["evidence"] == "vr1"


def test_latest_artifact_of_type_wins():
    t = _trace()
    t["artifacts"].append(
        {"artifact_id": "vr1b", "artifact_type": "VerificationResult", "derived_from": ["vg1"],
         "producer_action_id": 40, "payload": {"goal_id": "g1", "goal_artifact_id": "vg1", "status": "proved"}})
    r = resolve_item(crit("settle", "VerificationResult"), t)
    assert r["evidence"] == "vr1b"  # newest by producer_action_id


# --- Tolerant aliases + backward compatibility ---------------------------------------------

def test_evidence_accepts_artifact_type_alias():
    item = {"id": "c", "component": {"function": "settle"}, "evidence": {"artifact_type": "VerificationResult"}}
    assert resolve_item(item, _trace())["status"] == "done"


def test_legacy_binding_item_uses_the_old_path():
    # No component/evidence → legacy path. A non-matching binding keeps 'todo'.
    r = resolve_item({"id": "L", "kind": "property", "binding": {"symbol": "zzz", "property": "zzz"}}, _trace())
    assert r == {"status": "todo", "from_trace": False, "evidence": None}


# --- Counter-evidence: an OPEN defeater on the evidence contests a typed criterion (not just legacy) ---

def _open_defeater(target_id, status="open"):
    from ponens import lineage
    return lineage.residual_to_artifact({
        "residual_id": "d1", "kind": "defeater", "defeater_kind": "undermines",
        "statement": "model diverges from code", "status": status,
        "target": {"target_type": "artifact", "target_id": target_id}})


def test_open_defeater_blocks_a_typed_conformance_criterion():
    # A FAILING conformance carries an undermines-defeater on its ConformanceResult; the conformance
    # criterion must then read `blocked`, not silently `done` on the mere existence of the result.
    t = _trace()
    t["artifacts"].append({"artifact_id": "conf1", "artifact_type": "ConformanceResult",
                           "derived_from": ["model"], "producer_action_id": 10, "payload": {"status": "passed"}})
    c = crit("settle", "ConformanceResult")
    assert resolve_item(c, t)["status"] == "done"          # conformance present + uncontested
    t["artifacts"].append(_open_defeater("conf1"))
    assert resolve_item(c, t)["status"] == "blocked"       # now contested → not met


def test_defeater_on_the_provenance_also_blocks_a_typed_criterion():
    # The defeater need not target the evidence directly — one on what it derives from (the model) counts.
    t = _trace()
    t["artifacts"].append({"artifact_id": "conf1", "artifact_type": "ConformanceResult",
                           "derived_from": ["model"], "producer_action_id": 10, "payload": {"status": "passed"}})
    t["artifacts"].append(_open_defeater("model"))
    assert resolve_item(crit("settle", "ConformanceResult"), t)["status"] == "blocked"


def test_addressed_defeater_does_not_block_a_typed_criterion():
    t = _trace()
    t["artifacts"].append({"artifact_id": "conf1", "artifact_type": "ConformanceResult",
                           "derived_from": ["model"], "producer_action_id": 10, "payload": {"status": "passed"}})
    t["artifacts"].append(_open_defeater("conf1", status="addressed"))
    assert resolve_item(crit("settle", "ConformanceResult"), t)["status"] == "done"  # resolved → no longer blocks

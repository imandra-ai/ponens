"""Typed acceptance criteria resolved by lineage — Goal Contract v0.1 §4 (ponens.goals)."""

from ponens.goals import resolve_item


def _trace():
    # src → IMLModel(settle, fee_tier, refund) → VGs/Decomp → results/tests
    return {
        "actions": [{"id": i} for i in range(1, 20)],
        "artifacts": [
            {"artifact_id": "src", "artifact_type": "SourceCode", "derived_from": None, "producer_action_id": 1},
            {"artifact_id": "model", "artifact_type": "IMLModel", "derived_from": ["src"], "producer_action_id": 2,
             "payload": {"symbols": ["settle", "fee_tier", "refund"]}},
            # settle: money_conserved PROVED — description deliberately does NOT contain the property
            # keyword (the exact shape that broke the old description-substring binding, #1).
            {"artifact_id": "vg1", "artifact_type": "VerificationGoal", "derived_from": ["model"], "producer_action_id": 3,
             "payload": {"goal_id": "g1", "target_symbol": "settle", "property_name": "money_conserved",
                         "description": "charges add up"}},
            {"artifact_id": "vr1", "artifact_type": "VerificationResult", "derived_from": ["vg1"], "producer_action_id": 4,
             "payload": {"goal_id": "g1", "goal_artifact_id": "vg1", "status": "proved"}},
            # refund: refund_nonneg REFUTED
            {"artifact_id": "vg2", "artifact_type": "VerificationGoal", "derived_from": ["model"], "producer_action_id": 5,
             "payload": {"goal_id": "g2", "target_symbol": "refund", "property_name": "refund_nonneg",
                         "description": "refund never negative"}},
            {"artifact_id": "vr2", "artifact_type": "VerificationResult", "derived_from": ["vg2"], "producer_action_id": 6,
             "payload": {"goal_id": "g2", "goal_artifact_id": "vg2", "status": "refuted"}},
            # fee_tier: a 5-region decomposition + a passing suite generated FROM it
            {"artifact_id": "dec", "artifact_type": "Decomp", "derived_from": ["model"], "producer_action_id": 7,
             "payload": {"target_symbol": "fee_tier", "region_count": 5}},
            {"artifact_id": "tests", "artifact_type": "Tests", "derived_from": ["dec"], "producer_action_id": 8,
             "payload": {"count": 12, "failing": 0}},
        ],
    }


def crit(component, evidence):
    return {"id": "c", "component": {"function": component}, "evidence": evidence}


# --- Verification -----------------------------------------------------------

def test_verification_proved_done_even_when_description_differs():  # #1 regression
    r = resolve_item(crit("settle", {"kind": "verification", "property": "money_conserved", "expect": "proved"}), _trace())
    assert r["status"] == "done"
    assert r["evidence"] == "vr1"


def test_verification_wrong_component_stays_not_checked():
    r = resolve_item(crit("nonexistent", {"kind": "verification", "property": "money_conserved"}), _trace())
    assert r == {"status": "todo", "from_trace": False, "evidence": None}


def test_verification_refuted_blocks_when_expecting_proved():
    r = resolve_item(crit("refund", {"kind": "verification", "property": "refund_nonneg", "expect": "proved"}), _trace())
    assert r["status"] == "blocked"


def test_expect_refuted_wants_the_counterexample():
    r = resolve_item(crit("refund", {"kind": "verification", "property": "refund_nonneg", "expect": "refuted"}), _trace())
    assert r["status"] == "done"


def test_verification_requires_an_autoformalized_model():
    # A VG NOT derived from an IMLModel (hand-authored) must not satisfy a verification criterion.
    t = _trace()
    t["artifacts"] += [
        {"artifact_id": "vgX", "artifact_type": "VerificationGoal", "derived_from": None, "producer_action_id": 9,
         "payload": {"goal_id": "gX", "target_symbol": "loose", "property_name": "p", "description": "d"}},
        {"artifact_id": "vrX", "artifact_type": "VerificationResult", "derived_from": ["vgX"], "producer_action_id": 10,
         "payload": {"goal_id": "gX", "goal_artifact_id": "vgX", "status": "proved"}},
    ]
    r = resolve_item(crit("loose", {"kind": "verification", "property": "p"}), t)
    assert r["status"] == "todo"  # no IMLModel in its lineage → not counted


def test_verification_goal_without_result_is_in_progress():
    t = _trace()
    t["artifacts"].append(
        {"artifact_id": "vg3", "artifact_type": "VerificationGoal", "derived_from": ["model"], "producer_action_id": 11,
         "payload": {"goal_id": "g3", "target_symbol": "fee_tier", "property_name": "monotone", "description": "d"}})
    r = resolve_item(crit("fee_tier", {"kind": "verification", "property": "monotone"}), t)
    assert r["status"] == "doing"


# --- Tests ------------------------------------------------------------------

def test_tests_all_pass_meets_min_done():
    r = resolve_item(crit("fee_tier", {"kind": "tests", "min": 5}), _trace())
    assert r["status"] == "done"
    assert r["evidence"] == "tests"


def test_tests_below_min_is_in_progress():
    r = resolve_item(crit("fee_tier", {"kind": "tests", "min": 50}), _trace())
    assert r["status"] == "doing"


def test_tests_with_failures_blocks():
    t = _trace()
    t["artifacts"].append(
        {"artifact_id": "tf", "artifact_type": "Tests", "derived_from": ["model"], "producer_action_id": 12,
         "payload": {"count": 3, "failing": 1, "target_symbol": "settle"}})
    r = resolve_item(crit("settle", {"kind": "tests"}), t)
    assert r["status"] == "blocked"


# --- Decomposition ----------------------------------------------------------

def test_decomposition_enough_regions_done():
    r = resolve_item(crit("fee_tier", {"kind": "decomposition", "min_regions": 3}), _trace())
    assert r["status"] == "done"
    assert r["evidence"] == "dec"


def test_decomposition_too_few_regions_in_progress():
    r = resolve_item(crit("fee_tier", {"kind": "decomposition", "min_regions": 20}), _trace())
    assert r["status"] == "doing"


# --- Backward compatibility -------------------------------------------------

def test_legacy_binding_item_uses_the_old_path():
    # No component/evidence → legacy path. A non-matching binding keeps 'todo' (doesn't crash / isn't
    # captured by the typed resolver).
    r = resolve_item({"id": "L", "kind": "property", "binding": {"symbol": "zzz", "property": "zzz"}}, _trace())
    assert r == {"status": "todo", "from_trace": False, "evidence": None}

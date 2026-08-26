"""§8.8 property-language front-end, Phase 2: selectors + quantifiers (ponens.goals + ponens.component).

Covers:
  - resolve_selector per kind: glob / module / scope / tag(best-effort over high_stakes_paths).
  - forall / exists over a selector, combined with the Phase-1 status lattice.
  - variable binding/substitution into inner atoms ({"var": "f"}).
  - empty selector -> todo (no vacuous done) for both quantifiers.
  - quantifiers nested under Phase-1 combinators.
"""

from ponens.goals import resolve_item, eval_formula, _subst_atom
from ponens.component import resolve_selector, _dedup


def _trace():
    """Two files: payments/charge.py (charge PROVED, refund REFUTED) and pricing/tiers.py (fee_tier
    PROVED). Component ids stamped as assign_component_ids would. high_stakes_paths = payments/."""
    return {
        "actions": [{"id": i} for i in range(1, 20)],
        "high_stakes_paths": ["payments/"],
        "artifacts": [
            {"artifact_id": "src_pay", "artifact_type": "SourceCode", "derived_from": None,
             "producer_action_id": 1, "name": "payments/charge.py"},
            {"artifact_id": "m_pay", "artifact_type": "IMLModel", "derived_from": ["src_pay"],
             "producer_action_id": 2,
             "payload": {"iml_code": "let charge x = x\nlet refund y = y",
                         "component_ids": {"charge": "cmp0", "refund": "cmp1"}}},
            {"artifact_id": "src_price", "artifact_type": "SourceCode", "derived_from": None,
             "producer_action_id": 3, "name": "pricing/tiers.py"},
            {"artifact_id": "m_price", "artifact_type": "IMLModel", "derived_from": ["src_price"],
             "producer_action_id": 4,
             "payload": {"iml_code": "let fee_tier z = z", "component_ids": {"fee_tier": "cmp2"}}},
            # verdicts: charge proved, refund refuted, fee_tier proved
            {"artifact_id": "vg_c", "artifact_type": "VerificationGoal", "derived_from": ["m_pay"],
             "producer_action_id": 5, "payload": {"goal_id": "gc", "target_symbol": "charge"}},
            {"artifact_id": "vr_c", "artifact_type": "VerificationResult", "derived_from": ["vg_c"],
             "producer_action_id": 6, "payload": {"goal_id": "gc", "goal_artifact_id": "vg_c", "status": "proved"}},
            {"artifact_id": "vg_r", "artifact_type": "VerificationGoal", "derived_from": ["m_pay"],
             "producer_action_id": 7, "payload": {"goal_id": "gr", "target_symbol": "refund"}},
            {"artifact_id": "vr_r", "artifact_type": "VerificationResult", "derived_from": ["vg_r"],
             "producer_action_id": 8, "payload": {"goal_id": "gr", "goal_artifact_id": "vg_r", "status": "refuted"}},
            {"artifact_id": "vg_f", "artifact_type": "VerificationGoal", "derived_from": ["m_price"],
             "producer_action_id": 9, "payload": {"goal_id": "gf", "target_symbol": "fee_tier"}},
            {"artifact_id": "vr_f", "artifact_type": "VerificationResult", "derived_from": ["vg_f"],
             "producer_action_id": 10, "payload": {"goal_id": "gf", "goal_artifact_id": "vg_f", "status": "proved"}},
        ],
    }


GOAL = {"id": "g", "scope": ["charge", "fee_tier"]}
PROVED_VAR = {"atom": {"kind": "property", "binding": {"symbol": {"var": "f"}}}}  # per-element property


def _syms(elements):
    return sorted(e["symbol"] for e in elements)


# ---------------------------------------------------------------------------
# resolve_selector
# ---------------------------------------------------------------------------

def test_selector_glob():
    assert _syms(resolve_selector({"glob": "payments/**"}, _trace())) == ["charge", "refund"]


def test_selector_module():
    assert _syms(resolve_selector({"module": "pricing"}, _trace())) == ["fee_tier"]


def test_selector_scope():
    assert _syms(resolve_selector({"scope": True}, _trace(), GOAL)) == ["charge", "fee_tier"]


def test_selector_tag_best_effort_over_high_stakes():
    # tag matches by high_stakes_paths substring regardless of tag name (documented gap).
    assert _syms(resolve_selector({"tag": "money"}, _trace())) == ["charge", "refund"]
    assert _syms(resolve_selector({"tag": "anything"}, _trace())) == ["charge", "refund"]


def test_selector_carries_component_id_and_file():
    el = next(e for e in resolve_selector({"glob": "payments/**"}, _trace()) if e["symbol"] == "charge")
    assert el["component_id"] == "cmp0"
    assert el["file"] == "payments/charge.py"


def test_selector_unknown_or_empty_is_empty_list():
    assert resolve_selector({"glob": "nope/**"}, _trace()) == []
    assert resolve_selector({"bogus": 1}, _trace()) == []
    assert resolve_selector("notadict", _trace()) == []


def test_dedup_by_component_id():
    els = [{"symbol": "a", "component_id": "cmp0"}, {"symbol": "a2", "component_id": "cmp0"},
           {"symbol": "b", "component_id": None}, {"symbol": "b", "component_id": None}]
    assert _dedup(els) == [{"symbol": "a", "component_id": "cmp0"}, {"symbol": "b", "component_id": None}]


# ---------------------------------------------------------------------------
# variable substitution
# ---------------------------------------------------------------------------

def test_subst_binding_symbol():
    a = _subst_atom({"kind": "property", "binding": {"symbol": {"var": "f"}}}, {"f": {"symbol": "charge"}})
    assert a["binding"]["symbol"] == "charge"


def test_subst_component_var():
    a = _subst_atom({"component": {"var": "f"}, "evidence": {"artifact": "VerificationResult"}},
                    {"f": {"symbol": "charge", "component_id": "cmp0"}})
    assert a["component"] == {"function": "charge", "symbol": "charge"}


def test_subst_noop_without_env():
    atom = {"kind": "property", "binding": {"symbol": {"var": "f"}}}
    assert _subst_atom(atom, None) is atom


# ---------------------------------------------------------------------------
# quantifiers (through resolve_item, with the goal for scope)
# ---------------------------------------------------------------------------

def _f(node):
    return resolve_item({"id": "x", "formula": node}, _trace(), goal=GOAL)["status"]


def test_forall_over_glob_blocks_when_one_refuted():
    # payments/** = {charge PROVED, refund REFUTED}; forall(proved) → and → blocked.
    assert _f({"forall": {"in": {"glob": "payments/**"}, "as": "f", "holds": PROVED_VAR}}) == "blocked"


def test_exists_over_glob_done_when_one_proved():
    # exists(proved) over payments/** → or(done, blocked) → done.
    assert _f({"exists": {"in": {"glob": "payments/**"}, "as": "f", "holds": PROVED_VAR}}) == "done"


def test_forall_over_module_all_proved():
    assert _f({"forall": {"in": {"module": "pricing"}, "as": "f", "holds": PROVED_VAR}}) == "done"


def test_forall_over_scope_all_proved():
    # scope = {charge, fee_tier}, both proved → done.
    assert _f({"forall": {"in": {"scope": True}, "as": "f", "holds": PROVED_VAR}}) == "done"


def test_empty_selector_is_todo_for_both_quantifiers():
    assert _f({"forall": {"in": {"glob": "nope/**"}, "as": "f", "holds": PROVED_VAR}}) == "todo"
    assert _f({"exists": {"in": {"glob": "nope/**"}, "as": "f", "holds": PROVED_VAR}}) == "todo"


def test_quantifier_nested_under_combinator():
    # and[ forall(module pricing: proved)=done , exists(payments: proved)=done ] → done
    node = {"and": [
        {"forall": {"in": {"module": "pricing"}, "as": "f", "holds": PROVED_VAR}},
        {"exists": {"in": {"glob": "payments/**"}, "as": "f", "holds": PROVED_VAR}},
    ]}
    assert _f(node) == "done"
    # and[ forall(payments: proved)=blocked , ... ] → blocked propagates
    node2 = {"and": [
        {"forall": {"in": {"glob": "payments/**"}, "as": "f", "holds": PROVED_VAR}},
        {"forall": {"in": {"module": "pricing"}, "as": "f", "holds": PROVED_VAR}},
    ]}
    assert _f(node2) == "blocked"


def test_role_inherited_into_quantifier_body():
    # governed role on the quantifier flows to the per-element atom (here no defeater/staleness, so done).
    node = {"forall": {"in": {"module": "pricing"}, "as": "f", "holds": PROVED_VAR}, "role": "met"}
    assert _f(node) == "done"

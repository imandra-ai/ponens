"""§8.8 property-language front-end, Phase 1: the formula AST + recursive evaluator (ponens.goals).

Covers three things:
  1. Regression — a legacy acceptance item (each kind) desugars to a single atom and resolves
     IDENTICALLY to a bare item (byte-for-byte), so the formula layer is non-breaking.
  2. Combinators — and/or/not/implies lift over the 4-valued status lattice {done,doing,todo,blocked}.
  3. Roles — [met] vs [governed] gate defeater/freshness; the default (no role) reproduces today.
"""

from ponens import lineage
from ponens.goals import (
    resolve_item, eval_formula, eval_atom,
    _combine_and, _combine_or, _combine_not,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _open_defeater(target_id):
    return lineage.residual_to_artifact({
        "residual_id": "d-" + target_id, "kind": "defeater", "defeater_kind": "undermines",
        "statement": "model diverges from code", "status": "open",
        "target": {"target_type": "artifact", "target_id": target_id}})


def _trace():
    """src → model(settle, refund, hold, aged) → VGs/VRs, plus a policy eval, a residual, a diff."""
    return {
        "actions": [{"id": i} for i in range(1, 30)],
        "artifacts": [
            {"artifact_id": "src", "artifact_type": "SourceCode", "derived_from": None, "producer_action_id": 1},
            {"artifact_id": "model", "artifact_type": "IMLModel", "derived_from": ["src"], "producer_action_id": 2,
             "payload": {"symbols": ["settle", "refund", "hold", "aged"]}},
            # settle: PROVED
            {"artifact_id": "vg_s", "artifact_type": "VerificationGoal", "derived_from": ["model"], "producer_action_id": 3,
             "payload": {"goal_id": "g_s", "target_symbol": "settle"}},
            {"artifact_id": "vr_s", "artifact_type": "VerificationResult", "derived_from": ["vg_s"], "producer_action_id": 4,
             "payload": {"goal_id": "g_s", "goal_artifact_id": "vg_s", "status": "proved"}},
            # refund: REFUTED  → property kind resolves `blocked`
            {"artifact_id": "vg_r", "artifact_type": "VerificationGoal", "derived_from": ["model"], "producer_action_id": 5,
             "payload": {"goal_id": "g_r", "target_symbol": "refund"}},
            {"artifact_id": "vr_r", "artifact_type": "VerificationResult", "derived_from": ["vg_r"], "producer_action_id": 6,
             "payload": {"goal_id": "g_r", "goal_artifact_id": "vg_r", "status": "refuted"}},
            # hold: VG but NO result  → property kind resolves `doing`
            {"artifact_id": "vg_h", "artifact_type": "VerificationGoal", "derived_from": ["model"], "producer_action_id": 7,
             "payload": {"goal_id": "g_h", "target_symbol": "hold"}},
            # aged: PROVED at step 8, then the symbol changes at step 25 → the proof goes STALE
            {"artifact_id": "vg_a", "artifact_type": "VerificationGoal", "derived_from": ["model"], "producer_action_id": 8,
             "payload": {"goal_id": "g_a", "target_symbol": "aged"}},
            {"artifact_id": "vr_a", "artifact_type": "VerificationResult", "derived_from": ["vg_a"], "producer_action_id": 9,
             "payload": {"goal_id": "g_a", "goal_artifact_id": "vg_a", "status": "proved"}},
            # obligation / gap fixtures
            {"artifact_id": "diff_settle", "artifact_type": "Diff", "derived_from": ["src"], "producer_action_id": 10,
             "payload": {"target_symbol": "settle"}, "summary": "edit settle"},
        ],
        "policy_evaluations": [{"policy_id": "p_ok", "status": "passed"},
                               {"policy_id": "p_bad", "status": "failed"}],
        "residuals": [{"residual_id": "res_open", "kind": "limitation", "status": "open"},
                      {"residual_id": "res_done", "kind": "limitation", "status": "addressed"}],
    }


# Leaf items (bare = legacy; each resolves to a known status against _trace()).
PROVED = {"id": "a", "kind": "property", "binding": {"symbol": "settle"}}      # done
REFUTED = {"id": "b", "kind": "property", "binding": {"symbol": "refund"}}     # blocked
DOING = {"id": "c", "kind": "property", "binding": {"symbol": "hold"}}         # doing
TODO = {"id": "d", "kind": "property", "binding": {"symbol": "ghost"}}         # todo (no VG)
OBL_OK = {"id": "e", "kind": "obligation", "binding": {"policy_id": "p_ok"}}   # done
OBL_BAD = {"id": "f", "kind": "obligation", "binding": {"policy_id": "p_bad"}} # blocked
GAP_OPEN = {"id": "g", "kind": "gap", "binding": {"residual_id": "res_open"}}  # todo
GAP_DONE = {"id": "h", "kind": "gap", "binding": {"residual_id": "res_done"}}  # done
TYPED = {"id": "i", "component": {"function": "settle"}, "evidence": {"artifact": "VerificationResult"}}  # done


# ---------------------------------------------------------------------------
# 1. Regression: legacy item == {"formula": {"atom": item}}  (desugar is identical)
# ---------------------------------------------------------------------------

def test_legacy_desugar_is_identical_across_kinds():
    t = _trace()
    for item, expect in [(PROVED, "done"), (REFUTED, "blocked"), (DOING, "doing"), (TODO, "todo"),
                         (OBL_OK, "done"), (OBL_BAD, "blocked"), (GAP_OPEN, "todo"), (GAP_DONE, "done"),
                         (TYPED, "done")]:
        bare = resolve_item(item, t)
        wrapped = resolve_item({"id": item["id"], "formula": {"atom": item}}, t)
        assert bare["status"] == expect, (item["id"], bare)
        assert bare == wrapped, (item["id"], bare, wrapped)  # byte-for-byte


# ---------------------------------------------------------------------------
# 2a. Status lattice (pure combinators)
# ---------------------------------------------------------------------------

def _r(s):
    return {"status": s, "from_trace": True, "evidence": None}


def test_and_lattice():
    st = lambda xs: _combine_and([_r(s) for s in xs])["status"]
    assert st(["done", "done"]) == "done"
    assert st(["done", "doing"]) == "doing"
    assert st(["done", "todo"]) == "doing"     # any done|doing → doing
    assert st(["todo", "todo"]) == "todo"
    assert st(["done", "blocked"]) == "blocked"  # any blocked dominates
    assert st(["doing", "blocked"]) == "blocked"
    assert _combine_and([])["status"] == "todo"  # empty → todo (no vacuous done)


def test_or_lattice():
    st = lambda xs: _combine_or([_r(s) for s in xs])["status"]
    assert st(["todo", "done"]) == "done"
    assert st(["blocked", "done"]) == "done"     # any done wins
    assert st(["todo", "doing"]) == "doing"
    assert st(["blocked", "blocked"]) == "blocked"
    assert st(["blocked", "todo"]) == "todo"     # not all blocked, no done/doing
    assert _combine_or([])["status"] == "todo"


def test_not_lattice():
    n = lambda s: _combine_not(_r(s))["status"]
    assert n("done") == "todo"
    assert n("todo") == "done"
    assert n("doing") == "doing"
    assert n("blocked") == "blocked"   # contested stays contested


# ---------------------------------------------------------------------------
# 2b. Combinators over REAL atoms (through eval_formula)
# ---------------------------------------------------------------------------

def _f(node):
    return resolve_item({"id": "x", "formula": node}, _trace())["status"]


def test_and_of_atoms():
    assert _f({"and": [{"atom": PROVED}, {"atom": TYPED}]}) == "done"        # both done
    assert _f({"and": [{"atom": PROVED}, {"atom": REFUTED}]}) == "blocked"   # refuted propagates
    assert _f({"and": [{"atom": PROVED}, {"atom": DOING}]}) == "doing"


def test_or_of_atoms():
    assert _f({"or": [{"atom": TODO}, {"atom": PROVED}]}) == "done"
    assert _f({"or": [{"atom": REFUTED}, {"atom": REFUTED}]}) == "blocked"
    assert _f({"or": [{"atom": TODO}, {"atom": DOING}]}) == "doing"


def test_not_of_atom():
    assert _f({"not": {"atom": PROVED}}) == "todo"
    assert _f({"not": {"atom": TODO}}) == "done"


def test_implies_of_atoms():
    # implies(a,b) = or(not a, b). Antecedent unmet (todo→not=done) ⇒ vacuously done.
    assert _f({"implies": [{"atom": TODO}, {"atom": REFUTED}]}) == "done"
    # Antecedent met (done→not=todo), consequent done ⇒ done.
    assert _f({"implies": [{"atom": PROVED}, {"atom": TYPED}]}) == "done"
    # Antecedent met, consequent todo ⇒ or(todo, todo) = todo.
    assert _f({"implies": [{"atom": PROVED}, {"atom": TODO}]}) == "todo"


# ---------------------------------------------------------------------------
# 3. Roles: [met] vs [governed] vs default
# ---------------------------------------------------------------------------

def test_role_defeater_met_vs_governed_vs_default():
    t = _trace()
    t["artifacts"].append(_open_defeater("vr_s"))  # contest the proof of `settle`
    # default (legacy, no role): a contested proof is blocked — today's behavior.
    assert resolve_item(PROVED, t)["status"] == "blocked"
    # met: mere existence — the defeater is ignored.
    assert eval_formula({"atom": PROVED, "role": "met"}, t)["status"] == "done"
    # governed: contested ⇒ blocked.
    assert eval_formula({"atom": PROVED, "role": "governed"}, t)["status"] == "blocked"


def test_role_freshness_governed_only():
    t = _trace()
    # `aged` was proved at step 9, but a later Diff renames/changes it → the proof is stale (§18.3).
    t["artifacts"].append({"artifact_id": "diff_aged", "artifact_type": "Diff", "derived_from": ["src"],
                           "producer_action_id": 25, "payload": {"target_symbol": "aged"}, "summary": "edit aged"})
    AGED = {"id": "z", "kind": "property", "binding": {"symbol": "aged"}}
    # default & met do NOT freshness-gate → still done.
    assert resolve_item(AGED, t)["status"] == "done"
    assert eval_formula({"atom": AGED, "role": "met"}, t)["status"] == "done"
    # governed requires fresh → stale ⇒ blocked.
    assert eval_formula({"atom": AGED, "role": "governed"}, t)["status"] == "blocked"


def test_role_inherited_down_subtree():
    t = _trace()
    t["artifacts"].append(_open_defeater("vr_s"))
    # role on the combinator node is inherited by the child atom → met ignores the defeater.
    assert resolve_item({"id": "x", "formula": {"and": [{"atom": PROVED}], "role": "met"}}, t)["status"] == "done"
    # without the inherited role, the same shape blocks (default).
    assert resolve_item({"id": "x", "formula": {"and": [{"atom": PROVED}]}}, t)["status"] == "blocked"


def test_eval_atom_helper_roles():
    t = _trace()
    t["artifacts"].append(_open_defeater("vr_s"))
    assert eval_atom(PROVED, t)["status"] == "blocked"            # default
    assert eval_atom(PROVED, t, role="met")["status"] == "done"
    assert eval_atom(PROVED, t, role="governed")["status"] == "blocked"

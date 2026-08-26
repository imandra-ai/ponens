"""Unit tests for component-identity STAMPING + CONSUMPTION (2c / 2d).

`assign_component_ids` (component.py) groups a trace's model symbols into stable components and stamps
`payload.component_ids` (models) + `payload.target_component_id` (VerificationGoals). The consumers —
`lineage.roots_in_component` (goal rooting) and `goals.stale_evidence` (freshness) — then FOLLOW A
RENAME by component instead of by name. Everything is additive: a trace with no stamped ids resolves
exactly as before.

Each trace is a tiny in-memory dict (same shape as test_merge.py): a model artifact carries
`payload.iml_code`; a proof is a VerificationGoal{target_symbol} + a proved VerificationResult.
"""

import copy

from ponens.component import assign_component_ids, match_descriptor
from ponens import lineage
from ponens.goals import enrich, stale_evidence, _resolve_typed


# ---- trace builders -------------------------------------------------------

def _model(src, aid="m1", step=1, derived_from=None):
    a = {"artifact_id": aid, "artifact_type": "IMLModel", "producer_action_id": step,
         "payload": {"iml_code": src}}
    if derived_from is not None:
        a["derived_from"] = derived_from
    return a


def _proof(sym, vg="vg1", vr="vr1", step=2, desc=None):
    return [
        {"artifact_id": vg, "artifact_type": "VerificationGoal", "producer_action_id": step,
         "payload": {"goal_id": vg + "-G", "target_symbol": sym,
                     "description": desc or f"property of {sym}"}},
        {"artifact_id": vr, "artifact_type": "VerificationResult", "producer_action_id": step + 1,
         "derived_from": [vg], "payload": {"goal_id": vg + "-G", "goal_artifact_id": vg,
                                           "status": "proved"}},
    ]


# A distinctive multi-line body: a rename touches only the signature line, so similarity stays
# confidently above the 80% floor (identity.iml SIM_MIN) while an unrelated symbol is far below it. The
# body is long enough that a rename PLUS a single-line body edit still clears the floor by a margin (so
# a renamed+changed component is recognized as the SAME component, and its proof correctly goes stale).
_CLAMP = ("let clamp x =\n"
          "  let lo = 0 in\n"
          "  let hi = 100 in\n"
          "  let a = x + 1 in\n"
          "  let b = a * 2 in\n"
          "  let c = b - 3 in\n"
          "  let d = c + 4 in\n"
          "  let e = d * 5 in\n"
          "  let f0 = e - 6 in\n"
          "  if x < lo then lo\n"
          "  else if x > hi then hi\n"
          "  else x\n")
_CLAMP_INT_SAME = _CLAMP.replace("let clamp x =", "let clamp_int x =")            # rename, identical body
_CLAMP_INT_CHANGED = _CLAMP_INT_SAME.replace("let d = c + 4 in", "let d = c + 99 in")  # rename + 1-line change


# ================================================================
# 1. rename ROOTS the goal (roots_in_component follows the rename)
# ================================================================

def test_rename_roots_the_goal():
    # ours proves clamp (m1); a later model (m2, same model line) renames clamp -> clamp_int, identical
    # body. A typed goal criterion `component: clamp, evidence: VerificationResult` should STILL resolve.
    trace = {"trace_id": "t", "artifacts": [
        _model(_CLAMP, aid="m1", step=1, derived_from=["src"]),
        *_proof("clamp", vg="vg1", vr="vr1", step=2),
        _model(_CLAMP_INT_SAME, aid="m2", step=5, derived_from=["src"]),
    ]}
    stamped = copy.deepcopy(trace)
    info = assign_component_ids(stamped)
    # clamp and clamp_int chain to the SAME component (rename, identical body).
    assert info["by_name"]["clamp"] == info["by_name"]["clamp_int"]

    item = {"component": {"function": "clamp"}, "evidence": {"artifact": "VerificationResult"}}
    res = _resolve_typed(item, stamped)
    assert res["status"] == "done"          # roots via component_id across the rename
    assert res["evidence"] == "vr1"

    # CONTRAST: strip the component_ids -> name mismatch -> does NOT root (the goal names `clamp`, but the
    # VR's lineage now would only be reachable by the component-identity path, which is gone).
    stripped = copy.deepcopy(stamped)
    for a in stripped["artifacts"]:
        a.get("payload", {}).pop("component_ids", None)
        a.get("payload", {}).pop("target_component_id", None)
    # roots_in_component still matches by NAME here (the VG's target_symbol IS clamp), so isolate the pure
    # component-identity contribution: a goal naming the NEW name `clamp_int` roots ONLY via component id.
    item_new = {"component": {"function": "clamp_int"}, "evidence": {"artifact": "VerificationResult"}}
    assert _resolve_typed(item_new, stamped)["status"] == "done"      # follows rename via component id
    assert _resolve_typed(item_new, stripped)["status"] == "todo"     # no component id -> name mismatch


# ================================================================
# 2. stale FOLLOWS the rename (stale_evidence chains by component)
# ================================================================

def test_stale_follows_rename():
    # prove clamp (m1); later model renames clamp -> clamp_int AND changes the body (hi 100 -> 255).
    trace = {"trace_id": "t", "artifacts": [
        _model(_CLAMP, aid="m1", step=1, derived_from=["src"]),
        *_proof("clamp", vg="vg1", vr="vr1", step=2),
        _model(_CLAMP_INT_CHANGED, aid="m2", step=5, derived_from=["src"]),
    ]}
    stamped = copy.deepcopy(trace)
    assign_component_ids(stamped)
    res = stale_evidence(stamped)
    stale = [r for r in res if r.get("kind") == "stale_evidence" and r.get("target", {}).get("target_id") == "vr1"]
    assert stale, "the proof of clamp should go stale under the renamed+changed component"


# ================================================================
# 3. name FALLBACK — a trace with NO component_ids resolves as before
# ================================================================

def test_name_fallback_no_component_ids():
    # No renames, no stamping: an existing NAME-based rooting must still resolve identically.
    trace = {"trace_id": "t", "artifacts": [
        _model(_CLAMP, aid="m1", step=1),
        *_proof("clamp", vg="vg1", vr="vr1", step=2),
    ]}
    # roots_in_component with NO component_ids in the trace -> pure name path.
    assert lineage._component_by_name(trace) == {}
    assert lineage.roots_in_component("vr1", "clamp", trace) is True
    item = {"component": {"function": "clamp"}, "evidence": {"artifact": "VerificationResult"}}
    assert _resolve_typed(item, trace)["status"] == "done"
    # A goal about a genuinely-different symbol does not root.
    assert lineage.roots_in_component("vr1", "other", trace) is False


# ================================================================
# 4. never-conflate — two different symbols get DIFFERENT ids
# ================================================================

_OTHER = ("let scale y =\n"
          "  let k = 3 in\n"
          "  let base = 7 in\n"
          "  y * k + base\n")


def test_never_conflate_distinct_symbols():
    trace = {"trace_id": "t", "artifacts": [
        _model(_CLAMP + _OTHER, aid="m1", step=1, derived_from=["src"]),
        *_proof("clamp", vg="vg1", vr="vr1", step=2),
        *_proof("scale", vg="vg2", vr="vr2", step=4),
    ]}
    stamped = copy.deepcopy(trace)
    info = assign_component_ids(stamped)
    assert info["by_name"]["clamp"] != info["by_name"]["scale"]      # distinct components
    # A goal about clamp roots in clamp's proof, NOT scale's.
    item_clamp = {"component": {"function": "clamp"}, "evidence": {"artifact": "VerificationResult"}}
    assert _resolve_typed(item_clamp, stamped)["evidence"] == "vr1"
    # roots_in_component never conflates across the two components.
    assert lineage.roots_in_component("vr2", "clamp", stamped) is False
    assert lineage.roots_in_component("vr1", "scale", stamped) is False


# ================================================================
# 5. assign_component_ids resolution unit — lineage / exact / similar / distinct / ambiguous
# ================================================================

def test_assign_exact_same_id():
    # Same body, same model line, same name across two revisions -> SAME component id (lineage/exact).
    trace = {"trace_id": "t", "artifacts": [
        _model(_CLAMP, aid="m1", step=1, derived_from=["src"]),
        _model(_CLAMP, aid="m2", step=5, derived_from=["src"]),  # identical re-model
    ]}
    info = assign_component_ids(trace)
    ids = [m["payload"]["component_ids"]["clamp"] for m in trace["artifacts"]]
    assert ids[0] == ids[1]
    assert info["by_name"]["clamp"] == ids[0]


def test_assign_similar_rename_same_id():
    # Rename with identical body (similarity/exact-fingerprint) -> SAME component id.
    trace = {"trace_id": "t", "artifacts": [
        _model(_CLAMP, aid="m1", step=1, derived_from=["src"]),
        _model(_CLAMP_INT_SAME, aid="m2", step=5, derived_from=["src"]),
    ]}
    info = assign_component_ids(trace)
    assert info["by_name"]["clamp"] == info["by_name"]["clamp_int"]


def test_assign_distinct_new_id():
    # Two genuinely-different symbols in one model -> two DIFFERENT ids.
    trace = {"trace_id": "t", "artifacts": [_model(_CLAMP + _OTHER, aid="m1", step=1)]}
    info = assign_component_ids(trace)
    assert info["by_name"]["clamp"] != info["by_name"]["scale"]
    assert {info["by_name"]["clamp"], info["by_name"]["scale"]} == {"cmp0", "cmp1"}


def test_assign_ambiguous_mints_new():
    # ONE renamed symbol facing TWO equally-similar prior candidates -> never guess WHICH -> mint fresh
    # (never conflate). m1 defines two identical-body siblings (distinct components); m2 (a DIFFERENT
    # model line, so no lineage-by-name) has a single `clamp_new` with that same body -> two exact-
    # fingerprint candidates -> ambiguous -> mint.
    c1a = _CLAMP.replace("let clamp x =", "let clamp_a x =")
    c1b = _CLAMP.replace("let clamp x =", "let clamp_b x =")
    c_new = _CLAMP.replace("let clamp x =", "let clamp_new x =")
    trace = {"trace_id": "t", "artifacts": [
        _model(c1a + c1b, aid="m1", step=1, derived_from=["srcA"]),   # two distinct identical-body sibs
        _model(c_new, aid="m2", step=5, derived_from=["srcB"]),       # different model line -> no lineage
    ]}
    info = assign_component_ids(trace)
    a_id = trace["artifacts"][0]["payload"]["component_ids"]["clamp_a"]
    b_id = trace["artifacts"][0]["payload"]["component_ids"]["clamp_b"]
    new_id = info["by_name"]["clamp_new"]
    assert a_id != b_id                            # the two siblings are distinct components
    assert new_id != a_id and new_id != b_id       # ambiguous match -> minted fresh, never conflated


def test_assign_lineage_carries_across_body_change():
    # Same model line + same name but a CHANGED body: the lineage tier (producer-declared same-model-line
    # link) still reuses the id — identity follows the model line even when the fingerprint diverges.
    trace = {"trace_id": "t", "artifacts": [
        _model(_CLAMP, aid="m1", step=1, derived_from=["src"]),
        _model(_CLAMP.replace("let hi = 100 in", "let hi = 42 in"), aid="m2", step=5, derived_from=["src"]),
    ]}
    info = assign_component_ids(trace)
    ids = [m["payload"]["component_ids"]["clamp"] for m in trace["artifacts"]]
    assert ids[0] == ids[1]                   # lineage keeps them one component across the edit


# ================================================================
# enrich wiring: the source trace is NOT mutated; the projection carries ids
# ================================================================

def test_enrich_does_not_mutate_source():
    trace = {"trace_id": "t", "goals": [], "artifacts": [
        _model(_CLAMP, aid="m1", step=1, derived_from=["src"]),
        *_proof("clamp", vg="vg1", vr="vr1", step=2),
        _model(_CLAMP_INT_SAME, aid="m2", step=5, derived_from=["src"]),
    ]}
    before = copy.deepcopy(trace)
    out = enrich(trace)
    # source untouched (no component_ids leaked back onto the on-disk trace)
    assert trace == before
    for a in trace["artifacts"]:
        assert "component_ids" not in a.get("payload", {})
    # the projection carries the stamped ids
    m2 = next(a for a in out["artifacts"] if a.get("artifact_id") == "m2")
    assert "component_ids" in m2["payload"]


def test_enrich_goal_roots_across_rename():
    # End-to-end through enrich: a typed goal named `clamp_int` (the new name) resolves `done` because the
    # enrich projection stamps component_ids and rooting follows the rename.
    trace = {"trace_id": "t", "artifacts": [
        _model(_CLAMP, aid="m1", step=1, derived_from=["src"]),
        *_proof("clamp", vg="vg1", vr="vr1", step=2),
        _model(_CLAMP_INT_SAME, aid="m2", step=5, derived_from=["src"]),
    ], "goals": [{
        "id": "g1", "intent": "clamp is verified",
        "acceptance": [{"id": "a1", "component": {"function": "clamp_int"},
                        "evidence": {"artifact": "VerificationResult"}}],
    }]}
    out = enrich(trace)
    item = out["goals"][0]["acceptance"][0]
    assert item["status"] == "done"

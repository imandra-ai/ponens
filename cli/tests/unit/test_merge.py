"""Unit tests for residual-aware trace MERGE (ponens.merge).

Ports the IML example battery (formal/merge/{delta,classify}.iml) down to the trace level. Each trace
is a tiny in-memory dict: model artifacts carry `payload.iml_code`, and a standing result is an
IMLModel + VerificationGoal{target_symbol} + VerificationResult{status:proved}. Scope is the two live
branches: SkipDisjoint (carried_forward) and ReReason (needs_rereasoning).
"""

from ponens.merge import merge, merge_delta, _standing_results, _symbols


# ---- trace builders -------------------------------------------------------

def _model(src, aid="m1", step=1, derived_from=None):
    a = {"artifact_id": aid, "artifact_type": "IMLModel", "producer_action_id": step,
         "payload": {"iml_code": src}}
    if derived_from is not None:
        a["derived_from"] = derived_from
    return a


def _proved(sym, vg="vg1", vr="vr1", step=2, desc=None):
    """A standing proof about `sym`: a VerificationGoal (target_symbol) + a proved VerificationResult."""
    return [
        {"artifact_id": vg, "artifact_type": "VerificationGoal", "producer_action_id": step,
         "payload": {"goal_id": vg + "-G", "target_symbol": sym,
                     "description": desc or f"property of {sym}"}},
        {"artifact_id": vr, "artifact_type": "VerificationResult", "producer_action_id": step + 1,
         "derived_from": [vg], "payload": {"goal_id": vg + "-G", "goal_artifact_id": vg,
                                           "status": "proved"}},
    ]


def _trace(src, results=None, residuals=None, step=1):
    t = {"trace_id": "t", "artifacts": [_model(src, step=step)]}
    for r in results or []:
        t["artifacts"].extend(r)
    if residuals:
        t["residuals"] = residuals
    return t


# Common source fixtures: f depends on g (transitive), h is unrelated.
SRC = "let g x = x + 1\nlet f x = g x + 2\nlet h x = x * 10\n"


# ---- 1. disjoint: theirs changes an unrelated symbol -> CarriedForward -----

def test_disjoint_carried_forward():
    ours = _trace(SRC, results=[_proved("f")])
    theirs = _trace("let g x = x + 1\nlet f x = g x + 2\nlet h x = x * 999\n")  # only h changed
    rep = merge(ours, theirs)
    assert rep["delta"]["changed"] == ["h"]
    assert [c["result_id"] for c in rep["carried_forward"]] == ["vr1"]
    assert rep["carried_forward"][0]["basis"] == "closure-disjoint"
    assert rep["rereason"] == []


# ---- 2. direct touch: theirs changes the proved symbol itself -> ReReason --

def test_direct_touch_rereason():
    ours = _trace(SRC, results=[_proved("f")])
    theirs = _trace("let g x = x + 1\nlet f x = g x + 99\nlet h x = x * 10\n")  # f's body changed
    rep = merge(ours, theirs)
    assert "f" in rep["delta"]["changed"]
    assert rep["carried_forward"] == []
    assert [r["result_id"] for r in rep["rereason"]] == ["vr1"]
    rr = rep["rereason"][0]
    assert rr["kind"] == "needs_rereasoning"
    assert rr["residual_id"] == "rereason-vr1"
    assert "f" in rr["touched"]
    assert rr["cause"] == "closure-changed"
    assert rr["target"] == {"target_type": "artifact", "target_id": "vr1"}


# ---- 3. transitive (the killer case): theirs changes helper g, not f -------

def test_transitive_touch_rereason():
    ours = _trace(SRC, results=[_proved("f")])
    # g's body changes; f's own text is untouched, but g is in f's closure.
    theirs = _trace("let g x = x + 500\nlet f x = g x + 2\nlet h x = x * 10\n")
    rep = merge(ours, theirs)
    # g's edit changes g's checksum AND (via the closure checksum) f's — both land in the delta.
    assert "g" in rep["delta"]["changed"]
    assert rep["carried_forward"] == []
    rr = rep["rereason"][0]
    assert rr["result_id"] == "vr1"
    assert "g" in rr["touched"]  # closure caught the cross-cut


# ---- 4. added / removed symbol present in delta ---------------------------

def test_added_and_removed_in_delta():
    ours = _trace("let g x = x + 1\nlet f x = g x + 2\n")
    theirs = _trace("let f x = 42\nlet k x = x - 1\n")  # g removed, k added, f changed
    rep = merge(ours, theirs)
    assert rep["delta"]["added"] == ["k"]
    assert rep["delta"]["removed"] == ["g"]
    assert "f" in rep["delta"]["changed"]


# ---- 5. totality: every standing result bucketed exactly once -------------

def test_totality():
    ours = _trace(SRC, results=[
        _proved("f", vg="vgf", vr="vrf"),
        _proved("h", vg="vgh", vr="vrh"),
    ])
    theirs = _trace("let g x = x + 1\nlet f x = g x + 2\nlet h x = x * 999\n")  # h changed
    rep = merge(ours, theirs)
    assert rep["totality_ok"] is True
    ids = {c["result_id"] for c in rep["carried_forward"]} | {r["result_id"] for r in rep["rereason"]}
    assert ids == {"vrf", "vrh"}
    # h touched -> rereason; f disjoint -> carried; each exactly once
    assert {c["result_id"] for c in rep["carried_forward"]} == {"vrf"}
    assert {r["result_id"] for r in rep["rereason"]} == {"vrh"}
    assert rep["counts"] == {"standing": 2, "carried": 1, "rereason": 1, "delta": 1}


# ---- 6. no-false-fresh: a genuinely-affected result is NEVER carried ------

def test_no_false_fresh():
    ours = _trace(SRC, results=[_proved("f")])
    theirs = _trace("let g x = x + 500\nlet f x = g x + 2\nlet h x = x * 10\n")  # transitive hit
    rep = merge(ours, theirs)
    carried_ids = {c["result_id"] for c in rep["carried_forward"]}
    assert "vr1" not in carried_ids  # affected result never appears as fresh
    assert "vr1" in {r["result_id"] for r in rep["rereason"]}


# ---- 7. 3-way base attribution -------------------------------------------

def test_three_way_base_attribution():
    base = _trace("let g x = x + 1\nlet f x = g x + 2\n")
    # OURS changed g (vs base); THEIRS is identical to base (didn't touch g).
    ours = _trace("let g x = x + 7\nlet f x = g x + 2\n", results=[_proved("f")])
    theirs = _trace("let g x = x + 1\nlet f x = g x + 2\n")

    # With --base: theirs did NOT change g vs base -> g not in delta -> f carried forward.
    rep3 = merge(ours, theirs, base=base)
    assert rep3["delta"]["changed"] == []
    assert {c["result_id"] for c in rep3["carried_forward"]} == {"vr1"}
    assert rep3["rereason"] == []

    # Contrast 2-way (no base): reference is OURS, whose g differs from theirs -> g in delta -> rereason.
    rep2 = merge(ours, theirs)
    assert "g" in rep2["delta"]["changed"]
    assert {r["result_id"] for r in rep2["rereason"]} == {"vr1"}


# ---- 8. assumption-awareness ---------------------------------------------

def test_assumption_awareness():
    ours = _trace(SRC, results=[_proved("f")],
                  residuals=[{"residual_id": "as1", "kind": "assumption", "status": "open",
                              "statement": "assume g is monotone", "related_artifact_ids": ["vr1"]}])
    theirs = _trace("let g x = x + 500\nlet f x = g x + 2\nlet h x = x * 10\n")  # touches closure
    rep = merge(ours, theirs)
    rr = rep["rereason"][0]
    assert rr["assumptions_in_question"] == ["as1"]
    assert "as1" in rr["statement"]


def test_assumption_ignored_when_disjoint():
    # An open assumption on a result that is NOT touched stays silent (it's carried forward).
    ours = _trace(SRC, results=[_proved("f")],
                  residuals=[{"residual_id": "as1", "kind": "assumption", "status": "open",
                              "related_artifact_ids": ["vr1"]}])
    theirs = _trace("let g x = x + 1\nlet f x = g x + 2\nlet h x = x * 999\n")  # only h
    rep = merge(ours, theirs)
    assert {c["result_id"] for c in rep["carried_forward"]} == {"vr1"}
    assert rep["rereason"] == []


def test_closed_assumption_not_cited():
    ours = _trace(SRC, results=[_proved("f")],
                  residuals=[{"residual_id": "as1", "kind": "assumption", "status": "addressed",
                              "related_artifact_ids": ["vr1"]}])
    theirs = _trace("let g x = x + 500\nlet f x = g x + 2\nlet h x = x * 10\n")
    rep = merge(ours, theirs)
    assert rep["rereason"][0]["assumptions_in_question"] == []


# ---- edge cases ----------------------------------------------------------

def test_empty_delta_all_carried():
    ours = _trace(SRC, results=[_proved("f"), _proved("h", vg="vgh", vr="vrh")])
    theirs = _trace(SRC)  # identical source -> empty delta
    rep = merge(ours, theirs)
    assert rep["delta"] == {"changed": [], "added": [], "removed": []}
    assert len(rep["carried_forward"]) == 2
    assert rep["rereason"] == []
    assert rep["totality_ok"] is True


def test_empty_trace():
    ours = {"trace_id": "t", "artifacts": []}
    theirs = {"trace_id": "t", "artifacts": []}
    rep = merge(ours, theirs)
    assert rep["counts"]["standing"] == 0
    assert rep["carried_forward"] == []
    assert rep["rereason"] == []
    assert rep["totality_ok"] is True


def test_standing_only_proved_counts():
    # A refuted result is a live issue, not a standing fact -> not a standing result.
    refuted = [
        {"artifact_id": "vgr", "artifact_type": "VerificationGoal", "producer_action_id": 2,
         "payload": {"goal_id": "GR", "target_symbol": "f"}},
        {"artifact_id": "vrr", "artifact_type": "VerificationResult", "producer_action_id": 3,
         "payload": {"goal_id": "GR", "goal_artifact_id": "vgr", "status": "refuted"}},
    ]
    t = _trace(SRC, results=[refuted])
    assert _standing_results(t) == []


def test_latest_standing_wins():
    # Two proofs about f; the later one is the standing result.
    ours = _trace(SRC, results=[
        _proved("f", vg="vg_old", vr="vr_old", step=2),
        _proved("f", vg="vg_new", vr="vr_new", step=10),
    ])
    ids = {r["result_id"] for r in _standing_results(ours)}
    assert ids == {"vr_new"}


def test_symbols_latest_revision_wins():
    # A later model revision that drops h changes the symbol set / checksums accordingly.
    t = {"trace_id": "t", "artifacts": [
        _model("let g x = x + 1\nlet h x = x\n", aid="m1", step=1),
        _model("let g x = x + 2\n", aid="m2", step=5),  # later: g redefined, h still present from m1
    ]}
    # h from m1 survives (never redefined), g's latest def wins.
    assert "g" in _symbols(t) and "h" in _symbols(t)


def test_delta_helper_direct():
    ours = _trace("let a x = x\nlet b x = x\n")
    theirs = _trace("let a x = x + 1\nlet c x = x\n")  # a changed; b -> c is a rename (identical body)
    d = merge_delta(ours, theirs)
    # Component-aware (2b): `b` and `c` have byte-identical bodies modulo their own name, so `b -> c` is
    # an exact-fingerprint rename (content unchanged), NOT a remove+add. `a` still changed.
    assert d["changed"] == ["a"]
    assert d["added"] == [] and d["removed"] == []
    assert d["renamed"] == [{"from": "b", "to": "c", "changed": False}]


# ---- 2b. rename-aware merge_delta ----------------------------------------

# A helper `g` with a distinctive multi-line body. A rename touches only the signature line, so with a
# body of enough shared lines the similarity stays confidently above the 80% floor (identity.iml's
# SIM_MIN) while an unrelated add is far below it.
_G_BODY = ("let g x =\n"
           "  let a = x + 1 in\n"
           "  let b = a * 2 in\n"
           "  let c = b + 4 in\n"
           "  let d = c * 5 in\n"
           "  let e = d - 6 in\n"
           "  let f0 = e + 8 in\n"
           "  let g0 = f0 * 9 in\n"
           "  let h0 = g0 - 10 in\n"
           "  let i0 = h0 + 11 in\n"
           "  let j0 = i0 * 12 in\n"
           "  j0 + 7\n")
_G2_BODY_SAME = _G_BODY.replace("let g x =", "let g2 x =")           # rename, identical body
_G2_BODY_CHANGED = _G2_BODY_SAME.replace("  j0 + 7\n", "  j0 + 999\n")  # rename + one-line body change
_F_ON_G = "let f x = g x + 2\n"
_F_ON_G2 = "let f x = g2 x + 2\n"


def test_rename_unchanged_carried_forward():
    # ours proves f (which calls helper g); theirs renames g -> g2 with an IDENTICAL body.
    ours = _trace(_G_BODY + _F_ON_G, results=[_proved("f")])
    theirs = _trace(_G2_BODY_SAME + _F_ON_G2)
    rep = merge(ours, theirs)
    # g is a rename, content unchanged -> NOT in the delta; renamed records g -> g2 (changed:false).
    assert rep["delta"]["renamed"] == [{"from": "g", "to": "g2", "changed": False}]
    assert "g" not in rep["delta"]["removed"]
    assert "g2" not in rep["delta"]["added"]
    assert "g" not in rep["delta"]["changed"]
    # f only differs by the callee's NAME; f's own text changed (g -> g2) so f is a real change and
    # re-reasons. The payoff is that g's *proof/closure* is not spuriously remove+add'd.
    # (Contrast pre-2b: g removed + g2 added would put both in the delta.)
    assert rep["delta"]["removed"] == [] and rep["delta"]["added"] == []


def test_rename_unchanged_pure_helper_carried_forward():
    # Isolate the payoff: theirs renames ONLY the unused helper g -> g2, f untouched (does not call g).
    src = _G_BODY + "let f x = x + 2\n"
    ours = _trace(src, results=[_proved("f")])
    theirs = _trace(_G2_BODY_SAME + "let f x = x + 2\n")
    rep = merge(ours, theirs)
    assert rep["delta"]["renamed"] == [{"from": "g", "to": "g2", "changed": False}]
    # Nothing in the delta at all -> f's proof is carried forward, NOT re-reasoned.
    assert rep["delta"]["changed"] == []
    assert rep["delta"]["added"] == [] and rep["delta"]["removed"] == []
    assert {c["result_id"] for c in rep["carried_forward"]} == {"vr1"}
    assert rep["rereason"] == []


def test_rename_changed_rereasons():
    # theirs renames g -> g2 AND changes its body; f calls the helper.
    ours = _trace(_G_BODY + _F_ON_G, results=[_proved("f")])
    theirs = _trace(_G2_BODY_CHANGED + _F_ON_G2)
    rep = merge(ours, theirs)
    assert rep["delta"]["renamed"] == [{"from": "g", "to": "g2", "changed": True}]
    # A content-changed rename: g (the old name) lands in `changed`, not remove+add.
    assert "g" in rep["delta"]["changed"]
    assert "g" not in rep["delta"]["removed"]
    assert "g2" not in rep["delta"]["added"]
    # g is in f's closure -> f re-reasons.
    assert {r["result_id"] for r in rep["rereason"]} == {"vr1"}
    assert rep["carried_forward"] == []


def test_genuine_remove_add_stays():
    # A removed symbol with no similar added counterpart stays removed; the unrelated add stays added.
    ours = _trace(_G_BODY + "let f x = x + 2\n", results=[_proved("f")])
    theirs = _trace("let totally_new p q = p * q - 7\nlet f x = x + 2\n")  # g removed, unrelated add
    rep = merge(ours, theirs)
    assert rep["delta"].get("renamed") is None  # no rename detected
    assert rep["delta"]["removed"] == ["g"]
    assert rep["delta"]["added"] == ["totally_new"]


def test_ambiguous_rename_stays_remove_add():
    # Two added symbols equally similar to the removed one -> never-guess -> stays remove+add.
    g2a = _G_BODY.replace("let g x =", "let g2a x =")
    g2b = _G_BODY.replace("let g x =", "let g2b x =")
    ours = _trace(_G_BODY + "let f x = x + 2\n", results=[_proved("f")])
    theirs = _trace(g2a + g2b + "let f x = x + 2\n")  # g removed; two equally-similar adds
    rep = merge(ours, theirs)
    assert rep["delta"].get("renamed") is None
    assert rep["delta"]["removed"] == ["g"]
    assert set(rep["delta"]["added"]) == {"g2a", "g2b"}

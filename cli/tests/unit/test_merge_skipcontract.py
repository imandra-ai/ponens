"""Unit tests for the SkipContract branch of residual-aware trace MERGE (ponens.merge).

Upgrades `classify` from two live branches (SkipDisjoint / ReReason) to the three the proved model in
`formal/merge/classify.iml` has, for the SOUND slice only: the SkipContract branch fires when EVERY
genuinely-changed touched dependency of a standing result is `uninterpreted` in OURS's model
assumptions. The proved classifier's opaque `dep_kind ∈ {Uninterpreted, Typed, Axiomatized, Pinned}` is
realized at the trace level by the model artifact's structured `payload.assumptions` list of
`{target, abstraction, discharged?, ...}` (the producer's `ArtifactAssumption`, where
`abstraction ∈ 'concrete'|'contract'|'uninterpreted'|'pinned'`).

The sound rule: `uninterpreted` = the result proved its property for ALL values of that opaque dep, so
any merge change to the dep leaves the property holding -> carry forward. `contract` (even discharged),
`pinned`, `concrete`, and no-assumption -> re-reason (stale discharge / genuine dependence).
"""

from ponens.merge import merge, _assumptions_index


# ---- trace builders (mirror test_merge.py, plus payload.assumptions) -------

def _model(src, aid="m1", step=1, assumptions=None):
    payload = {"iml_code": src}
    if assumptions is not None:
        payload["assumptions"] = assumptions
    return {"artifact_id": aid, "artifact_type": "IMLModel", "producer_action_id": step,
            "payload": payload}


def _proved(sym, vg="vg1", vr="vr1", step=2):
    return [
        {"artifact_id": vg, "artifact_type": "VerificationGoal", "producer_action_id": step,
         "payload": {"goal_id": vg + "-G", "target_symbol": sym,
                     "description": f"property of {sym}"}},
        {"artifact_id": vr, "artifact_type": "VerificationResult", "producer_action_id": step + 1,
         "derived_from": [vg], "payload": {"goal_id": vg + "-G", "goal_artifact_id": vg,
                                           "status": "proved"}},
    ]


def _trace(src, results=None, assumptions=None):
    t = {"trace_id": "t", "artifacts": [_model(src, assumptions=assumptions)]}
    for r in results or []:
        t["artifacts"].extend(r)
    return t


# f depends on g (transitive); f's OWN body is unchanged across the merge in every "g changes" case.
SRC = "let g x = x + 1\nlet f x = g x + 2\n"
SRC_G_CHANGED = "let g x = x + 500\nlet f x = g x + 2\n"  # only g's body differs; f's body identical

# f depends on g AND h; both g and h are dependencies of f.
SRC_GH = "let g x = x + 1\nlet h x = x - 1\nlet f x = g x + h x\n"
SRC_GH_BOTH_CHANGED = "let g x = x + 500\nlet h x = x - 500\nlet f x = g x + h x\n"


def _assert_totality(rep):
    carried = {c["result_id"] for c in rep["carried_forward"]}
    rereason = {r["result_id"] for r in rep["rereason"]}
    assert rep["totality_ok"] is True
    assert carried.isdisjoint(rereason)
    assert carried | rereason == {"vr1"}  # single standing result in these fixtures


# ---- 0. the index reads payload.assumptions -------------------------------

def test_assumptions_index_reads_payload():
    ours = _trace(SRC, results=[_proved("f")],
                  assumptions=[{"target": "g", "kind": "callee", "abstraction": "uninterpreted"}])
    assert _assumptions_index(ours) == {"g": "uninterpreted"}
    # tolerant: an entry missing target/abstraction is skipped, empty/missing yields {}
    assert _assumptions_index(_trace(SRC, results=[_proved("f")])) == {}
    messy = _trace(SRC, results=[_proved("f")],
                   assumptions=[{"kind": "callee"}, {"target": "g"}, "not-a-dict", None])
    assert _assumptions_index(messy) == {}


# ---- 1. uninterpreted -> carried forward (the SkipContract win) -----------

def test_uninterpreted_carried_forward():
    ours = _trace(SRC, results=[_proved("f")],
                  assumptions=[{"target": "g", "kind": "callee", "abstraction": "uninterpreted"}])
    theirs = _trace(SRC_G_CHANGED)  # g's body changes
    rep = merge(ours, theirs)
    assert "g" in rep["delta"]["changed"]
    assert rep["rereason"] == []
    assert [c["result_id"] for c in rep["carried_forward"]] == ["vr1"]
    cf = rep["carried_forward"][0]
    assert cf["basis"] == "uninterpreted-opaque"
    assert cf["via_assumptions"] == ["g"]
    _assert_totality(rep)


def test_contrast_no_assumption_rereasons():
    """Same code change, but WITHOUT the uninterpreted assumption -> re-reason. Isolates that the
    SkipContract win comes from the assumption data, not the code."""
    ours = _trace(SRC, results=[_proved("f")])  # no assumptions declared
    theirs = _trace(SRC_G_CHANGED)
    rep = merge(ours, theirs)
    assert rep["carried_forward"] == []
    assert [r["result_id"] for r in rep["rereason"]] == ["vr1"]
    _assert_totality(rep)


# ---- 2. pinned -> re-reason -----------------------------------------------

def test_pinned_rereasons():
    ours = _trace(SRC, results=[_proved("f")],
                  assumptions=[{"target": "g", "kind": "callee", "abstraction": "pinned"}])
    theirs = _trace(SRC_G_CHANGED)
    rep = merge(ours, theirs)
    assert rep["carried_forward"] == []
    assert [r["result_id"] for r in rep["rereason"]] == ["vr1"]
    _assert_totality(rep)


# ---- 3. contract (discharged) but callee changed -> re-reason -------------

def test_contract_discharged_but_callee_changed_rereasons():
    """A discharged contract's proof was over the OLD callee body; the callee changed, so the discharge is
    stale and there is no recorded reproof formula -> re-reason (sound; reproof deferred)."""
    ours = _trace(SRC, results=[_proved("f")],
                  assumptions=[{"target": "g", "kind": "callee", "abstraction": "contract",
                                "discharged": True}])
    theirs = _trace(SRC_G_CHANGED)
    rep = merge(ours, theirs)
    assert rep["carried_forward"] == []
    assert [r["result_id"] for r in rep["rereason"]] == ["vr1"]
    _assert_totality(rep)


# ---- 4. concrete / no assumption -> re-reason (sound fallback) ------------

def test_concrete_rereasons():
    ours = _trace(SRC, results=[_proved("f")],
                  assumptions=[{"target": "g", "kind": "callee", "abstraction": "concrete"}])
    theirs = _trace(SRC_G_CHANGED)
    rep = merge(ours, theirs)
    assert rep["carried_forward"] == []
    assert [r["result_id"] for r in rep["rereason"]] == ["vr1"]
    _assert_totality(rep)


# ---- 5. mixed touched: one uninterpreted, one concrete -> re-reason -------

def test_mixed_touched_rereasons():
    """R touches g (uninterpreted) AND h (concrete); BOTH change. Not ALL genuinely-changed touched deps
    are opaque -> re-reason (never-false-fresh)."""
    ours = _trace(SRC_GH, results=[_proved("f")],
                  assumptions=[{"target": "g", "kind": "callee", "abstraction": "uninterpreted"},
                               {"target": "h", "kind": "callee", "abstraction": "concrete"}])
    theirs = _trace(SRC_GH_BOTH_CHANGED)
    rep = merge(ours, theirs)
    assert rep["carried_forward"] == []
    assert [r["result_id"] for r in rep["rereason"]] == ["vr1"]
    _assert_totality(rep)


def test_mixed_touched_all_uninterpreted_carried():
    """Complement of test 5: both changed deps are uninterpreted -> carry forward."""
    ours = _trace(SRC_GH, results=[_proved("f")],
                  assumptions=[{"target": "g", "kind": "callee", "abstraction": "uninterpreted"},
                               {"target": "h", "kind": "callee", "abstraction": "uninterpreted"}])
    theirs = _trace(SRC_GH_BOTH_CHANGED)
    rep = merge(ours, theirs)
    assert rep["rereason"] == []
    cf = rep["carried_forward"][0]
    assert cf["basis"] == "uninterpreted-opaque"
    assert cf["via_assumptions"] == ["g", "h"]
    _assert_totality(rep)


# ---- 5b. result's OWN body changed -> re-reason even if a dep is opaque ---

def test_own_body_change_blocks_skip():
    """f's own body changes (not just g). Even with g uninterpreted, f is a genuinely-changed touched
    component that is not opaque -> re-reason."""
    ours = _trace(SRC, results=[_proved("f")],
                  assumptions=[{"target": "g", "kind": "callee", "abstraction": "uninterpreted"}])
    theirs = _trace("let g x = x + 500\nlet f x = g x + 99\n")  # BOTH g and f bodies change
    rep = merge(ours, theirs)
    assert rep["carried_forward"] == []
    assert [r["result_id"] for r in rep["rereason"]] == ["vr1"]
    _assert_totality(rep)


# ---- 6. disjoint still SkipDisjoint (unchanged) ---------------------------

def test_disjoint_still_skipdisjoint():
    """An unrelated symbol changes; f's closure is untouched -> SkipDisjoint, regardless of assumptions."""
    ours = _trace("let g x = x + 1\nlet f x = g x + 2\nlet k x = x * 10\n", results=[_proved("f")],
                  assumptions=[{"target": "g", "kind": "callee", "abstraction": "uninterpreted"}])
    theirs = _trace("let g x = x + 1\nlet f x = g x + 2\nlet k x = x * 999\n")  # only k changed
    rep = merge(ours, theirs)
    assert rep["delta"]["changed"] == ["k"]
    assert rep["rereason"] == []
    cf = rep["carried_forward"][0]
    assert cf["basis"] == "closure-disjoint"  # NOT uninterpreted-opaque: nothing in f's closure touched
    _assert_totality(rep)


# ---- 7. totality holds in every case (covered by _assert_totality above) --

def test_totality_across_cases():
    for maker in (
        lambda: (_trace(SRC, results=[_proved("f")],
                        assumptions=[{"target": "g", "abstraction": "uninterpreted"}]),
                 _trace(SRC_G_CHANGED)),
        lambda: (_trace(SRC, results=[_proved("f")],
                        assumptions=[{"target": "g", "abstraction": "pinned"}]),
                 _trace(SRC_G_CHANGED)),
        lambda: (_trace(SRC, results=[_proved("f")]), _trace(SRC_G_CHANGED)),
    ):
        ours, theirs = maker()
        rep = merge(ours, theirs)
        _assert_totality(rep)

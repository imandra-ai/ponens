"""Unit tests for the goal-COVERAGE layer of trace MERGE (ponens.merge).

SelectorRegression, realized over `goal.scope` (the coverage mechanism that exists today): a merge that
changes WHAT A GOAL MUST COVER — adds/removes an in-scope component — regresses the obligation, even when
no existing proof's closure changed. This is a distinct goal-level section from the result-level
carried_forward/rereason buckets, and is purely additive to the merge report.
"""

from ponens.merge import merge, _in_scope


# ---- trace builders (mirroring test_merge.py) -----------------------------

def _model(src, aid="m1", step=1):
    return {"artifact_id": aid, "artifact_type": "IMLModel", "producer_action_id": step,
            "payload": {"iml_code": src}}


def _proved(sym, vg="vg1", vr="vr1", step=2):
    return [
        {"artifact_id": vg, "artifact_type": "VerificationGoal", "producer_action_id": step,
         "payload": {"goal_id": vg + "-G", "target_symbol": sym,
                     "description": f"property of {sym}"}},
        {"artifact_id": vr, "artifact_type": "VerificationResult", "producer_action_id": step + 1,
         "derived_from": [vg], "payload": {"goal_id": vg + "-G", "goal_artifact_id": vg,
                                           "status": "proved"}},
    ]


def _trace(src, results=None, goals=None, step=1):
    t = {"trace_id": "t", "artifacts": [_model(src, step=step)]}
    for r in results or []:
        t["artifacts"].extend(r)
    if goals is not None:
        t["goals"] = goals
    return t


def _goal(gid="G1", scope=None):
    return {"id": gid, "intent": f"cover {gid}", "scope": scope or []}


# ---- 1. added in-scope unproven -> regression -----------------------------

def test_added_in_scope_unproven_regresses():
    ours = _trace("let payments x = x + 1\n",
                  goals=[_goal("G1", scope=["payments"])])
    theirs = _trace("let payments x = x + 1\nlet payments_newfee x = x + 5\n")
    rep = merge(ours, theirs)
    assert "payments_newfee" in rep["delta"]["added"]
    cr = rep["coverage_regressions"]
    assert len(cr) == 1
    entry = cr[0]
    assert entry["goal_id"] == "G1"
    assert entry["kind"] == "coverage_regression"
    assert entry["residual_id"] == "coverage-G1"
    assert entry["added_members"] == ["payments_newfee"]
    assert entry["removed_members"] == []
    assert entry["severity"] == "medium"
    assert entry["status"] == "open"
    assert entry["derived"] is True
    assert entry["scope"] == ["payments"]


# ---- 2. added out-of-scope -> no regression -------------------------------

def test_added_out_of_scope_no_regression():
    ours = _trace("let payments x = x + 1\n",
                  goals=[_goal("G1", scope=["payments"])])
    theirs = _trace("let payments x = x + 1\nlet shipping x = x + 5\n")  # not matching scope
    rep = merge(ours, theirs)
    assert "shipping" in rep["delta"]["added"]
    assert "coverage_regressions" not in rep


# ---- 3. added in-scope BUT already proved -> no regression ----------------

def test_added_in_scope_but_proved_no_regression():
    ours = _trace("let payments x = x + 1\n",
                  goals=[_goal("G1", scope=["payments"])])
    # theirs adds payments_newfee AND carries a standing proof about it -> covered in merged view.
    theirs = _trace("let payments x = x + 1\nlet payments_newfee x = x + 5\n",
                    results=[_proved("payments_newfee", vg="vgn", vr="vrn")])
    rep = merge(ours, theirs)
    assert "payments_newfee" in rep["delta"]["added"]
    assert "coverage_regressions" not in rep


# ---- 4. removed in-scope -> recorded -------------------------------------

def test_removed_in_scope_recorded():
    ours = _trace("let payments x = x + 1\nlet payments_legacy x = x - 1\n",
                  goals=[_goal("G1", scope=["payments"])])
    theirs = _trace("let payments x = x + 1\n")  # payments_legacy removed
    rep = merge(ours, theirs)
    assert "payments_legacy" in rep["delta"]["removed"]
    cr = rep["coverage_regressions"]
    assert len(cr) == 1
    entry = cr[0]
    assert entry["removed_members"] == ["payments_legacy"]
    assert entry["added_members"] == []
    assert entry["severity"] == "low"


# ---- 5. no scope / no goals -> field omitted -----------------------------

def test_goal_without_scope_no_field():
    ours = _trace("let payments x = x + 1\n", goals=[_goal("G1", scope=[])])
    theirs = _trace("let payments x = x + 1\nlet payments_newfee x = x + 5\n")
    rep = merge(ours, theirs)
    assert "coverage_regressions" not in rep


def test_no_goals_no_field():
    ours = _trace("let payments x = x + 1\n")  # no goals key at all
    theirs = _trace("let payments x = x + 1\nlet payments_newfee x = x + 5\n")
    rep = merge(ours, theirs)
    assert "coverage_regressions" not in rep
    # sanity: the rest of the report is present and unchanged in shape
    assert set(rep.keys()) == {"delta", "carried_forward", "rereason", "totality_ok", "counts"}


# ---- 6. rename not double-counted ----------------------------------------

# A distinctive multi-line in-scope helper whose rename touches only the signature line, so the
# similarity resolver confidently detects a rename (see test_merge.py's _G_BODY convention).
_PAY_BODY = ("let payments_calc x =\n"
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
_PAY_BODY_RENAMED = _PAY_BODY.replace("let payments_calc x =", "let payments_compute x =")


def test_rename_not_double_counted():
    ours = _trace(_PAY_BODY, goals=[_goal("G1", scope=["payments"])])
    theirs = _trace(_PAY_BODY_RENAMED)  # payments_calc -> payments_compute, identical body
    rep = merge(ours, theirs)
    # rename reconciled by merge_delta: not in added/removed.
    assert rep["delta"].get("renamed") == [{"from": "payments_calc", "to": "payments_compute",
                                            "changed": False}]
    assert rep["delta"]["added"] == [] and rep["delta"]["removed"] == []
    # so no coverage churn: the renamed component appears as neither added nor removed member.
    assert "coverage_regressions" not in rep


# ---- helper predicate ----------------------------------------------------

def test_in_scope_predicate():
    assert _in_scope("payments_newfee", ["payments"]) is True   # substring
    assert _in_scope("payments", ["Payments"]) is True          # case-insensitive
    assert _in_scope("shipping", ["payments"]) is False
    assert _in_scope("", ["payments"]) is False
    assert _in_scope("payments", []) is False

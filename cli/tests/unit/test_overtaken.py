"""A gap retires when its own stated condition comes true - and never by itself."""
import sys; sys.path.insert(0, 'cli')
from ponens import lineage as L
from ponens import goals as G


def _trace(residual, evidence=0, arts=()):
    return {
        "artifacts": [
            {"artifact_id": residual["residual_id"], "artifact_type": "Residual", "payload": residual},
            *[{"artifact_id": "e%d" % i, "artifact_type": "IMLModel", "payload": {}} for i in range(evidence)],
            *arts,
        ],
        "actions": [{"id": 1}],
    }


def _ask_gap(**over):
    r = {"residual_id": "r1", "kind": "open_question", "severity": "high", "status": "open",
         "statement": "The turn ended by asking the user and recorded nothing.",
         "suggested_check": "Answer the question, then record the answer.",
         "introduced_by_action_id": 1}
    r.update(over)
    return r


def test_a_gap_without_a_condition_never_retires():
    """Old traces, and every gap whose producer did not commit to a falsifiable claim."""
    [r] = L.residual_surface(_trace(_ask_gap(), evidence=3))
    assert "overtaken" not in r


def test_later_actions_retire_a_claim_about_an_empty_turn():
    [r] = L.residual_surface(_trace(_ask_gap(retires_when="more_evidence", record_size_at_declaration=0), evidence=3))
    assert r["overtaken"]["why"].startswith("the record has grown")
    assert "confirm it still applies" in r["overtaken"]["recheck"]


def test_it_does_not_retire_while_the_record_has_not_moved():
    g = _ask_gap(retires_when="more_evidence", record_size_at_declaration=3)
    [r] = L.residual_surface(_trace(g, evidence=3))
    assert "overtaken" not in r


def test_another_GAP_does_not_count_as_the_record_moving_on():
    """Bookkeeping about the record is not evidence in it - otherwise a gap retires the one before it."""
    t = _trace(_ask_gap(retires_when="more_evidence", record_size_at_declaration=0), evidence=0)
    t["artifacts"].append({"artifact_id": "r9", "artifact_type": "Residual",
                           "payload": {"residual_id": "r9", "kind": "assumption", "status": "open",
                                       "statement": "something else"}})
    r = next(x for x in L.residual_surface(t) if x["residual_id"] == "r1")
    assert "overtaken" not in r


def test_a_gap_that_stamped_no_size_claims_nothing():
    [r] = L.residual_surface(_trace(_ask_gap(retires_when="more_evidence"), evidence=5))
    assert "overtaken" not in r


def test_retiring_is_not_closing():
    """The status stays open, so every consumer that only reads `status` still reports the gap."""
    [r] = L.residual_surface(_trace(_ask_gap(retires_when="more_evidence", record_size_at_declaration=0), evidence=3))
    assert r["status"] == "open"


def test_a_failing_check_retires_on_a_later_pass():
    g = {"residual_id": "r1", "kind": "unverified", "severity": "high", "status": "open",
         "statement": "`test_fees.py` fails its own tests - 2 of 3 did not hold.",
         "suggested_check": "fix the failures", "introduced_by_action_id": 1,
         "retires_when": {"passing_result_for": "test_fees.py"}}
    later = {"artifact_id": "fr9", "artifact_type": "CommandResult", "producer_action_id": 5,
             "payload": {"target": "test_fees.py", "status": "passed"}}
    [r] = L.residual_surface(_trace(g, evidence=3, arts=(later,)))
    assert "has passed since" in r["overtaken"]["why"] and r["overtaken"]["by"] == "fr9"


def test_an_EARLIER_pass_does_not_retire_it():
    """The suite passing before the failure was recorded says nothing about the failure."""
    g = {"residual_id": "r1", "kind": "unverified", "severity": "high", "status": "open",
         "statement": "fails", "suggested_check": "fix", "introduced_by_action_id": 4,
         "retires_when": {"passing_result_for": "test_fees.py"}}
    earlier = {"artifact_id": "fr1", "artifact_type": "CommandResult", "producer_action_id": 2,
               "payload": {"target": "test_fees.py", "status": "passed"}}
    [r] = L.residual_surface(_trace(g, evidence=3, arts=(earlier,)))
    assert "overtaken" not in r


def test_a_later_FAILING_result_does_not_retire_it():
    g = {"residual_id": "r1", "kind": "unverified", "severity": "high", "status": "open",
         "statement": "fails", "suggested_check": "fix", "introduced_by_action_id": 1,
         "retires_when": {"passing_result_for": "test_fees.py"}}
    later = {"artifact_id": "fr9", "artifact_type": "CommandResult", "producer_action_id": 5,
             "payload": {"target": "test_fees.py", "status": "failed"}}
    [r] = L.residual_surface(_trace(g, evidence=3, arts=(later,)))
    assert "overtaken" not in r


def test_next_demotes_an_overtaken_gap_below_a_live_one():
    live = {"residual_id": "r2", "kind": "unverified", "severity": "high", "status": "open",
            "statement": "the suite fails", "suggested_check": "fix it", "introduced_by_action_id": 1}
    t = _trace(_ask_gap(retires_when="more_evidence", record_size_at_declaration=0), evidence=3)
    t["artifacts"].append({"artifact_id": "r2", "artifact_type": "Residual", "payload": live})
    steps = G.next_steps(t) if hasattr(G, "next_steps") else None
    assert steps is not None, "next_steps not found - check the entry point name"
    gaps = [s for s in steps if s["kind"] == "gap"]
    assert gaps[0]["item_id"] == "r2", "the live gap must come first"
    assert gaps[-1]["item_id"] == "r1"
    assert gaps[-1]["why"].startswith("may no longer apply")


# ── staleness: re-established, or abandoned ─────────────────────────────────────────────────────────

def _stale(rid, about, action):
    return {"residual_id": rid, "kind": "limitation", "severity": "medium", "status": "open",
            "statement": "`m.iml` changed since this result was established [%s]." % about,
            "suggested_check": "re-verify against the current source",
            "related_artifact_ids": [about], "introduced_by_action_id": action}


def _result(aid, symbol, action, kind="StateSpaceAnalysisResult"):
    return {"artifact_id": aid, "artifact_type": kind, "producer_action_id": action,
            "payload": {"target_symbol": symbol}}


def _t(residuals, arts):
    return {"artifacts": [{"artifact_id": r["residual_id"], "artifact_type": "Residual", "payload": r}
                          for r in residuals] + list(arts),
            "actions": [{"id": 1}]}


def test_a_property_re_established_later_retires_its_staleness():
    t = _t([_stale("r1", "fr1", 3)],
           [_result("fr1", "split_bill", 1), _result("fr7", "split_bill", 5)])
    r = next(x for x in L.residual_surface(t) if x["residual_id"] == "r1")
    assert "was established again after this" in r["overtaken"]["why"]
    assert r["overtaken"]["by"] == "fr7"
    assert "abandoned" not in r


def test_a_property_never_re_established_is_ABANDONED_not_retired():
    """40 of 48 measured staleness gaps are this. Retiring them would hide real unfinished work."""
    t = _t([_stale("r1", "fr1", 3)], [_result("fr1", "sum_property_holds", 1)])
    r = next(x for x in L.residual_surface(t) if x["residual_id"] == "r1")
    assert "overtaken" not in r, "nothing re-established it, so nothing answers it"
    assert r["abandoned"] == {"symbol": "sum_property_holds", "result": "fr1"}


def test_an_EARLIER_result_for_the_symbol_does_not_retire_it():
    t = _t([_stale("r1", "fr5", 6)],
           [_result("fr5", "split_bill", 4), _result("fr1", "split_bill", 2)])
    r = next(x for x in L.residual_surface(t) if x["residual_id"] == "r1")
    assert "overtaken" not in r and r["abandoned"]["symbol"] == "split_bill"


def test_a_result_for_a_DIFFERENT_symbol_does_not_retire_it():
    t = _t([_stale("r1", "fr1", 3)],
           [_result("fr1", "sum_property_holds", 1), _result("fr7", "something_else", 5)])
    r = next(x for x in L.residual_surface(t) if x["residual_id"] == "r1")
    assert "overtaken" not in r and r["abandoned"]["symbol"] == "sum_property_holds"


def test_abandoned_work_is_stated_once_and_says_what_happened():
    from ponens import overview as O
    t = _t([_stale("r%d" % i, "fr%d" % i, 3) for i in (1, 2, 3)],
           [_result("fr1", "p_one", 1), _result("fr2", "p_two", 1), _result("fr3", "p_three", 1)])
    t["goals"] = []
    block = O.render_overview(O.overview(t, None)).split("Gaps", 1)[1].split("Gate:", 1)[0]
    assert "3 properties were established and then abandoned" in block
    assert "p_one, p_two, p_three" in block
    assert block.count("changed since this result") == 0, "not also listed one by one"


# ── one cause, several consequences ────────────────────────────────────────────────────────────────

def _defeater(rid, about, sym):
    return {"residual_id": rid, "kind": "defeater", "severity": "high", "status": "open",
            "statement": "The IML model for `rounding.py` was hand-edited after this result [%s]." % about,
            "suggested_check": "re-run it", "related_artifact_ids": [about]}


def test_gaps_that_share_a_cause_are_stated_once_with_what_they_hit():
    """Four results undermined by ONE hand-edit were four lines differing only in the citation."""
    from ponens import overview as O
    rs = [_defeater("r1", "fr3", "split_bill"), _defeater("r2", "fr4", "parts_sum"),
          _defeater("r3", "fr5", "sum_holds")]
    arts = [_result("fr3", "split_bill", 1), _result("fr4", "parts_sum", 1), _result("fr5", "sum_holds", 1),
            # a later result for each, so they retire as staleness would not apply here
            ]
    t = _t(rs, arts); t["goals"] = []
    block = O.render_overview(O.overview(t, None)).split("Gaps", 1)[1].split("Gate:", 1)[0]
    assert block.count("hand-edited") == 1, "one line, not three"
    assert "3 results affected" in block
    assert "split_bill" in block and "parts_sum" in block and "sum_holds" in block


def test_the_fold_keeps_gaps_with_DIFFERENT_statements_apart():
    from ponens import overview as O
    a = _defeater("r1", "fr3", "split_bill")
    b = dict(_defeater("r2", "fr4", "parts_sum"))
    b["statement"] = "Something else entirely happened [fr4]."
    t = _t([a, b], [_result("fr3", "split_bill", 1), _result("fr4", "parts_sum", 1)]); t["goals"] = []
    block = O.render_overview(O.overview(t, None)).split("Gaps", 1)[1].split("Gate:", 1)[0]
    assert "hand-edited" in block and "Something else entirely" in block
    assert "results affected" not in block


def test_next_folds_them_too_so_both_views_agree():
    """`next` is the ACTIONABLE list; folding only the overview left it listing items 5, 7, 8 and 9."""
    rs = [_defeater("r1", "fr3", "split_bill"), _defeater("r2", "fr4", "parts_sum")]
    t = _t(rs, [_result("fr3", "split_bill", 1), _result("fr4", "parts_sum", 1)]); t["goals"] = []
    gaps = [s for s in G.next_steps(t) if s["kind"] == "gap"]
    assert len(gaps) == 1
    assert "2 results affected" in gaps[0]["label"]
    assert gaps[0]["also"] == ["r2"], "the folded ones are still named"


# ── an engine `unknown` that was later proved ──────────────────────────────────────────────────────

def _goal(aid, desc, action):
    return {"artifact_id": aid, "artifact_type": "VerificationGoal", "producer_action_id": action,
            "payload": {"kind": "verify", "description": desc}}


def _verdict(aid, goal_id, status, action, sym=None):
    return {"artifact_id": aid, "artifact_type": "VerificationResult", "producer_action_id": action,
            "payload": {"goal_artifact_id": goal_id, "status": status,
                        **({"target_symbol": sym} if sym else {})}}


def _undecided(rid, about, action):
    return {"residual_id": rid, "kind": "unverified", "severity": "high", "status": "open",
            "statement": "ImandraX could not decide the goal for f (P) [fr1].",
            "suggested_check": "bound the search", "related_artifact_ids": [about],
            "introduced_by_action_id": action}


LAMBDA = "fun m c -> m >= 0 ==> Impl.to_minor_units m (abs_currency c) = Entry.to_minor_units m c"


def test_the_same_goal_proved_later_retires_the_unknown():
    t = _t([_undecided("r1", "fr1-result", 3)],
           [_goal("fr1-goal", LAMBDA, 1), _verdict("fr1-result", "fr1-goal", "unknown", 2),
            _goal("fr5-goal", LAMBDA, 6), _verdict("fr5-result", "fr5-goal", "proved", 7)])
    r = next(x for x in L.residual_surface(t) if x["residual_id"] == "r1")
    assert "proved later" in r["overtaken"]["why"]
    assert r["overtaken"]["by"] == "fr5-result"


def test_a_DIFFERENT_property_about_the_same_function_does_not_retire_it():
    """The whole reason matching cannot go through the symbol: a weaker property would answer it."""
    t = _t([_undecided("r1", "fr1-result", 3)],
           [_goal("fr1-goal", LAMBDA, 1), _verdict("fr1-result", "fr1-goal", "unknown", 2, "to_minor_units"),
            _goal("fr5-goal", "fun m c -> m >= 0 ==> Impl.to_minor_units m (abs_currency c) >= 0", 6),
            _verdict("fr5-result", "fr5-goal", "proved", 7, "to_minor_units")])
    r = next(x for x in L.residual_surface(t) if x["residual_id"] == "r1")
    assert "overtaken" not in r


def test_a_REFORMULATION_does_not_retire_it_either():
    """Bounding the property to get it through proves a different statement."""
    t = _t([_undecided("r1", "fr1-result", 3)],
           [_goal("fr1-goal", LAMBDA, 1), _verdict("fr1-result", "fr1-goal", "unknown", 2),
            _goal("fr5-goal", LAMBDA + " [@@upto 3]", 6), _verdict("fr5-result", "fr5-goal", "proved", 7)])
    r = next(x for x in L.residual_surface(t) if x["residual_id"] == "r1")
    assert "overtaken" not in r


def test_an_EARLIER_proof_does_not_retire_a_later_unknown():
    t = _t([_undecided("r1", "fr5-result", 8)],
           [_goal("fr1-goal", LAMBDA, 1), _verdict("fr1-result", "fr1-goal", "proved", 2),
            _goal("fr5-goal", LAMBDA, 6), _verdict("fr5-result", "fr5-goal", "unknown", 7)])
    r = next(x for x in L.residual_surface(t) if x["residual_id"] == "r1")
    assert "overtaken" not in r


def test_a_bare_property_NAME_works_the_same_as_a_lambda():
    t = _t([_undecided("r1", "fr1-result", 3)],
           [_goal("fr1-goal", "never_negative", 1), _verdict("fr1-result", "fr1-goal", "unknown", 2),
            _goal("fr5-goal", "never_negative", 6), _verdict("fr5-result", "fr5-goal", "proved", 7)])
    r = next(x for x in L.residual_surface(t) if x["residual_id"] == "r1")
    assert r["overtaken"]["by"] == "fr5-result"


def test_whitespace_is_not_a_different_property():
    t = _t([_undecided("r1", "fr1-result", 3)],
           [_goal("fr1-goal", "fun x ->  x >= 0", 1), _verdict("fr1-result", "fr1-goal", "unknown", 2),
            _goal("fr5-goal", "fun x -> x >= 0", 6), _verdict("fr5-result", "fr5-goal", "proved", 7)])
    r = next(x for x in L.residual_surface(t) if x["residual_id"] == "r1")
    assert r["overtaken"] is not None


def test_retiring_is_still_not_closing():
    t = _t([_undecided("r1", "fr1-result", 3)],
           [_goal("fr1-goal", LAMBDA, 1), _verdict("fr1-result", "fr1-goal", "unknown", 2),
            _goal("fr5-goal", LAMBDA, 6), _verdict("fr5-result", "fr5-goal", "proved", 7)])
    r = next(x for x in L.residual_surface(t) if x["residual_id"] == "r1")
    assert r["status"] == "open"
    assert "not a reformulation or a bounded version" in r["overtaken"]["recheck"]

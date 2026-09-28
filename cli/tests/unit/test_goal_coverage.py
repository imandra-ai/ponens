"""Work recorded UNDER a goal, against work that is evidence FOR one of its criteria.

Two different relations were one edge until artifacts carried a `goal_id`. Membership is which goal the
work was done under - bookkeeping, total, stamped when the work happened. Evidence is whether an artifact
discharges a criterion - typed, lineage-rooted, and allowed to be absent. Because only the second
existed, a goal with no criteria absorbed nothing at all, and a read or a code change sat outside the
goal even in a session that had declared one.

The number these tests protect is `unrooted`, and the thing they protect it from is being turned into a
score. Unrooted work is NORMAL - reading the config is real work and evidences nothing - so this is a
report a reviewer reads, not a bar anybody has to clear. Scoring it would push an author towards criteria
the evidence trivially satisfies, which is the failure the whole evidence path is shaped to avoid.
"""
import copy

from ponens import goals as goalops


def artifact(aid, atype, goal_id=None, symbol=None, derived_from=None, status=None):
    payload = {}
    if symbol:
        payload["target_symbol"] = symbol
    if status:
        payload["status"] = status
    a = {"artifact_id": aid, "artifact_type": atype, "name": aid,
         "derived_from": derived_from or [], "payload": payload}
    if goal_id:
        a["goal_id"] = goal_id
    return a


def goal(gid, items):
    return {"id": gid, "intent": gid, "scope": [], "status": "active", "acceptance": items}


def criterion(cid, component, evidence):
    return {"id": cid, "kind": "property", "label": cid,
            "component": {"function": component}, "evidence": {"artifact": evidence}}


def test_work_under_a_goal_is_counted_apart_from_evidence_for_it():
    # A read and a code change are real work under the goal. Neither is the evidence the goal asked for,
    # and saying so is the whole point: this goal's definition of done covers one of the three things
    # that happened under it.
    t = {"goals": [goal("g", [criterion("a1", "settles", "VerificationResult")])],
         "artifacts": [
             artifact("src-1", "SourceCode", "g"),
             artifact("d-1", "Diff", "g", symbol="settles"),
             artifact("v-1", "VerificationResult", "g", symbol="settles", status="proved"),
         ]}
    cov = goalops.goal_coverage(t["goals"][0], t)
    assert cov["recorded"] == 3
    assert cov["rooted"] == 1
    assert cov["unrooted"] == 2
    assert cov["unrooted_by_type"] == {"SourceCode": 1, "Diff": 1}


def test_a_goal_with_no_criteria_still_holds_its_work():
    # THE case the old cone could not represent. The default goal deliberately carries no criteria, so
    # nothing can root in it - and before membership existed that made a whole session's work invisible
    # to the only goal there was.
    t = {"goals": [goal("session-goal", [])],
         "artifacts": [artifact("src-1", "SourceCode", "session-goal"),
                       artifact("d-1", "Diff", "session-goal")]}
    cov = goalops.goal_coverage(t["goals"][0], t)
    assert cov["recorded"] == 2
    assert cov["rooted"] == 0
    assert cov["criteria"] == 0


def test_two_goals_do_not_borrow_each_other_s_work():
    t = {"goals": [goal("g1", [criterion("a1", "settles", "VerificationResult")]),
                   goal("g2", [criterion("b1", "fee_tier", "VerificationResult")])],
         "artifacts": [
             artifact("v-1", "VerificationResult", "g1", symbol="settles", status="proved"),
             artifact("v-2", "VerificationResult", "g2", symbol="fee_tier", status="proved"),
         ]}
    assert goalops.goal_coverage(t["goals"][0], t)["recorded"] == 1
    assert goalops.goal_coverage(t["goals"][1], t)["recorded"] == 1


def test_an_unanswered_criterion_is_named_as_unknown_not_unmet():
    t = {"goals": [goal("g", [criterion("a1", "settles", "VerificationResult"),
                              criterion("a2", "net_exposure", "VerificationResult")])],
         "artifacts": [artifact("v-1", "VerificationResult", "g", symbol="settles", status="proved")]}
    enriched = goalops.enrich(copy.deepcopy(t))
    g = enriched["goals"][0]
    # Resolution ran: a1 is done off the proof, a2 has nothing pointing at it.
    assert g["acceptance"][0]["status"] == "done"
    assert g["acceptance"][1]["status"] == "todo"
    assert g["coverage"]["criteria_unevidenced"] == ["a2"]
    # And it is NOT reported as failed: `blocked` means evidence said no, `todo` means nobody asked.
    assert g["acceptance"][1]["status"] != "blocked"


def test_artifacts_belonging_to_no_goal_are_reported_as_a_hole():
    # Empty for anything a current build recorded - the store opens a default goal before it records, so
    # the stamp is total by construction. A non-empty list means an older record, or a producer that got
    # around `record()`; the second is a hole in the bookkeeping and worth seeing.
    t = {"goals": [goal("g", [])],
         "artifacts": [artifact("v-1", "VerificationResult", "g", symbol="s"),
                       artifact("v-2", "VerificationResult", None, symbol="s")]}
    assert goalops.unstamped_artifacts(t) == ["v-2"]
    assert "unstamped_artifacts" in goalops.enrich(copy.deepcopy(t))


def test_coverage_says_nothing_about_whether_the_goal_is_met():
    # The guard against the obvious mistake. Membership must never be read as evidence: a goal can hold a
    # pile of work and be entirely unmet, and can be met with most of its work rooting in nothing.
    t = {"goals": [goal("g", [criterion("a1", "settles", "VerificationResult")])],
         "artifacts": [artifact("src-1", "SourceCode", "g"),
                       artifact("src-2", "SourceCode", "g"),
                       artifact("d-1", "Diff", "g", symbol="settles")]}
    enriched = goalops.enrich(copy.deepcopy(t))
    g = enriched["goals"][0]
    assert g["coverage"]["recorded"] == 3
    assert g["faithfulness"]["met"] is False


def enriched_with(goals, artifacts):
    import copy
    return goalops.enrich(copy.deepcopy({"goals": goals, "artifacts": artifacts}))


def test_a_record_with_no_criteria_says_so_rather_than_nothing():
    """44 of 73 corpus records printed NOTHING in the requirements section.

    The section is omitted when there are no requirements, which made "nobody stated what done means"
    look exactly like a clean run. Those are completely different situations and a reader could not tell
    them apart. Saying it is true, invents nothing, and is actionable - asking for a definition is the
    one thing a reviewer can do about it.
    """
    from ponens import overview as ov
    o = ov.overview({"goals": [goal("session-goal", [])],
                     "artifacts": [artifact("v-1", "VerificationResult", "session-goal", symbol="s")]})
    text = ov.render_overview(o)
    assert "none stated" in text
    assert "what \"done\" means" in text


def test_evidence_that_answers_no_requirement_is_reported():
    """18 corpus records hold verdicts while the surface says "no evidence yet".

    Not merely unhelpful - the opposite of true. `config-driven` holds a refutation, the fix, and a proof
    of the fix, and reads as though nothing happened.
    """
    from ponens import overview as ov
    g = goal("g", [criterion("a1", "settles", "VerificationResult")])
    # A result about a DIFFERENT symbol: real evidence, answering none of what was asked.
    o = ov.overview({"goals": [g],
                     "artifacts": [artifact("v-1", "VerificationResult", "g", symbol="unrelated", status="proved")]})
    assert "none of them answers a requirement" in ov.render_overview(o)


def test_a_met_requirement_says_none_of_that():
    from ponens import overview as ov
    g = goal("g", [criterion("a1", "settles", "VerificationResult")])
    o = ov.overview({"goals": [g],
                     "artifacts": [artifact("v-1", "VerificationResult", "g", symbol="settles", status="proved")]})
    text = ov.render_overview(o)
    assert "none stated" not in text
    assert "none of them answers a requirement" not in text

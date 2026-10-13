"""Three-valued policy evaluation (POLICY_LANGUAGE §5.1): a fact a formula reads may be unknown - an edit no symbol
could be attributed to, evidence whose currency was not judged. Strong Kleene logic decides what it can, and a policy
whose answer turns on an unknown fact is `undetermined`, with the actions where - never passed, never failed."""

from ponens.trace import evaluate_policy_full, undetermined_actions, k_and, k_or, k_not, k_all, k_any


def record(actions, artifacts=(), goals=()):
    return {"actions": actions, "artifacts": list(artifacts), "goals": list(goals)}


def edit(i, file, symbol=None, attributed=True):
    a = {"id": i, "type": "EditFile", "target": file, "outputs": [f"d{i}"]}
    if not attributed:
        a["attributed"] = False
    return a, {"artifact_id": f"d{i}", "artifact_type": "Diff", "payload": {"file": file, **({"target_symbol": symbol} if symbol else {})}}


def run(i, **payload):
    return {"id": i, "type": "RunTests", "outputs": [f"r{i}"]}, {"artifact_id": f"r{i}", "artifact_type": "TestResult",
                                                                   "payload": {"evidence_strength": "tests", **payload}}


def check(formula, rec):
    return evaluate_policy_full({"name": "p", "formula": formula}, rec)[0]


def test_kleene_connectives():
    assert k_and(False, None) is False and k_and(True, None) is None and k_and(True, True) is True
    assert k_or(True, None) is True and k_or(False, None) is None and k_or(False, False) is False
    assert k_not(None) is None and k_not(True) is False
    assert k_all([True, None]) is None and k_all([None, False]) is False
    assert k_any([False, None]) is None and k_any([None, True]) is True


def test_current_is_read_from_the_stamp_and_unknown_without_one():
    f = "G(EditFile → F(RunTests ∧ current))"
    e, d = edit(1, "fees.py", "refund_fee")
    for stamp, want in ((True, "passed"), (False, "failed"), (None, "undetermined")):
        r, t = run(2, current=stamp)
        assert check(f, record([e, r], [d, t])) == want, stamp
    r, t = run(2)  # not stamped at all
    assert check(f, record([e, r], [d, t])) == "undetermined"


def test_a_known_answer_wins_over_an_unknown_one():
    e, d = edit(1, "fees.py", "refund_fee")
    r1, t1 = run(2, current=None)
    r2, t2 = run(3, current=True)
    assert check("G(EditFile → F(RunTests ∧ current))", record([e, r1, r2], [d, t1, t2])) == "passed", "one current run is enough"
    # A failure elsewhere decides it, whatever is unknown.
    e2, d2 = edit(4, "clamp.py", "clamp")
    assert check("G(EditFile → F(RunTests ∧ current))", record([e, r1, e2], [d, t1, d2])) == "failed"


def test_an_unattributed_edit_is_undetermined_where_a_policy_asks_which_symbol():
    named, d1 = edit(1, "fees.py", "refund_fee")
    loose, d2 = edit(2, "fees.py", attributed=False)
    goals = [{"intent": "Refunds", "acceptance": [{"component": {"function": "refund_fee"}}]}]
    rec = record([named, loose], [d1, d2], goals)
    assert check("G(EditFile → named_by_goal)", rec) == "undetermined"
    assert undetermined_actions({"name": "p", "formula": "G(EditFile → named_by_goal)"}, rec) == [2]
    # A file criterion names every edit in its file - attributed or not.
    file_goal = [{"intent": "Refunds", "acceptance": [{"component": {"file": "fees.py"}}]}]
    assert check("G(EditFile → named_by_goal)", record([named, loose], [d1, d2], file_goal)) == "passed"
    # A policy that does not ask which symbol - the file is known - is decided as before.
    assert check("G(EditFile → ¬labeled(generated))", {**rec, "path_labels": {"generated": ["gen/"]}}) == "passed"


def test_ci_confirmed_is_two_valued():
    e, d = edit(1, "fees.py", "refund_fee")
    r, t = run(2, ci="confirmed")
    assert check("G(EditFile → F(RunTests ∧ ci_confirmed))", record([e, r], [d, t])) == "passed"
    r, t = run(2, ci="contradicted")
    assert check("G(EditFile → F(RunTests ∧ ci_confirmed))", record([e, r], [d, t])) == "failed"
    r, t = run(2)
    assert check("G(EditFile → F(RunTests ∧ ci_confirmed))", record([e, r], [d, t])) == "failed", "not run by CI: not confirmed"


def test_a_record_with_no_unknown_facts_is_judged_as_before():
    e, d = edit(1, "fees.py", "refund_fee")
    r, t = run(2)
    assert check("G(EditFile → F(RunTests))", record([e, r], [d, t])) == "passed"
    assert check("G(EditFile → P(RunTests))", record([e, r], [d, t])) == "failed"


# --- About the code an edit changed (POLICY_LANGUAGE §2.6): by the goal contract's own resolution ---------------

def contract(proof_status="proved", current=True, ci=None, attributed=True, edited="settle"):
    vr = {"status": proof_status, "goal_id": "g1", "goal_artifact_id": "vg1"}
    if current is not None or current is None:
        vr["current"] = current
    if ci:
        vr["ci"] = ci
    edit_action = {"id": 10, "type": "EditFile", "outputs": ["d10"]}
    if not attributed:
        edit_action["attributed"] = False
    return {
        "actions": [{"id": i} for i in range(1, 10)] + [edit_action],
        "artifacts": [
            {"artifact_id": "src", "artifact_type": "SourceCode", "derived_from": None, "producer_action_id": 1},
            {"artifact_id": "model", "artifact_type": "IMLModel", "derived_from": ["src"], "producer_action_id": 2, "payload": {"symbols": ["settle"]}},
            {"artifact_id": "vg1", "artifact_type": "VerificationGoal", "derived_from": ["model"], "producer_action_id": 3,
             "payload": {"goal_id": "g1", "target_symbol": "settle", "property_name": "money_conserved"}},
            {"artifact_id": "vr1", "artifact_type": "VerificationResult", "derived_from": ["vg1"], "producer_action_id": 4, "payload": vr},
            {"artifact_id": "d10", "artifact_type": "Diff", "producer_action_id": 10,
             "payload": {"file": "payments/settle.py", **({"target_symbol": edited} if attributed else {})}},
        ],
        "goals": [{"id": "g", "intent": "Settle", "status": "active", "scope": [],
                   "acceptance": [{"id": "c1", "component": {"function": "settle"}, "evidence": {"artifact": "VerificationResult"}}]}],
    }


def test_established_reads_the_criteria_that_name_the_edited_symbol():
    assert check("G(EditFile → named_by_goal ∧ established)", contract()) == "passed"
    assert check("G(EditFile → established_as(proved))", contract()) == "passed"
    assert check("G(EditFile → established_as(proved) ∨ established_as(bounded))", contract(proof_status="bounded")) == "passed"
    assert check("G(EditFile → established_as(proved))", contract(proof_status="bounded")) == "failed"
    assert check("G(EditFile → established)", contract(edited="other")) == "failed", "a symbol no criterion names"


def test_evidence_current_and_ci_read_the_evidence_that_meets_them():
    f = "G(EditFile ∧ established → evidence_current)"
    assert check(f, contract(current=True)) == "passed"
    assert check(f, contract(current=False)) == "failed"
    assert check(f, contract(current=None)) == "undetermined"
    assert check("G(EditFile ∧ established → evidence_ci_confirmed)", contract(ci="confirmed")) == "passed"
    assert check("G(EditFile ∧ established → evidence_ci_confirmed)", contract()) == "failed"


def test_an_unattributed_edit_leaves_what_it_changed_unknown():
    assert check("G(EditFile → established)", contract(attributed=False)) == "undetermined"


def test_a_failing_policy_still_says_where_it_is_undetermined():
    from ponens.trace import undetermined_actions
    named, d1 = edit(1, "fees.py", "refund_fee")
    loose, d2 = edit(2, "fees.py", attributed=False)
    other, d3 = edit(3, "fees.py", "charge_fee")
    goals = [{"intent": "Refunds", "acceptance": [{"component": {"function": "refund_fee"}}]}]
    rec = record([named, loose, other], [d1, d2, d3], goals)
    pol = {"name": "p", "formula": "G(EditFile → named_by_goal)"}
    assert check(pol["formula"], rec) == "failed"
    assert undetermined_actions(pol, rec) == [2]


def test_a_proof_of_the_model_only_is_not_a_proof_of_the_changed_code():
    rec = contract()
    next(a for a in rec["artifacts"] if a["artifact_id"] == "vr1")["payload"]["of_code"] = False
    assert check("G(EditFile → established_as(proved))", rec) == "failed"
    assert check("G(EditFile → established)", rec) == "passed", "the criterion is still met - by a proof of the model"

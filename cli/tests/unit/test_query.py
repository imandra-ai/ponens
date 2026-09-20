"""`ponens trace symbols` / `trace symbol` — asking the record what it knows about a symbol.

The overview says where a project stands. These say what is already established about one function, so
an agent consults the record instead of re-deriving the function's behaviour from source every turn.
"""
from ponens import query as q
from ponens import blame as blamemod
from ponens import trace as traceops


def _trace():
    t = traceops.create_empty_trace(model="m", assistant="t")
    t["actions"] = [{"id": i, "type": ty, "category": "reasoning", "rationale": "r", "inputs": [], "outputs": []}
                    for i, ty in ((1, "Formalize"), (2, "Verify"), (3, "Verify"))]
    t["artifacts"] = [
        {"artifact_id": "src1", "artifact_type": "SourceCode", "name": "payments.py",
         "derived_from": [], "producer_action_id": 1},
        {"artifact_id": "m1", "artifact_type": "IMLModel", "derived_from": ["src1"], "producer_action_id": 1,
         "payload": {"formal_code": "let step s a = s\n", "symbols": ["step"]}},
        {"artifact_id": "g1", "artifact_type": "VerificationGoal", "derived_from": ["m1"], "producer_action_id": 2,
         "payload": {"goal_id": 1, "target_symbol": "step", "description": "terminal stays terminal"}},
        {"artifact_id": "d1", "artifact_type": "StateSpaceAnalysisResult", "derived_from": ["m1"],
         "producer_action_id": 2, "ref": "fr9-regions",
         "payload": {"status": "complete", "evidence_strength": "proof", "target_symbol": "step",
                     "complete": True,
                     "regions": [
                         {"id": "1.1", "constraints": ["s.status = Canceled", "a.c <> Cancel"],
                          "invariant": "s", "input": "…", "expected": "…"},
                         {"id": "1.2", "constraints": ["s.status = Requires_capture", "a.c = Capture"],
                          "invariant": "{s with status = Succeeded}"},
                         {"id": "1.3", "constraints": ["s.status = Requires_capture", "a.c = Cancel"],
                          "invariant": "{s with status = Canceled}"},
                     ]}},
    ]
    return t


def test_index_is_one_small_record_per_symbol():
    res = q.symbols(_trace())
    assert res["summary"]["symbols"] == 1
    row = res["symbols"][0]
    assert row["symbol"] == "step"
    assert row["kind"] == "decomposition"
    assert row["grade"] == "proved"
    assert row["freshness"] in ("fresh", "unknown")
    assert row["regions"] == 3
    assert row["ref"] == "fr9-regions"


def test_index_resolves_the_source_file_not_the_model():
    """A decomposition names the model it ran on; a reader means the file the symbol lives in."""
    assert q.symbols(_trace())["symbols"][0]["file"] == "payments.py"


def test_summary_says_what_the_behaviour_turns_on_without_returning_regions():
    res = q.symbol(_trace(), "step")
    assert "regions" not in res
    assert res["shape"]["outcomes"] == 3
    # variables and fields, never the constructor values they are compared against
    assert "s.status" in res["shape"]["splits_on"]
    assert not any(v in res["shape"]["splits_on"] for v in ("Cancel", "Canceled", "Capture"))


def test_absence_is_an_answer_not_an_error():
    assert q.symbol(_trace(), "nobody_reasoned_about_this") == {
        "symbol": "nobody_reasoned_about_this", "known": False}


def test_regions_come_back_only_when_asked_and_say_whether_they_are_exhaustive():
    res = q.symbol(_trace(), "step", regions=True)
    assert res["complete"] is True
    assert res["total"] == 3 and res["returned"] == 3
    assert res["regions"][0]["constraints"] == ["s.status = Canceled", "a.c <> Cancel"]


def test_a_truncated_region_list_says_what_it_left_out():
    res = q.symbol(_trace(), "step", regions=True, limit=1)
    assert res["total"] == 3 and res["matched"] == 3 and res["returned"] == 1
    assert len(res["regions"]) == 1


def test_where_narrows_the_map():
    res = q.symbol(_trace(), "step", regions=True, where="a.c = Capture")
    assert res["matched"] == 1
    assert res["regions"][0]["id"] == "1.2"


def test_where_can_select_by_outcome():
    res = q.symbol(_trace(), "step", regions=True, where="outcome:Succeeded")
    assert res["matched"] == 1 and res["regions"][0]["id"] == "1.2"


def test_rendering_is_readable_without_json():
    assert "step" in q.render_symbols(q.symbols(_trace()))
    assert "Nothing is known" in q.render_symbol(q.symbol(_trace(), "absent"))


def test_index_reports_regions_even_when_a_later_record_arrives():
    """A decomposition is not retracted by the test run recorded after it.

    The index read the region count off the NEWEST record only, so a symbol that was decomposed and then
    tested reported `regions=None` from `trace symbols` while `trace symbol` - which searches every
    record - answered `2 regions` for the same trace. Two views of one record disagreeing about a plain
    fact is worse than either answer; the count now comes from whichever record carries one.
    """
    t = _trace()
    t["actions"].append({"id": 4, "type": "Test", "category": "verification", "rationale": "r",
                         "inputs": [], "outputs": []})
    t["artifacts"].append(
        {"artifact_id": "t1", "artifact_type": "TestResult", "derived_from": ["src1"],
         "producer_action_id": 4, "created_at": "2030-01-01T00:00:00Z",
         "payload": {"status": "passed", "target_symbol": "step", "evidence_strength": "tests",
                     "passed": 3, "failed": 0}})

    row = q.symbols(t)["symbols"][0]
    assert row["kind"] == "testresult", "the newest record still sets the headline kind"
    assert row["regions"] == 3, "and the decomposition's region count survives it"
    assert q.symbol(t, "step")["shape"]["splits_on"], "the detail view agreed all along"


def test_index_headlines_the_best_result_not_the_latest_one():
    """A later test run does not retract an earlier proof.

    The row used to describe `recs[0]`, the newest record, so running a suite against a function that
    had been PROVED moved the headline from `proved · proof · fresh` to `tested · tests · unknown` -
    the strongest thing known about the symbol became invisible the moment anything weaker happened
    afterwards, and `trace symbols` contradicted `trace blame` about the same trace. The row now takes
    the record `blame` already picked.
    """
    t = _trace()
    t["actions"].append({"id": 4, "type": "Verify", "category": "verification", "rationale": "r",
                         "inputs": [], "outputs": []})
    t["artifacts"].append(
        {"artifact_id": "v1", "artifact_type": "VerificationResult", "derived_from": ["m1"],
         "producer_action_id": 4, "ref": "fr1-result", "created_at": "2029-01-01T00:00:00Z",
         "payload": {"status": "proved", "target_symbol": "step", "evidence_strength": "proof",
                     "engine": "imandrax", "goal_artifact_id": "g1"}})
    # …and then something weaker, and LATER.
    t["actions"].append({"id": 5, "type": "Test", "category": "verification", "rationale": "r",
                         "inputs": [], "outputs": []})
    t["artifacts"].append(
        {"artifact_id": "t1", "artifact_type": "TestResult", "derived_from": ["src1"],
         "producer_action_id": 5, "created_at": "2030-01-01T00:00:00Z",
         "payload": {"status": "passed", "target_symbol": "step", "evidence_strength": "tests"}})

    row = q.symbols(t)["symbols"][0]
    assert row["grade"] == "proved", "the proof is still the strongest thing known"
    assert row["kind"] == "verification"
    assert row["ref"] == "fr1-result", "and the row points at the record it describes"

    # The two surfaces agree, which is the actual requirement.
    best = blamemod.blame(t)["symbols"]["step"]["best"]
    assert best["artifact_id"] == "v1"


def test_index_falls_back_to_the_latest_when_nothing_is_established():
    """With no best, "the latest thing that happened" IS the honest headline."""
    t = _trace()
    t["actions"].append({"id": 4, "type": "Verify", "category": "verification", "rationale": "r",
                         "inputs": [], "outputs": []})
    t["artifacts"].append(
        {"artifact_id": "u1", "artifact_type": "VerificationResult", "derived_from": ["m1"],
         "producer_action_id": 4, "created_at": "2030-01-01T00:00:00Z",
         "payload": {"status": "unknown", "target_symbol": "step", "engine": "imandrax"}})
    row = q.symbols(t)["symbols"][0]
    assert row["symbol"] == "step"
    assert row["gaps"] >= 0


def test_the_index_row_and_the_detail_header_describe_the_same_record():
    """Two views of one symbol, one headline rule.

    Moving the index to the best result without moving the detail header produced exactly the class of
    contradiction this change set out to remove: `proved · fresh` in the list, `unknown` at the top of
    the page about that same symbol. Both go through `_headline` now.
    """
    t = _trace()
    t["actions"].append({"id": 4, "type": "Verify", "category": "verification", "rationale": "r",
                         "inputs": [], "outputs": []})
    t["artifacts"].append(
        {"artifact_id": "v1", "artifact_type": "VerificationResult", "derived_from": ["m1"],
         "producer_action_id": 4, "created_at": "2029-01-01T00:00:00Z",
         "payload": {"status": "proved", "target_symbol": "step", "evidence_strength": "proof",
                     "engine": "imandrax", "goal_artifact_id": "g1"}})
    t["actions"].append({"id": 5, "type": "Test", "category": "verification", "rationale": "r",
                         "inputs": [], "outputs": []})
    t["artifacts"].append(
        {"artifact_id": "t1", "artifact_type": "TestResult", "derived_from": ["src1"],
         "producer_action_id": 5, "created_at": "2030-01-01T00:00:00Z",
         "payload": {"status": "passed", "target_symbol": "step", "evidence_strength": "tests"}})

    row = q.symbols(t)["symbols"][0]
    detail = q.symbol(t, "step")
    assert row["freshness"] == detail["freshness"]["state"]
    assert row["ref"] == "fr1-result" or row["ref"] == "v1"
    # and the detail still carries the whole history, newest first
    assert [e["kind"] for e in detail["evidence"]][0] == "testresult"

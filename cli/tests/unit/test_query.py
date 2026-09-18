"""`ponens trace symbols` / `trace symbol` — asking the record what it knows about a symbol.

The overview says where a project stands. These say what is already established about one function, so
an agent consults the record instead of re-deriving the function's behaviour from source every turn.
"""
from ponens import query as q
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

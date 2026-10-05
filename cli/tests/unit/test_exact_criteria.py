"""Exact criteria: a statement the evidence must BE, words the evidence must say - and a person's link.

A substring lets a weaker claim answer a stronger criterion: "never negative" is part of "never negative
unless refunded", and "P" is part of "P -> Q". A producer that can say exactly what it wants asks for it;
overlapping wording becomes a candidate a person decides on, never met on its own.
"""

from ponens.goals import resolve_item
from ponens.overview import _goal_requirements


def _trace(*results):
    arts = [{"artifact_id": "src", "artifact_type": "SourceCode", "derived_from": None, "producer_action_id": 1,
             "payload": {"target_symbol": "fee"}}]
    for i, (prop, status, extra) in enumerate(results, start=1):
        arts.append({"artifact_id": f"vg{i}", "artifact_type": "VerificationGoal", "derived_from": ["src"], "producer_action_id": 2 * i,
                     "payload": {"target_symbol": "fee", "description": prop}})
        arts.append({"artifact_id": f"vr{i}", "artifact_type": "VerificationResult", "derived_from": [f"vg{i}"], "producer_action_id": 2 * i + 1,
                     "payload": {"target_symbol": "fee", "goal_artifact_id": f"vg{i}", "status": status, **extra}})
    return {"actions": [{"id": i} for i in range(1, 30)], "artifacts": arts}


def _item(**kw):
    return {"id": "c1", "kind": "property", "required": True, "component": {"function": "fee"},
            "evidence": {"artifact": "VerificationResult"}, **kw}


def test_by_default_a_criterion_is_matched_by_substring_as_before():
    t = _trace(("the fee is never negative unless refunded", "proved", {}))
    assert resolve_item(_item(property="never negative"), t)["status"] == "done"


def test_exact_words_are_not_met_by_a_weaker_claim_that_contains_them_but_name_it_a_candidate():
    t = _trace(("the fee is never negative unless refunded", "proved", {}))
    r = resolve_item(_item(property="the fee is never negative", property_match="exact"), t)
    assert r["status"] == "todo"
    assert r["candidates"] == [{"artifact_id": "vr1", "property": "the fee is never negative unless refunded"}]


def test_exact_words_are_met_by_the_same_words_case_and_spacing_aside():
    t = _trace(("The fee is  never negative", "proved", {}))
    r = resolve_item(_item(property="the fee is never negative", property_match="exact"), t)
    assert r["status"] == "done" and r["evidence"] == "vr1"
    assert "candidates" not in r


def test_a_person_links_evidence_worded_otherwise_and_it_answers_the_criterion_by_its_own_verdict():
    t = _trace(("fee >= 0 for every amount", "proved", {}), ("fee <= 3", "refuted", {}))
    assert resolve_item(_item(property="the fee is never negative", property_match="exact", linked_evidence=["vr1"]), t)["status"] == "done"
    # A link does not make a refutation a proof, nor reach evidence about another component.
    assert resolve_item(_item(property="the fee is at most 3", property_match="exact", linked_evidence=["vr2"]), t)["status"] == "blocked"
    other = _item(property="the fee is never negative", property_match="exact", linked_evidence=["vr1"], component={"function": "refund"})
    assert resolve_item(other, t)["status"] != "done"


def test_an_exact_statement_is_met_only_by_evidence_that_reports_that_very_statement():
    stmt = "∀ (x : Int), cap x ≤ 100"
    t = _trace(("cap is clamped", "proved", {"statement": "∀ (x : Int), 0 ≤ x → cap x ≤ 100"}),
               ("cap never exceeds 100", "proved", {}))
    # Neither a different statement, nor the same words without the statement, meets it.
    assert resolve_item(_item(property="cap never exceeds 100", statement=stmt), t)["status"] == "todo"
    t = _trace(("cap is clamped", "proved", {"statement": "∀ (x : Int),   cap x ≤ 100"}))
    assert resolve_item(_item(property="cap never exceeds 100", statement=stmt), t)["status"] == "done"
    # Case kept: Lean is case-sensitive.
    assert resolve_item(_item(statement="∀ (x : Int), Cap x ≤ 100"), t)["status"] == "todo"


def test_the_overview_says_a_person_decides_and_lists_the_candidates():
    t = _trace(("the fee is never negative unless refunded", "proved", {}))
    item = _item(property="the fee is never negative", property_match="exact")
    r = resolve_item(item, t)
    enriched = {"goals": [{"id": "g1", "acceptance": [{**item, "status": r["status"], "candidates": r["candidates"]}]}]}
    [req] = _goal_requirements(enriched)
    assert req["state"] == "open"
    assert req["reason"] == "no evidence yet - 1 result worded otherwise; a person decides whether it meets it"
    assert req["candidates"][0]["artifact_id"] == "vr1"


def test_exact_words_said_of_the_criterions_own_subject_are_the_same_words():
    # "fee is never negative" says "never negative" of fee - the subject named, not a weaker claim.
    for said in ("fee is never negative", "fee never negative", "FEE is  never negative"):
        t = _trace((said, "proved", {}))
        assert resolve_item(_item(property="never negative", property_match="exact"), t)["status"] == "done", said
    t = _trace(("fee stays within the ceiling", "proved", {}))
    assert resolve_item(_item(property="within the ceiling", property_match="exact"), t)["status"] == "done"


def test_a_qualifier_is_never_stripped_and_another_subject_is_not_this_one():
    for said in ("fee is never negative unless refunded", "for positive amounts, fee is never negative",
                 "refund is never negative"):
        t = _trace((said, "proved", {}))
        r = resolve_item(_item(property="never negative", property_match="exact"), t)
        assert r["status"] == "todo", said

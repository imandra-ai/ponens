"""RECORD_OVERVIEW reason codes (ponens 1.21): every requirement and row carries `reason_code` beside its `reason` -
the reason for a person, the code for a program (a consumer must never match the reason's words). Closed set, null
exactly when met."""
import os
import re

from ponens import overview as O

from tests.unit.test_overview import _conf, _req, _reqs, _sym_goal, _sym_reqs, _trace


def _row(t, reqs, cwd=None):
    return _req(t, reqs, cwd=cwd)["symbols"][0]


def test_each_row_rule_says_its_code(tmp_path):
    (tmp_path / "pay.py").write_text("def other(): pass\n")
    assert _row(_trace(goals=[_sym_goal()]), _sym_reqs(), cwd=str(tmp_path))["reason_code"] == "symbol_not_found"
    assert _row(_trace(goals=[]), _sym_reqs())["reason_code"] == "not_declared"
    assert _row(_trace(arts=[], goals=[_sym_goal()]), _sym_reqs())["reason_code"] == "no_evidence"
    assert _row(_trace(arts=[_conf("c1", 1, status="failed")], goals=[_sym_goal()]), _sym_reqs())["reason_code"] == "failed"
    assert _row(_trace(checksum="c2", goals=[_sym_goal()]), _sym_reqs())["reason_code"] == "out_of_date"
    assert _row(_trace(goals=[_sym_goal()]), _sym_reqs(strength="proof"))["reason_code"] == "weaker_than_required"
    (tmp_path / "pay.py").write_text("def can_refund(pi, amount):\n    return True\n")
    met = _req(_trace(goals=[_sym_goal()]), _sym_reqs(), cwd=str(tmp_path))
    assert met["symbols"][0]["reason_code"] is None and met["state"] == "met" and met["reason_code"] is None


def test_freshness_that_cannot_be_told_has_its_own_code():
    assert O._row_state(True, True, {"status": "passed", "freshness": "unknown", "grade": "tested"}, "tested") == \
        ("out_of_date", "freshness unknown", "freshness_unknown")


def test_a_requirement_takes_its_worst_rows_code_unless_the_model_or_its_reading_says_otherwise():
    r = _req(_trace(arts=[_conf("c1", 1, status="failed")], goals=[_sym_goal()]), _sym_reqs())
    assert (r["state"], r["reason_code"]) == ("failed", "failed")
    revised = _req(_trace(ref_version="2025-01-01"), _reqs())
    assert (revised["state"], revised["reason_code"]) == ("out_of_date", "model_revised")
    unread = _req(_trace(findings=["F-1: 'promptly' is not defined"]), _reqs())
    assert (unread["state"], unread["reason_code"]) == ("open", "reading_not_chosen")


def test_goal_items_say_their_code_too():
    enriched = {"goals": [{"id": "g1", "acceptance": [
        {"id": "met", "label": "a", "status": "done", "evidence_ref": "v1", "evidence_strength": "proof"},
        {"id": "edit", "label": "b", "status": "done", "evidence_ref": "d1"},                    # a Diff: no strength
        {"id": "stale", "label": "c", "status": "done", "evidence_ref": "v2", "evidence_strength": "proof", "freshness": "stale"},
        {"id": "contested", "label": "d", "status": "blocked"},
        {"id": "doing", "label": "e", "status": "doing"},
        {"id": "todo", "label": "f", "status": "todo"},
        {"id": "worded", "label": "g", "status": "todo", "candidates": [{"artifact_id": "v3", "property": "g, for positive inputs"}]},
    ]}]}
    codes = {r["item"]: r["reason_code"] for r in O._goal_requirements(enriched)}
    assert codes == {"met": None, "edit": "unranked", "stale": "out_of_date", "contested": "contested", "doing": "in_progress",
                     "todo": "no_evidence", "worded": "worded_otherwise"}


def test_every_code_is_in_the_closed_set_null_exactly_when_met_and_in_the_overview_json():
    t = _trace(arts=[], goals=[_sym_goal()])
    t["goals"].append({"id": "session-goal", "intent": "x", "scope": [], "status": "active", "acceptance": [
        {"id": "s1", "kind": "obligation", "label": "observed", "required": True, "component": {"function": "f"}, "evidence": {"artifact": "Observation"}}]})
    o = O.overview(t, _sym_reqs())
    rows = [*o["requirements"], *(s for r in o["requirements"] for s in r["symbols"])]
    assert rows and all("reason_code" in r for r in rows)
    for r in rows:
        assert (r["reason_code"] is None) == (r["state"] == "met")
        assert r["reason_code"] is None or r["reason_code"] in O.REASON_CODES


def test_the_spec_lists_exactly_the_codes_ponens_produces():
    spec = os.path.join(os.path.dirname(__file__), "..", "..", "..", "spec", "RECORD_OVERVIEW_v0_1.md")
    with open(spec) as f:
        text = f.read()
    table = text[text.index("### Reason codes"):text.index("### Requirements file schema")]
    assert set(re.findall(r"^\| `([a-z_]+)` \|", table, re.M)) == set(O.REASON_CODES)

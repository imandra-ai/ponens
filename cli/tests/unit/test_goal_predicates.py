"""Goals and provenance as policies over the trace, and applicability (vacuous passes said as such).

- `criteria`: every acceptance criterion of every goal, flattened, as a collection a quantifier ranges over
- `goal_declared`, `named_by_goal`: an edit is for a declared goal, and changes only what a criterion names
- `signature_change`, `search_confirmed`: facts stamped by whoever computed them (the hub, from the code)
- `policy_applicability`: False when a policy passed only because what it governs never happened
"""

import argparse
import io
import json
import os
import tempfile
from contextlib import redirect_stdout

from ponens.trace import evaluate_policy, policy_applicability, normalize_trace, cmd_check


def record(goals=(), actions=(), artifacts=(), **extra):
    t = {"trace_id": "t", "spec_version": "1.14", "trigger": {"type": "TaskReceived", "description": "x"},
         "goals": list(goals), "actions": list(actions), "artifacts": list(artifacts), "residuals": [],
         "outcome": {"type": "ProcessCompleted"}, **extra}
    normalize_trace(t)
    return t


def goal(*symbols, intent="Refunds never exceed the charge", author="human"):
    return {"id": "g1", "intent": intent, "intent_author": author, "status": "active", "scope": [],
            "acceptance": [{"id": f"c{i}", "label": f"{s} ok", "component": {"function": s}, "required": True}
                           for i, s in enumerate(symbols, 1)]}


def edit(aid, symbol, rationale="why", **payload):
    return ({"id": aid, "type": "EditFile", "category": "activity", "label": "edit", "rationale": rationale,
             "inputs": [], "outputs": [f"d{aid}"], "result_summary": "completed"},
            {"artifact_id": f"d{aid}", "artifact_type": "Diff", "name": "fees.py", "producer_action_id": aid,
             "derived_from": [], "payload": {"file": "fees.py", "target_symbol": symbol, **payload}})


def pol(formula, name="p"):
    return {"policy_id": name, "name": name, "formula": formula, "severity": "error", "scope": "trace", "kind": "temporal"}


def status(p, t):
    return evaluate_policy(p, t)[0]


def test_edits_named_by_goal():
    a, d = edit(1, "refund_fee")
    p = pol("G(EditFile → named_by_goal)")
    assert status(p, record([goal("refund_fee")], [a], [d])) == "passed"
    assert status(p, record([goal("charge_fee")], [a], [d])) == "failed"
    assert status(p, record([], [a], [d])) == "failed"


def test_goal_declared():
    a, d = edit(1, "refund_fee")
    p = pol("G(EditFile → goal_declared)")
    assert status(p, record([goal("refund_fee")], [a], [d])) == "passed"
    assert status(p, record([goal("refund_fee", intent="  ")], [a], [d])) == "failed"


def test_criteria_collection_and_intent_author():
    t = record([goal("refund_fee", "")])
    assert status(pol("∀ c ∈ criteria . c.symbol ≠ ∅"), t) == "failed"
    assert status(pol("∀ c ∈ criteria . c.symbol ≠ ∅"), record([goal("refund_fee")])) == "passed"
    assert status(pol("∀ g ∈ goals . g.intent_author = human"), record([goal("x", author="agent")])) == "failed"


def test_signature_change_needs_a_confirmed_search_before_it():
    p = pol("G(EditFile ∧ signature_change → P(search_confirmed))")
    a, d = edit(2, "charge_fee", signature_changed=True)
    search = {"id": 1, "type": "SearchCode", "category": "research", "label": "s", "rationale": "callers",
              "inputs": [], "outputs": ["s1"], "result_summary": "completed"}
    hits = lambda ok: {"artifact_id": "s1", "artifact_type": "SearchResults", "name": "s", "producer_action_id": 1,
                       "derived_from": [], "payload": {"query": "charge_fee(", "confirmed": ok}}
    assert status(p, record([goal("charge_fee")], [search, a], [hits(True), d])) == "passed"
    assert status(p, record([goal("charge_fee")], [search, a], [hits(False), d])) == "failed"
    assert status(p, record([goal("charge_fee")], [a], [d])) == "failed"


def test_applicability_separates_vacuous_passes():
    a, d = edit(1, "refund_fee")
    t = record([goal("refund_fee")], [a], [d])
    # Its trigger (a signature change) never happened: passed, but not applicable.
    sig = pol("G(EditFile ∧ signature_change → P(search_confirmed))")
    assert status(sig, t) == "passed" and policy_applicability(sig, t) is False
    # Its trigger happened and it held: applicable.
    named = pol("G(EditFile → named_by_goal)")
    assert status(named, t) == "passed" and policy_applicability(named, t) is True
    # A quantifier over an empty collection says nothing.
    assert policy_applicability(pol("∀ c ∈ criteria . c.symbol ≠ ∅"), record([])) is False


def test_check_json_reports_applicable():
    a, d = edit(1, "refund_fee")
    t = record([goal("refund_fee")], [a], [d],
               policies=[pol("G(EditFile ∧ signature_change → P(search_confirmed))", "sig"), pol("G(EditFile → named_by_goal)", "named")])
    for x in t["actions"]:
        x.pop("_original_outputs", None)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(t, f)
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_check(argparse.Namespace(trace_file=f.name, policy_file=None, json=True, write=False, strict=False))
        rows = {r["policy_id"]: r for r in json.loads(buf.getvalue())}
        assert rows["sig"]["applicable"] is False
        assert rows["named"]["applicable"] is True
    finally:
        os.unlink(f.name)


# ---- labeled(<name>): an organization's own vocabulary over paths --------------------------------

def test_labeled_matches_the_organizations_patterns():
    a, d = edit(1, "add_column")
    d["payload"]["file"] = "db/migrations/0042_fees.sql"
    p = pol("G(EditFile ∧ labeled(migrations) → P(RunTests))")
    labels = {"migrations": ["db/migrations/**"]}
    assert status(p, record([goal("add_column")], [a], [d], path_labels=labels)) == "failed"
    t = record([goal("add_column")], [a], [d], path_labels={"migrations": ["migrations/"]})  # a fragment, not a glob
    assert status(p, t) == "failed"
    # Not in the label: the rule does not apply - and says so.
    other = record([goal("add_column")], [a], [d], path_labels={"migrations": ["src/"]})
    assert status(p, other) == "passed"
    assert policy_applicability(p, other) is False


def test_an_undefined_label_holds_nowhere():
    a, d = edit(1, "add_column")
    p = pol("G(EditFile ∧ labeled(migrations) → P(RunTests))")
    assert status(p, record([goal("add_column")], [a], [d])) == "passed"


def test_labeled_lints_clean():
    from ponens.policy_compiler import check_policy
    _, errors, warnings = check_policy(pol("G(EditFile ∧ labeled(ledger-core) → P(Verify))"))
    assert not errors and not warnings


# ---- criteria about files and subjects (Goal Contract §4.1) ---------------------------------------

def file_goal(path):
    return {"id": "g1", "intent": "Migration 0042 is safe", "intent_author": "human", "status": "active", "scope": [],
            "acceptance": [{"id": "c1", "label": "tested", "component": {"file": path}, "required": True}]}


def test_an_edit_to_a_file_a_criterion_names_is_named():
    a, d = edit(1, None)
    d["payload"] = {"file": "db/migrations/0042.sql"}
    p = pol("G(EditFile → named_by_goal)")
    assert status(p, record([file_goal("db/migrations/0042.sql")], [a], [d])) == "passed"
    assert status(p, record([file_goal("db/migrations/*.sql")], [a], [d])) == "passed"
    assert status(p, record([file_goal("db/migrations/0041.sql")], [a], [d])) == "failed"


def test_criteria_say_what_they_are_about():
    p = pol("∀ c ∈ criteria . c.about ≠ ∅")
    assert status(p, record([file_goal("db/migrations/0042.sql")])) == "passed"
    subject = {**file_goal("x"), "acceptance": [{"id": "c1", "label": "conforms", "component": {"endpoint": "POST /v1/charge"}}]}
    assert status(p, record([subject])) == "passed"
    assert status(p, record([goal("refund_fee")])) == "passed"
    nothing = {**file_goal("x"), "acceptance": [{"id": "c1", "label": "vague"}]}
    assert status(p, record([nothing])) == "failed"

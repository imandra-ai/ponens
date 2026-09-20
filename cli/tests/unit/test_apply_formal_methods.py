"""Tests for the apply-formal-methods pack, the data-driven high-stakes surface, and the
machine-readable `ponens trace check --json / --write` output.

The pack policies are evaluated the same way the CodeLogician extension evaluates them live:
tokenize -> parse -> evaluate over a trace, via `evaluate_policy`. The CLI tests drive `cmd_check`
directly with an argparse Namespace (no server, no install) and assert the emitted
`policy_evaluation` records / in-place stamping.
"""

import argparse
import json
import os
import shutil

from ponens.trace import evaluate_policy, evaluate_policy_full, evaluate_formula, cmd_check
from ponens.policy_compiler import Atom

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures")
STRIPE = os.path.join(FIXTURES, "stripe-demo-trace.json")


# --------------------------------------------------------------------------- helpers

def action(aid, atype, evidence=None, category="activity"):
    return {"id": aid, "type": atype, "category": category, "rationale": "x",
            "result_summary": "", "evidence": evidence or [], "inputs": [], "outputs": []}


def fileref(path):
    return [{"type": "FileRef", "ref": path}]


def trace(actions, high_stakes_paths=None, artifacts=None):
    t = {"actions": actions, "artifacts": artifacts or [], "trigger": {}, "outcome": {}}
    if high_stakes_paths is not None:
        t["high_stakes_paths"] = high_stakes_paths
    return t


def policy(name, formula, severity="error"):
    return {"policy_id": name, "name": name, "formula": formula, "severity": severity}


def check_args(trace_file, **over):
    a = {"trace_file": trace_file, "policy_file": None, "strict": False, "json": False, "write": False}
    a.update(over)
    return argparse.Namespace(**a)


# --------------------------------------------------------------------------- data-driven high-stakes

def test_high_stakes_path_is_data_driven():
    """A path counts as high-stakes only when the trace's high_stakes_paths declares it."""
    a = action(1, "EditFile", evidence=fileref("billing/pricing.py"))
    atom = Atom("high_stakes_path")
    # Declared high-stakes -> matches.
    assert evaluate_formula(atom, trace([a], high_stakes_paths=["billing/"]), {"action": a}) is True
    # A different declared surface -> no match.
    assert evaluate_formula(atom, trace([a], high_stakes_paths=["payments/"]), {"action": a}) is False


def test_high_stakes_path_falls_back_to_defaults():
    """With no high_stakes_paths, the built-in demo defaults still apply (back-compat)."""
    a = action(1, "EditFile", evidence=fileref("payments/charge.py"))
    atom = Atom("high_stakes_path")
    assert evaluate_formula(atom, trace([a]), {"action": a}) is True          # 'payments/' default
    b = action(1, "EditFile", evidence=fileref("billing/pricing.py"))
    assert evaluate_formula(atom, trace([b]), {"action": b}) is False         # not a default


# --------------------------------------------------------------------------- pack policies discriminate

HIGH_STAKES_ANALYZED = policy(
    "reasoning_required_for_high_stakes",
    "G(EditFile ∧ high_stakes_path → P_chain(VerificationResult(proved ∨ sat) ∨ Decomposition))",
)
DECOMP_DRIVES_TESTS = policy("decomposition_drives_tests", "G(Decompose → F(GenerateTests))", "warning")


def test_high_stakes_edit_without_reasoning_fails():
    t = trace([action(1, "EditFile", evidence=fileref("billing/pricing.py"))],
              high_stakes_paths=["billing/"])
    status, _ = evaluate_policy(HIGH_STAKES_ANALYZED, t)
    assert status == "failed"


def test_edit_off_the_high_stakes_surface_passes_vacuously():
    # Same edit, but the file is not on the declared high-stakes surface -> antecedent false -> pass.
    t = trace([action(1, "EditFile", evidence=fileref("billing/pricing.py"))],
              high_stakes_paths=["payments/"])
    status, _ = evaluate_policy(HIGH_STAKES_ANALYZED, t)
    assert status == "passed"


def test_decomposition_without_tests_fails():
    status, _ = evaluate_policy(DECOMP_DRIVES_TESTS, trace([action(1, "Decompose")]))
    assert status == "failed"


def test_decomposition_followed_by_tests_passes():
    t = trace([action(1, "Decompose"), action(2, "GenerateTests")])
    status, _ = evaluate_policy(DECOMP_DRIVES_TESTS, t)
    assert status == "passed"


# --------------------------------------------------------------------------- evidence extraction

def test_evidence_names_the_witnessing_action_for_G_implies():
    pol = policy("retrieved_data_attributed", "G(Retrieve → provenance_checked ∧ recency_checked)")
    good = trace([{"id": 1, "type": "Retrieve", "rationale": "provenance checked, recency checked"},
                  {"id": 2, "type": "Release", "rationale": "send"}])
    bad = trace([{"id": 1, "type": "Retrieve", "rationale": "read from cache"},
                 {"id": 2, "type": "Release", "rationale": "send"}])
    status, _note, ev, vi, _ea, _va = evaluate_policy_full(pol, good)
    assert status == "passed" and ev == [1] and vi == []      # the Retrieve satisfied the predicate
    status, _note, ev, vi, _ea, _va = evaluate_policy_full(pol, bad)
    assert status == "failed" and vi == [1]                    # the Retrieve broke it


def test_evidence_names_the_dangling_action_for_structural():
    pol = {"name": "data_flow_integrity", "formula": "structural", "severity": "error"}
    bad = trace([{"id": 1, "type": "Retrieve", "rationale": "load", "outputs": ["a"]},
                 {"id": 2, "type": "Compute", "rationale": "reuse foreign ctx",
                  "inputs": ["foreign"], "outputs": ["b"]}])
    status, _note, _ev, vi, _ea, _va = evaluate_policy_full(pol, bad)
    assert status == "failed" and 2 in vi                       # action 2 has the dangling input


# --------------------------------------------------------------------------- machine-readable check

def test_cmd_check_json_emits_policy_evaluations(capsys):
    rc = cmd_check(check_args(STRIPE, json=True))
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert isinstance(out, list) and out, "expected a non-empty policy_evaluations array"
    for ev in out:
        assert set(("policy_id", "status")) <= set(ev)
        assert ev["status"] in ("passed", "failed", "unknown", "not_applicable")


def test_cmd_check_write_stamps_trace_in_place(tmp_path):
    dst = tmp_path / "t.json"
    shutil.copy(STRIPE, dst)
    rc = cmd_check(check_args(str(dst), write=True))
    assert rc in (0, 1)  # 1 only if an error-severity policy fails; the stamping still happens
    stamped = json.loads(dst.read_text())["policy_evaluations"]
    assert stamped and all("policy_id" in e and "status" in e for e in stamped)


def test_cmd_check_json_with_no_policies_emits_empty_array(tmp_path, capsys):
    t = json.loads(open(STRIPE).read())
    t["policies"] = []
    p = tmp_path / "nopol.json"
    p.write_text(json.dumps(t))
    rc = cmd_check(check_args(str(p), json=True))
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == []


# --------------------------------------------------------------------------- the summary line

def test_check_summary_counts_partition_and_a_warning_is_not_a_failure(tmp_path, capsys):
    """`N passed, N failed, N warnings` has to add up to the rows printed above it.

    `failed` used to tally EVERY violation regardless of severity, so a run whose only violation was a
    warning printed one `WARN` row and then announced `1 failed, 1 warnings` - the same violation
    counted twice, under a heading contradicted by the exit code, which was 0. A reader chasing a
    reported failure finds no FAIL row to chase.
    """
    # A real trace, not the formula-level stub `trace()` builds: `cmd_check` validates before it checks.
    from ponens.trace import create_empty_trace
    t = create_empty_trace(model="m", assistant="t")
    t["actions"] = [action(1, "EditFile", evidence=fileref("billing/pricing.py"))]
    t["policies"] = [
        {**policy("always_true", "G(EditFile → EditFile)"), "scope": "trace", "kind": "invariant"},
        {**policy("warns_only", "G(EditFile → Verify)", severity="warning"),
         "scope": "trace", "kind": "invariant"},
    ]
    p = tmp_path / "t.json"
    p.write_text(json.dumps(t))

    rc = cmd_check(check_args(str(p)))
    out = capsys.readouterr().out

    assert "  WARN    warns_only" in out
    assert "FAIL" not in out, "no error-severity violation, so no FAIL row"
    assert "1 passed, 0 failed, 1 warnings" in out
    assert rc == 0, "a warning does not fail the gate"


def test_check_summary_never_double_counts_a_syntax_rejection(tmp_path, capsys):
    """A policy rejected for SYNTAX is one row, counted once.

    Syntax rejection appends to `errors` and returns early without touching `failed`, so a summary that
    derived its counts by arithmetic over `passed`/`failed`/`total` reported the same policy as both a
    failure and as not-evaluated - and printed `-2 advisory`, a count that cannot exist.
    """
    from ponens.trace import create_empty_trace
    t = create_empty_trace(model="m", assistant="t")
    t["actions"] = [action(1, "EditFile")]
    t["policies"] = [{"policy_id": "malformed", "name": "malformed",
                      "formula": "G(EditFile → EditFile)", "severity": "error"}]  # no scope/kind
    p = tmp_path / "t.json"
    p.write_text(json.dumps(t))

    cmd_check(check_args(str(p)))
    out = capsys.readouterr().out

    assert "  SYNTAX  malformed" in out
    assert "0 passed, 1 failed, 0 warnings" in out
    assert "advisory" not in out and "not evaluated" not in out, "one row, one count"

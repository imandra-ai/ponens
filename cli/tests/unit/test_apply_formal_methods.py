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

from ponens.trace import evaluate_policy, evaluate_formula, cmd_check
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

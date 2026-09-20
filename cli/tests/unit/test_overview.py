"""RECORD_OVERVIEW v0.1: `ponens trace requirements` / `overview` / `integrity` — where a record
stands, in five words, read over what enrich / next_steps / blame already derive."""
import copy
import json
import os
import subprocess
import sys

from ponens import overview as O
from ponens import trace as T

REF = "ref:gallery:stripe/refunds@2024-06-20"
ENTRY = "gallery:stripe/refunds"


def _conf(aid, step, status="passed", strength="tests", ref=REF, target="can_refund", entry_sym="refund_allowed",
          version="2024-06-20", checksum="c1"):
    return {"artifact_id": aid, "artifact_type": "ConformanceResult", "derived_from": [ref], "producer_action_id": step,
            "payload": {"reference_artifact_id": ref, "target_symbol": target, "entry_symbol": entry_sym, "status": status,
                        "evidence_strength": strength, "engine": "codelogician",
                        "oracle": {"id": "codelogician", "oracle_type": "tester", "evidence_strength": strength},
                        "reference_version": version, "reference_checksum": checksum,
                        **({"counterexample": "amount=5"} if status == "failed" else {})}}


def _trace(arts=None, ref_version="2024-06-20", checksum="c1", goals=None, residuals=None, findings=None):
    t = T.create_empty_trace(model="m", assistant="t")
    t["reference_artifacts"] = [{"reference_artifact_id": REF, "name": "Refunds and amounts", "artifact_type": "RefFormalModel",
                                 "version": ref_version, "payload": {"checksum": checksum, **({"findings": findings} if findings else {})}}]
    arts = arts if arts is not None else [_conf("c1", 1)]
    t["actions"] = [{"id": a["producer_action_id"], "type": "RunTests", "category": "activity", "rationale": "r", "inputs": [REF], "outputs": [a["artifact_id"]]} for a in arts]
    t["artifacts"] = arts
    t["goals"] = goals if goals is not None else [_goal()]
    t["residuals"] = residuals or []
    t["outcome"] = {"type": "ProcessCompleted"}
    return t


def _goal(items=("binding:stripe-refunds:project",), gid="binding:stripe-refunds", ref=REF):
    return {"id": gid, "intent": "conform", "scope": [], "status": "active",
            "acceptance": [{"id": i, "kind": "conformance", "label": i, "required": True, "evidence": {"artifact": "ConformanceResult"},
                            "reference": ref, "binding": {},
                            **({"component": {"symbol": i.split(":")[-1]}} if not i.endswith(":project") else {})} for i in items]}


def _reqs(strength="tests", version="2024-06-20", code=None, interpretation=None):
    b = {"id": "stripe-refunds", "entry": ENTRY, "conformance": {"kind": "refinement", "strength": strength}}
    if version:
        b["version"] = version
    if code:
        b["code"] = code
    if interpretation:
        b["interpretation"] = interpretation
    return {"bindings": [b]}


def _req(t, reqs, cwd=None):
    return O.requirements(t, reqs, cwd=cwd)["requirements"][0]


# ── vocabulary ───────────────────────────────────────────────────────────────────────────────────

def test_grades_gap_states_and_freshness_words():
    assert [O.grade_of(s) for s in ("proof", "sat", "tests", "static_analysis", "attested", None)] == \
        ["proved", "witnessed", "tested", "checked", "attested", "unranked"]
    assert O.grade_at_least("proved", "tested") and not O.grade_at_least("tested", "proved") and not O.grade_at_least("unranked", "attested")
    assert O.gap_state("assumption") == "assumed" and O.gap_state("limitation") == "assumed"
    assert O.gap_state("defeater") == "failed" and O.gap_state("open_question") == "missing"
    assert O.gap_state("stale_evidence") == "out_of_date" and O.gap_state("needs_rereasoning") == "out_of_date"
    assert O.freshness_word("gone") == "out_of_date" and O.freshness_word(None) == "unknown"


# ── requirements: project-level ───────────────────────────────────────────────────────────────────

def test_project_level_requirement_met_at_tests_grade():
    r = _req(_trace(), _reqs())
    assert r["state"] == "met" and r["reason"] is None
    assert r["label"] == "Refunds and amounts"
    assert r["model"] == {"entry": ENTRY, "name": "Refunds and amounts", "version": "2024-06-20", "current_version": "2024-06-20",
                          "status": "current", "reference": REF}
    assert r["required_grade"] == "tested"
    assert r["evidence"]["artifact_id"] == "c1" and r["evidence"]["grade"] == "tested" and r["evidence"]["freshness"] == "fresh"
    assert r["symbols"][0]["scope"] == "project" and r["symbols"][0]["declared"] is True
    s = O.requirements(_trace(), _reqs())["summary"]
    assert s == {"requirements": 1, "met": 1, "open": 0, "failed": 0, "out_of_date": 0, "gate": "pass", "blocked_by": []}


def test_project_level_latest_result_wins_and_a_pass_after_a_failure_is_met():
    t = _trace(arts=[_conf("c1", 1, status="failed"), _conf("c2", 2)])
    assert _req(t, _reqs())["state"] == "met"
    t = _trace(arts=[_conf("c1", 1), _conf("c2", 2, status="failed")])
    r = _req(t, _reqs())
    assert r["state"] == "failed" and r["reason"] == "amount=5"


# ── requirements: the seven row rules (symbol-level) ─────────────────────────────────────────────

def _sym_reqs(strength="tests"):
    return _reqs(strength=strength, code=[{"file": "pay.py", "symbols": ["can_refund"], "maps_to": ["refund_allowed"]}])


def _sym_goal():
    return _goal(items=("binding:stripe-refunds:can_refund",))


def test_rule_1_symbol_not_found_in_file(tmp_path):
    (tmp_path / "pay.py").write_text("def other(): pass\n")
    row = _req(_trace(goals=[_sym_goal()]), _sym_reqs(), cwd=str(tmp_path))["symbols"][0]
    assert row["bound"] is False and row["state"] == "open" and row["reason"] == "symbol not found in pay.py"


def test_rule_2_not_declared():
    row = _req(_trace(goals=[]), _sym_reqs())["symbols"][0]
    assert row["bound"] is None and row["declared"] is False and row["state"] == "open" and row["reason"] == "not yet in the record"


def test_rule_3_no_evidence():
    row = _req(_trace(arts=[], goals=[_sym_goal()]), _sym_reqs())["symbols"][0]
    assert row["state"] == "open" and row["reason"] == "no evidence yet" and row["evidence"] is None


def test_rule_4_failed_with_its_counterexample():
    row = _req(_trace(arts=[_conf("c1", 1, status="failed")], goals=[_sym_goal()]), _sym_reqs())["symbols"][0]
    assert row["state"] == "failed" and row["reason"] == "amount=5"


def test_rule_5_out_of_date_when_the_model_moved_since_the_evidence():
    t = _trace(checksum="c2", goals=[_sym_goal()])             # the reference now carries another checksum
    row = _req(t, _sym_reqs())["symbols"][0]
    assert row["evidence"]["freshness"] == "out_of_date"
    assert row["state"] == "out_of_date" and row["reason"] == "the code or the model changed since"


def test_rule_6_grade_below_the_required_grade():
    row = _req(_trace(goals=[_sym_goal()]), _sym_reqs(strength="proof"))["symbols"][0]
    assert row["state"] == "open" and row["reason"] == "tested, needs proved"


def test_rule_7_met_and_bound_from_the_file_on_disk(tmp_path):
    (tmp_path / "pay.py").write_text("def can_refund(pi, amount):\n    return True\n")
    r = _req(_trace(goals=[_sym_goal()]), _sym_reqs(), cwd=str(tmp_path))
    row = r["symbols"][0]
    assert row["bound"] is True and row["state"] == "met" and row["reason"] is None
    assert r["state"] == "met" and r["evidence"]["artifact_id"] == "c1"


def test_bound_from_a_source_code_artifact_and_the_ts_patterns(tmp_path):
    t = _trace(goals=[_sym_goal()])
    t["artifacts"].append({"artifact_id": "s1", "artifact_type": "SourceCode", "payload": {"path": "pay.py", "symbols": ["can_refund"]}})
    assert _req(t, _sym_reqs())["symbols"][0]["bound"] is True
    (tmp_path / "pay.ts").write_text("export const can_refund = (pi: PI) => true;\n")
    reqs = _reqs(code=[{"file": "pay.ts", "symbols": ["can_refund"], "maps_to": ["refund_allowed"]}])
    assert _req(_trace(goals=[_sym_goal()]), reqs, cwd=str(tmp_path))["symbols"][0]["bound"] is True
    assert O._bound("pay.rb", "x", str(tmp_path), {}) is None


def test_other_evidence_on_the_symbol_is_shown_but_never_counted():
    t = _trace(arts=[], goals=[_sym_goal()])
    t["actions"] = [{"id": 1, "type": "Formalize", "category": "reasoning", "rationale": "r", "inputs": [], "outputs": ["m1"]},
                    {"id": 2, "type": "Verify", "category": "reasoning", "rationale": "r", "inputs": ["m1"], "outputs": ["g1", "v1"]}]
    t["artifacts"] = [
        {"artifact_id": "m1", "artifact_type": "IMLModel", "derived_from": [], "producer_action_id": 1, "payload": {"formal_code": "let can_refund x = true\n", "symbols": ["can_refund"]}},
        {"artifact_id": "g1", "artifact_type": "VerificationGoal", "derived_from": ["m1"], "producer_action_id": 2, "payload": {"goal_id": 1, "target_symbol": "can_refund"}},
        {"artifact_id": "v1", "artifact_type": "VerificationResult", "derived_from": ["g1"], "producer_action_id": 2,
         "payload": {"goal_id": 1, "goal_artifact_id": "g1", "status": "proved", "engine": "imandrax", "evidence_strength": "proof"}}]
    row = _req(t, _sym_reqs())["symbols"][0]
    assert row["state"] == "open" and row["reason"] == "no evidence yet"
    assert row["other_evidence"]["artifact_id"] == "v1" and row["other_evidence"]["grade"] == "proved"


# ── requirements: the model and the reading ───────────────────────────────────────────────────────

def test_model_revised_makes_the_requirement_out_of_date():
    t = _trace(ref_version="2025-01-01")
    r = _req(t, _reqs())
    assert r["model"]["status"] == "revised" and r["model"]["current_version"] == "2025-01-01"
    assert r["state"] == "out_of_date" and r["reason"] == "the model was revised: 2024-06-20 → 2025-01-01"
    assert _req(_trace(), _reqs(version=None))["model"]["status"] == "unknown"


def test_reading_states():
    findings = ["F-1: 'promptly' is not defined"]
    r = _req(_trace(findings=findings), _reqs())
    assert r["reading"]["state"] == "missing" and r["open_findings"] == findings
    assert r["state"] == "open" and r["reason"] == "reading not chosen"
    interp = {"finding": "F-1", "chosen": "T+1", "justification": "j", "approved_by": "alice"}
    r = _req(_trace(findings=findings), _reqs(interpretation=interp))
    assert r["reading"] == {"state": "chosen", "chosen": "T+1", "approved_by": "alice"} and r["state"] == "met"
    t = _trace(findings=findings, residuals=[{"residual_id": "binding:stripe-refunds:interpretation", "kind": "assumption", "severity": "medium", "status": "open", "statement": "T+1"}])
    assert _req(t, _reqs(interpretation=interp))["reading"]["state"] == "recorded"
    assert _req(_trace(), _reqs())["reading"]["state"] == "not_needed"


def test_summary_gate_blocked_names_the_requirements():
    reqs = {"bindings": [_reqs()["bindings"][0], {"id": "other", "entry": "gallery:stripe/webhooks", "version": "1", "conformance": {"kind": "refinement", "strength": "tests"}}]}
    s = O.requirements(_trace(), reqs)["summary"]
    assert s["requirements"] == 2 and s["met"] == 1 and s["open"] == 1 and s["gate"] == "blocked" and s["blocked_by"] == ["other"]


# ── requirements from goals that are not in the file ─────────────────────────────────────────────

def test_goal_items_outside_the_file_are_requirements_too():
    t = _trace()
    t["actions"] = [{"id": 1, "type": "Formalize", "category": "reasoning", "rationale": "r", "inputs": [], "outputs": ["m1"]},
                    {"id": 2, "type": "Verify", "category": "reasoning", "rationale": "r", "inputs": ["m1"], "outputs": ["g1", "v1"]},
                    {"id": 3, "type": "RunTests", "category": "activity", "rationale": "r", "inputs": [REF], "outputs": ["c1"]}]
    t["artifacts"] = [
        {"artifact_id": "m1", "artifact_type": "IMLModel", "derived_from": [], "producer_action_id": 1, "payload": {"formal_code": "let settle x = x\n", "symbols": ["settle"]}},
        {"artifact_id": "g1", "artifact_type": "VerificationGoal", "derived_from": ["m1"], "producer_action_id": 2, "payload": {"goal_id": 1, "target_symbol": "settle"}},
        {"artifact_id": "v1", "artifact_type": "VerificationResult", "derived_from": ["g1"], "producer_action_id": 2,
         "payload": {"goal_id": 1, "goal_artifact_id": "g1", "status": "proved", "engine": "imandrax", "evidence_strength": "proof"}},
        _conf("c1", 3)]
    t["goals"].append({"id": "session-goal", "intent": "settle is safe", "scope": ["settle"], "status": "active", "acceptance": [
        {"id": "s1", "kind": "property", "label": "settle proved", "required": True, "component": {"function": "settle"}, "evidence": {"artifact": "VerificationResult"}},
        {"id": "s2", "kind": "obligation", "label": "calendar observed", "required": True, "component": {"function": "calendar"}, "evidence": {"artifact": "Observation"}},
        {"id": "s3", "kind": "gap", "label": "nice", "required": False, "status": "doing"}]})
    res = O.requirements(t, _reqs())
    ids = [r["id"] for r in res["requirements"]]
    assert ids == ["stripe-refunds", "session-goal/s1", "session-goal/s2", "session-goal/s3"]   # file-derived first
    s1, s2, s3 = res["requirements"][1:]
    assert s1["state"] == "met" and s1["model"] is None and s1["label"] == "settle proved" and s1["kind"] == "property"
    assert s1["evidence"]["artifact_id"] == "v1" and s1["evidence"]["grade"] == "proved" and s1["symbols"] == []
    assert s2["state"] == "open" and s2["reason"] == "no evidence yet" and s2["required"] is True
    assert s3["state"] == "open" and s3["reason"] == "in progress" and s3["required"] is False
    assert res["summary"]["requirements"] == 4 and res["summary"]["met"] == 2 and res["summary"]["open"] == 2
    # and with no file at all the overview still lists them
    o = O.overview(t, None)
    assert [r["id"] for r in o["requirements"]] == ["session-goal/s1", "session-goal/s2", "session-goal/s3"]
    for r in o["requirements"]:
        assert "label" in r


# ── overview: gaps · gate · next · evidence ───────────────────────────────────────────────────────

def test_overview_gaps_gate_next_and_evidence():
    t = _trace(arts=[_conf("c1", 1), _conf("c2", 2, status="failed", ref="ref:gallery:stripe/idempotency@1", target="replay", entry_sym="outcome", version="1", checksum=None)])
    t["reference_artifacts"].append({"reference_artifact_id": "ref:gallery:stripe/idempotency@1", "artifact_type": "RefFormalModel", "version": "1"})
    t["residuals"] = [
        {"residual_id": "d1", "kind": "defeater", "defeater_kind": "rebuts", "severity": "critical", "status": "open", "statement": "does NOT conform", "target": {"target_type": "artifact", "target_id": "c2"}},
        {"residual_id": "a1", "kind": "assumption", "severity": "medium", "status": "open", "statement": "ints are unbounded"},
        {"residual_id": "q1", "kind": "open_question", "severity": "high", "status": "open", "statement": "JPY path?", "suggested_check": "call it with jpy"},
        {"residual_id": "w1", "kind": "assumption", "severity": "low", "status": "waived", "statement": "settled"},
    ]
    t["policies"] = [{"policy_id": "p-err", "severity": "error"}, {"policy_id": "p-warn", "severity": "warning"}]
    t["policy_evaluations"] = [{"policy_id": "p-err", "status": "failed", "note": "no proof"}, {"policy_id": "p-warn", "status": "failed"}, {"policy_id": "p-ok", "status": "passed"}]
    t["goals"].append(_goal(items=("binding:stripe-idempotency:project",), gid="binding:stripe-idempotency", ref="ref:gallery:stripe/idempotency@1"))
    o = O.overview(t, _reqs())

    gaps = {g["id"]: g for g in o["gaps"]}
    assert [g["id"] for g in o["gaps"]] == ["d1", "q1", "a1"]                      # severity order, waived excluded
    assert gaps["d1"]["state"] == "failed" and gaps["d1"]["symbols"] == ["replay"]
    assert gaps["a1"]["state"] == "assumed" and gaps["q1"]["state"] == "missing" and gaps["q1"]["suggested_check"] == "call it with jpy"
    assert o["counts"]["gaps"] == {"missing": 1, "assumed": 1, "failed": 1, "out_of_date": 0}

    assert o["gate"]["state"] == "blocked" and o["gate"]["blocked_by"] == ["p-err"]
    rules = {r["id"]: r for r in o["gate"]["rules"]}
    assert rules["p-err"] == {"id": "p-err", "state": "blocked", "severity": "error", "note": "no proof"}
    assert rules["p-warn"]["state"] == "warning" and rules["p-ok"]["state"] == "pass"

    kinds = [(s["kind"], s["requirement"]) for s in o["next"]]
    assert ("fix", "stripe-idempotency") in kinds and ("gap", None) in kinds
    assert "establish" not in {k for k, _ in kinds}

    assert o["evidence"]["tested"] == 2 and o["evidence"]["failed"] == 1      # a failed tested result still has a grade
    assert o["evidence"]["by_symbol"]["can_refund"]["grade"] == "tested"
    assert o["record"]["artifacts"] == 2 and o["record"]["actions"] == 2 and o["record"]["outcome"] == "ProcessCompleted"
    assert o["summary"]["gate"] == "pass"          # the requirements summary; the policy gate is o["gate"]

    text = O.render_overview(o)
    for w in ("Requirements", "Gaps", "Gate: blocked", "Next", "[FIX]"):
        assert w in text


def test_overview_with_nothing_declared_is_quiet():
    t = _trace(arts=[], goals=[])
    o = O.overview(t, None)
    assert o["requirements"] == [] and o["gaps"] == [] and o["gate"]["state"] == "pass" and o["next"] == []
    # `pass` here means nothing was asked, and the rendered line has to say so: a bare "Gate: pass" over
    # a record with open gaps reads as an endorsement of the record rather than a statement about
    # policies. The state stays `pass` - it is precise about what it measures - and the line qualifies it.
    assert o["gate"]["rules"] == []
    assert "no policies attached" in O.render_overview(o)
    assert "Next: nothing to do" in O.render_overview(o)


def test_attached_but_unevaluated_policies_are_not_reported_as_unattached():
    """Two states, opposite advice: attach policies, versus run the checker over the ones you have.

    `gate()` builds its rules from `policy_evaluations`, and nothing stamps those until
    `trace check --write` runs - so a trace carrying eight policies rendered "no policies attached",
    sending a reader off to attach what was already there.
    """
    t = _trace(arts=[], goals=[])
    t["policies"] = [{"policy_id": "p%d" % i, "name": "p%d" % i, "formula": "G(true)"} for i in range(8)]

    o = O.overview(t, None)
    assert o["gate"]["rules"] == [] and o["gate"]["attached"] == 8
    text = O.render_overview(o)
    assert "8 policies attached, none evaluated" in text
    assert "trace check --write" in text, "and it names the command that fixes it"
    assert "no policies attached" not in text


# ── integrity ─────────────────────────────────────────────────────────────────────────────────────

def _ver(aid, status="proved"):
    return {"artifact_id": aid, "artifact_type": "VerificationResult", "payload": {"status": status}}


def test_integrity_names_lost_evidence():
    before = {"artifacts": [_conf("c1", 1), _conf("c2", 2, ref="ref:gallery:x@1"), _ver("v1")],
              "goals": [{"id": "g1", "acceptance": [{"id": "a1", "status": "done"}]}]}
    after = {"artifacts": [_conf("c1", 1, ref="src-1"), _ver("v1")], "goals": [{"id": "g1", "acceptance": [{"id": "a1", "status": "todo"}]}]}
    res = O.integrity(before, after)
    assert res["ok"] is False
    assert [(l["id"], l["detail"]) for l in res["lost"]] == [
        ("c1", "no longer cites " + REF), ("c2", "is gone"), ("g1/a1", "was done and is open again")]
    assert res["lost"][1]["what"] == "met requirement" and res["lost"][1]["reference"] == "ref:gallery:x@1"
    assert "would drop 3 items" in O.render_integrity(res)


def test_integrity_is_quiet_for_a_first_write_an_unchanged_record_and_a_new_verdict():
    t = {"artifacts": [_conf("c1", 1), _ver("v1")]}
    assert O.integrity({}, t) == {"ok": True, "lost": []}
    assert O.integrity(None, t)["ok"] is True
    assert O.integrity(t, t)["ok"] is True
    assert O.integrity(t, {"artifacts": t["artifacts"] + [_ver("v2", "refuted")]})["ok"] is True
    assert O.render_integrity(O.integrity(t, t)) == "Record check: nothing would be lost."


# ── the file: YAML and JSON; the CLI ──────────────────────────────────────────────────────────────

def test_requirements_file_yaml_and_json(tmp_path):
    y = tmp_path / "bindings.yaml"
    y.write_text("bindings:\n  - id: stripe-refunds\n    entry: gallery:stripe/refunds\n    version: 2024-06-20\n    conformance: {kind: refinement, strength: tests}\n")
    j = tmp_path / "bindings.json"
    j.write_text(json.dumps(_reqs()))
    # YAML reads the version as a date; normalization makes both files the same requirements
    assert O._requirements_of(O.load_requirements_file(str(y))) == O._requirements_of(O.load_requirements_file(str(j)))
    assert O._requirements_of(O.load_requirements_file(str(y)))[0]["version"] == "2024-06-20"
    assert O._requirements_of({}) == [] and O._requirements_of({"bindings": [{"id": "x"}]}) == []


def _run(args, cwd):
    return subprocess.run([sys.executable, "-m", "ponens.cli"] + args, capture_output=True, text=True, cwd=cwd)


def test_cli_requirements_overview_and_integrity_round_trip(tmp_path):
    t = _trace()
    tp = tmp_path / "trace.json"
    tp.write_text(json.dumps(t))
    rq = tmp_path / "bindings.yaml"
    rq.write_text("bindings:\n  - id: stripe-refunds\n    entry: gallery:stripe/refunds\n    version: 2024-06-20\n    conformance: {kind: refinement, strength: tests}\n")
    r = _run(["trace", "requirements", str(tp), "--file", str(rq), "--json"], str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["summary"]["gate"] == "pass"
    r = _run(["trace", "overview", str(tp), "--file", str(rq), "--json"], str(tmp_path))
    assert r.returncode == 0, r.stderr
    o = json.loads(r.stdout)
    assert o["requirements"][0]["state"] == "met" and o["gate"]["state"] == "pass" and "next" in o and "evidence" in o
    r = _run(["trace", "overview", str(tp)], str(tmp_path))
    assert r.returncode == 0 and "Gate: pass" in r.stdout
    weaker = tmp_path / "weaker.json"
    weaker.write_text(json.dumps({**t, "artifacts": []}))
    r = _run(["trace", "integrity", str(tp), str(weaker), "--json"], str(tmp_path))
    assert r.returncode == 3 and json.loads(r.stdout)["lost"][0]["id"] == "c1"
    r = _run(["trace", "integrity", str(tp), str(tp)], str(tmp_path))
    assert r.returncode == 0 and "nothing would be lost" in r.stdout

"""Unit tests for the action's pure core: trace discovery, the gate fold, the scorecard, and the
comment body. The subprocess / GitHub calls are exercised by the self-test workflow, not here."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import run as act  # noqa: E402


def test_find_trace_prefers_explicit_then_single_published(tmp_path):
    os.makedirs(tmp_path / ".ponens")
    (tmp_path / ".ponens" / "codelogician.json").write_text("{}")
    (tmp_path / ".ponens" / "codelogician.json.sync").write_text("{}")   # sidecar ignored
    assert act.find_trace("", str(tmp_path)) == os.path.join(".ponens", "codelogician.json")
    (tmp_path / "other.json").write_text("{}")
    assert act.find_trace("other.json", str(tmp_path)) == "other.json"
    assert act.find_trace("missing.json", str(tmp_path)) is None
    (tmp_path / ".ponens" / "second.json").write_text("{}")             # ambiguous → none
    assert act.find_trace("", str(tmp_path)) is None


def test_gate_folds_evaluations_by_severity_and_fail_on():
    evals = [
        {"policy_id": "p_ok", "status": "passed"},
        {"policy_id": "p_err", "status": "failed", "note": "no proof", "violating_artifact_ids": ["a9"]},
        {"policy_id": "p_warn", "status": "failed"},
        {"policy_id": "p_off", "status": "disabled"},
    ]
    sev = {"p_err": "error", "p_warn": "warning"}
    v = act.gate(evals, sev, "error")
    assert v["status"] == "failed" and v["checked"] == 4 and v["passed"] == 1
    assert [r["policy_id"] for r in v["violations"]] == ["p_err", "p_warn"]    # errors first
    assert v["violations"][0]["violating"] == ["a9"]
    assert act.gate(evals, sev, "never")["status"] == "advisory"
    assert act.gate([evals[0], evals[2]], sev, "error")["status"] == "advisory"  # only a warning failed
    assert act.gate([evals[0], evals[2]], sev, "warning")["status"] == "failed"
    assert act.gate([evals[0]], sev, "error")["status"] == "passed"
    # Unknown policy → error by default (the safe reading).
    assert act.gate([{"policy_id": "mystery", "status": "failed"}], {}, "error")["status"] == "failed"


def test_severity_index_reads_trace_and_policy_file():
    trace = {"policies": [{"policy_id": "a", "severity": "warning"}, {"name": "b"}]}
    pf = {"policies": [{"policy_id": "c", "severity": "Info"}]}
    assert act.severity_index(trace, pf) == {"a": "warning", "b": "error", "c": "info"}


def test_scorecard_reads_enriched_goals_and_summary():
    enriched = {
        "goals": [{"id": "g1", "intent": "refund never over-refunds", "progress": 0.5, "at_risk": 1, "open_gaps": 1,
                   "min_strength": "attested", "faithfulness": {"met": False, "certified": False},
                   "acceptance": [{"id": "s1", "status": "done", "evidence_strength": "proof", "freshness": "stale"},
                                  {"id": "s2", "status": "todo"}]}],
        "summary": {"goals_total": 1, "goals_met": 0, "open_residuals": 2, "open_high": 1, "stale_evidence": 1},
    }
    c = act.scorecard(enriched)
    assert c["summary"] == {"goals_total": 1, "goals_met": 0, "open_residuals": 2, "open_high": 1, "stale_evidence": 1}
    g = c["goals"][0]
    assert g["met"] is False and g["at_risk"] == 1 and g["min_strength"] == "attested"
    assert g["items"][0] == {"id": "s1", "status": "done", "strength": "proof", "freshness": "stale"}


def test_render_comment_carries_marker_verdict_goals_and_report():
    verdict = act.gate([{"policy_id": "p_err", "status": "failed", "note": "no proof", "violating_artifact_ids": ["a9"]},
                        {"policy_id": "ok", "status": "passed"}], {"p_err": "error"}, "error")
    card = act.scorecard({"goals": [{"id": "g1", "intent": "settle is safe | really", "progress": 1.0, "at_risk": 0,
                                     "open_gaps": 0, "min_strength": "proof", "faithfulness": {"met": True}}],
                          "summary": {"goals_total": 1, "goals_met": 1}})
    body = act.render_comment("failed", ".ponens/codelogician.json", verdict, card, "### 🧭 Ponens reasoning trace\n\n**Grade B**",
                              run_url="https://x/run/1")
    assert body.startswith(act.MARKER)
    assert "## ❌ Governance failed" in body
    assert "`.ponens/codelogician.json` · [run](https://x/run/1)" in body
    assert "**Policies:** 1/2 passed, 1 failed" in body
    assert "🔴 **p_err** (error): no proof — `a9`" in body
    assert "**Goals:** 1/1 met" in body
    assert "| settle is safe \\| really | ✅ met | 100% | proof | 0 | 0 |" in body   # pipes escaped
    assert "**Grade B**" in body
    assert "ponens.dev" in body


def test_render_no_trace_and_invalid():
    body = act.render_comment("no-trace", None, None, None, "", note="No reasoning trace was found")
    assert "## ⚪ No reasoning trace" in body and "No reasoning trace was found" in body
    body = act.render_comment("invalid", "t.json", None, None, "", note="```\nerror: missing trace_id\n```")
    assert "## ❌ Invalid trace" in body and "missing trace_id" in body


def test_outputs_and_summary_are_written_to_the_github_files(tmp_path, monkeypatch):
    out, summ = tmp_path / "out", tmp_path / "summary"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summ))
    act.set_output("status", "passed")
    act.set_output("violations", 0)
    act.step_summary("# hi\n")
    assert out.read_text() == "status=passed\nviolations=0\n"
    assert summ.read_text() == "# hi\n"


def test_pr_number_from_event_payload(tmp_path, monkeypatch):
    p = tmp_path / "event.json"
    p.write_text(json.dumps({"pull_request": {"number": 42}}))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(p))
    assert act.pr_number() == 42
    p.write_text(json.dumps({"ref": "refs/heads/main"}))
    assert act.pr_number() is None


@pytest.mark.skipif(not (os.environ.get("PONENS_BIN") or __import__("shutil").which("ponens")), reason="needs ponens")
def test_end_to_end_against_the_stripe_sample(tmp_path, monkeypatch):
    """Drive the real CLI on the repo's sample trace, outside a PR (no comment), and read the outputs."""
    import shutil
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    os.makedirs(tmp_path / ".ponens")
    shutil.copy(os.path.join(repo, "examples", "stripe_v1_1.json"), tmp_path / ".ponens" / "trace.json")
    monkeypatch.chdir(tmp_path)
    for k in ("INPUT_TRACE", "INPUT_TRANSCRIPT", "INPUT_POLICIES", "INPUT_POLICY_FILE", "GITHUB_EVENT_PATH", "GH_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out"))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary"))
    rc = act.main()
    outputs = dict(line.split("=", 1) for line in (tmp_path / "out").read_text().splitlines())
    assert rc == 0, outputs
    assert outputs["status"] in ("passed", "advisory")
    assert outputs["trace"] == os.path.join(".ponens", "trace.json")
    body = (tmp_path / ".ponens-ci" / "report.md").read_text()
    assert act.MARKER in body and "Ponens reasoning trace" in body and "**Policies:**" in body


def _bindings_doc(gate=False):
    ev = lambda grade: {"artifact_id": "c", "grade": grade, "status": "passed", "freshness": "fresh"}  # noqa: E731
    return {"requirements": [
        {"id": "rts22", "model": {"entry": "atlas:mifir-rts22-art4", "reference": "ref:atlas:mifir-rts22-art4@2017/590", "version": "2017/590",
                                  "current_version": "2017/590 · rev 2", "status": "revised"},
         "state": "out_of_date", "reason": "the model was revised: 2017/590 → 2017/590 · rev 2", "evidence": ev("proved"),
         "reading": {"state": "recorded", "chosen": "Strict"},
         "symbols": [{"scope": "symbol", "symbol": "is_transmitted", "entry_symbol": "transmitted_strict", "state": "met", "reason": None, "evidence": ev("proved")},
                     {"scope": "symbol", "symbol": "agreement_terms_ok", "entry_symbol": "agreement_terms", "state": "open", "reason": "tested, needs proved", "evidence": ev("tested")}]},
        {"id": "psd2", "model": {"entry": "atlas:psd2-exemptions", "reference": "ref:atlas:psd2-exemptions", "status": "unknown"},
         "state": "open", "reason": "reading not chosen", "evidence": None, "reading": {"state": "missing"},
         "symbols": [{"scope": "symbol", "symbol": "is_exempt", "entry_symbol": "exemption_applies", "state": "open", "reason": "not yet in the record", "evidence": None}]}],
        "summary": {"requirements": 2, "met": 0 if not gate else 2, "open": 0 if gate else 1, "failed": 0, "out_of_date": 0 if gate else 1,
                    "gate": "pass" if gate else "blocked", "blocked_by": [] if gate else ["rts22", "psd2"]}}


def test_bindings_render_and_gate():
    doc = _bindings_doc()
    lines = act.render_bindings(doc)
    assert lines[1] == "**Requirements:** ❌ 2 requirements · 0 met · 1 open · 1 out of date"
    assert "| `rts22` · `ref:atlas:mifir-rts22-art4@2017/590` · reading Strict · 🔴 model revised → 2017/590 · rev 2 | `is_transmitted` → `transmitted_strict` | proved · fresh | ✅ met |" in lines
    assert "|  | `agreement_terms_ok` → `agreement_terms` | tested · fresh | 🔴 open (tested, needs proved) |" in lines
    assert "| `psd2` · `ref:atlas:psd2-exemptions` · 🔴 no reading chosen | `is_exempt` → `exemption_applies` | — | 🔴 open (not yet in the record) |" in lines
    assert act.render_bindings({"requirements": [], "summary": {}}) == []
    assert act.bindings_status(doc, "error") == "failed"
    assert act.bindings_status(doc, "warning") == "failed"
    assert act.bindings_status(doc, "never") == "passed"
    assert act.bindings_status(_bindings_doc(gate=True), "error") == "passed"
    assert act.bindings_status(None, "error") == "skipped"
    assert act.bindings_status({"requirements": [], "summary": {"gate": "blocked"}}, "error") == "skipped"
    body = act.render_comment("failed", "t.json", {"status": "failed", "violations": [], "checked": 0, "passed": 0}, None, "", bindings=doc)
    assert "**Requirements:** ❌" in body and body.index("**Requirements:**") > body.index("**Policies:**")


def test_load_bindings_off_path_and_auto(tmp_path, monkeypatch):
    assert act.load_bindings("off", str(tmp_path)) is None
    (tmp_path / "b.json").write_text(json.dumps(_bindings_doc(True)))
    assert act.load_bindings("b.json", str(tmp_path))["summary"]["gate"] == "pass"
    assert act.load_bindings("missing.json", str(tmp_path)) is None
    # auto: nothing to check without a bindings file / a pre-computed JSON
    monkeypatch.setattr(act.shutil, "which", lambda _n: None)
    assert act.load_bindings("auto", str(tmp_path)) is None
    os.makedirs(tmp_path / ".ponens-ci")
    (tmp_path / ".ponens-ci" / "bindings.json").write_text(json.dumps(_bindings_doc()))
    assert act.load_bindings("auto", str(tmp_path))["summary"]["gate"] == "blocked"
    # auto with a requirements file and `cl` on PATH runs `cl requirements --json`
    os.makedirs(tmp_path / ".codelogician")
    (tmp_path / ".codelogician" / "bindings.yaml").write_text("bindings: []\n")
    monkeypatch.setattr(act.shutil, "which", lambda _n: "/usr/bin/cl")
    calls = []

    class P:
        stdout = json.dumps(_bindings_doc(True)); stderr = ""; returncode = 1

    monkeypatch.setattr(act.subprocess, "run", lambda args, **kw: calls.append(args) or P())
    assert act.load_bindings("auto", str(tmp_path))["summary"]["gate"] == "pass"
    assert calls[0][:3] == ["cl", "requirements", "--json"]


def _scan_doc(not_met=1):
    md = ("## CodeLogician scan · stripe\n\n13 checks passed · 1 not met · gate pass\n\n### Requirements not met (1)\n\n"
          "- **can_refund does not meet gallery:stripe/refunds:refund_allowed: 1 of 4 cases differ** · high · tested\n  - when amount = 0: model expects false, but the code returns true.\n")
    return {"version": 1, "mode": "no-agent", "scope": {"base": "0123456789abcdef", "files": ["pay.py"], "functions": ["can_refund"]},
            "summary": {"not_met": not_met, "checks_passed": 13}, "report": {"headline": "13 checks passed · 1 not met · gate pass", "markdown": md}}


def test_scan_render_status_and_base(tmp_path, monkeypatch):
    doc = _scan_doc()
    lines = act.render_scan(doc)
    assert lines[1] == "**Scan:** 13 checks passed · 1 not met · gate pass · changes since `0123456789ab`"
    assert "### Requirements not met (1)" in lines
    assert not any(l.startswith("## ") for l in lines)
    assert act.render_scan(None) == []
    assert act.scan_status(doc, "error") == "failed"
    assert act.scan_status(doc, "never") == "passed"
    assert act.scan_status(_scan_doc(0), "error") == "passed"
    assert act.scan_status(None, "error") == "skipped"
    body = act.render_comment("failed", "t.json", {"status": "failed", "violations": [], "checked": 0, "passed": 0}, None, "", scan=doc)
    assert "**Scan:**" in body and body.index("**Scan:**") > body.index("**Policies:**")
    p = tmp_path / "event.json"
    p.write_text(json.dumps({"pull_request": {"number": 7, "base": {"sha": "abc123"}}}))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(p))
    assert act.pr_base_sha() == "abc123"


def test_load_scan_modes(tmp_path, monkeypatch):
    assert act.load_scan("off", str(tmp_path), None) is None
    monkeypatch.setattr(act.shutil, "which", lambda _n: None)
    assert act.load_scan("no-agent", str(tmp_path), None) is None      # no cl on PATH → skipped, not failed
    monkeypatch.setattr(act.shutil, "which", lambda _n: "/usr/bin/cl")
    calls = []
    class P:
        stdout = json.dumps(_scan_doc()); stderr = ""; returncode = 1
    monkeypatch.setattr(act.subprocess, "run", lambda args, **kw: calls.append(args) or P())
    doc = act.load_scan("no-agent", str(tmp_path), "abc123")
    assert doc["summary"]["not_met"] == 1
    assert calls[0] == ["cl", "scan", "--json", "--dir", str(tmp_path), "--no-agent", "--diff", "abc123"]
    act.load_scan("agent", str(tmp_path), None)
    assert calls[1] == ["cl", "scan", "--json", "--dir", str(tmp_path)]
    assert act.load_scan("bogus", str(tmp_path), None) is None

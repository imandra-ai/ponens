"""Whole workflows, asserted on what a person actually READS.

The property suites check structure: that nothing declared becomes unreadable, that standing only
improves on evidence or a recorded decision. They cannot check whether the account a person gets back
makes sense - and several bugs in this area were exactly that. `trace check` once printed `-2
advisory` because syntax rejections were counted twice. `overview` said "no policies attached" about a
trace carrying eight. `grade` called a warning a failed governance gate while the gate passed. Every
one of those was found by a human reading output and frowning, and none of them would fail a
structural test.

So these run real workflows end to end through the CLI, in the order someone would actually run them,
and assert the OUTPUT. A story that reads wrong fails here even when every artifact is well-formed.

Engine verdicts are written the way an engine writes them (there is deliberately no `--status proved`
on the CLI - a verdict is earned, not typed). Everything a PERSON does goes through the CLI.
"""
import json
import subprocess
import sys

import pytest


def cli(trace_file, *args, expect=0):
    """Run a ponens command the way a person would, and return what they'd see."""
    r = subprocess.run([sys.executable, "-m", "ponens.cli", "trace", *args],
                       capture_output=True, text=True)
    out = r.stdout + r.stderr
    if expect is not None:
        assert r.returncode == expect, f"`trace {' '.join(args)}` rc={r.returncode}\n{out}"
    return out


def _read(f):
    return json.loads(f.read_text())


def _write(f, t):
    f.write_text(json.dumps(t, indent=2))


def _goal_and_result(f, *, vg, vr, status, symbol, prop, model, label):
    """What an oracle deposits when it runs a property: the GOAL it was asked to establish, then the
    result over that goal. A criterion binds to the goal - a result floating free of one establishes
    nothing in particular, which is why the resolver insists on both."""
    t = _read(f)
    nid = max([a["id"] for a in t.get("actions") or []] or [0]) + 1
    if not any(a["artifact_id"] == vg for a in t.get("artifacts") or []):
        t.setdefault("actions", []).append({
            "id": nid, "type": "DefineVG", "category": "reasoning",
            "rationale": f"define: {label}", "inputs": [model], "outputs": [vg]})
        t.setdefault("artifacts", []).append({
            "artifact_id": vg, "artifact_type": "VerificationGoal", "name": vg,
            "producer_action_id": nid, "derived_from": [model],
            # `description` is where the property keyword lives - a criterion binds to a goal by what
            # the goal SAYS it establishes, so a producer that omits it binds to nothing.
            "payload": {"target_symbol": symbol, "property": prop, "goal_id": vg,
                        "description": f"{symbol}: {prop}"}})
        nid += 1
    t.setdefault("actions", []).append({
        "id": nid, "type": "Verify", "category": "reasoning", "rationale": label,
        "inputs": [vg], "outputs": [vr]})
    t.setdefault("artifacts", []).append({
        "artifact_id": vr, "artifact_type": "VerificationResult", "name": vr,
        "producer_action_id": nid, "derived_from": [vg],
        "payload": {"status": status, "goal_artifact_id": vg, "target_symbol": symbol,
                    "property": prop, "engine": "imandrax", "evidence_strength": "proof"}})
    _write(f, t)
    return nid


def _model(f, name="capture_model", symbol="capture"):
    t = _read(f)
    nid = max([a["id"] for a in t.get("actions") or []] or [0]) + 1
    t.setdefault("actions", []).append({
        "id": nid, "type": "Formalize", "category": "reasoning",
        "rationale": "formalize the capture path", "inputs": [], "outputs": [name]})
    t.setdefault("artifacts", []).append({
        "artifact_id": name, "artifact_type": "IMLModel", "name": name,
        "producer_action_id": nid, "payload": {"symbols": [symbol]}})
    _write(f, t)
    return nid


@pytest.fixture
def trace(tmp_path):
    f = tmp_path / "work.json"
    cli(f, "init", str(f), "--model", "imandrax", "--assistant", "codelogician")
    return f


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# STORY 1  "I changed the capture path. Does the money math still hold?"
# ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_story_a_refuted_property_is_fixed_and_re_proved(trace):
    f = trace
    cli(f, "goal", "set", str(f), "--intent", "make capture idempotent", "--id", "g")
    cli(f, "goal", "accept", str(f), "--goal", "g", "--kind", "property",
        "--label", "capture is idempotent", "--symbol", "capture", "--property", "idempotent")

    # Before any evidence, the record is honest about being empty.
    out = cli(f, "resolve", str(f))
    assert "0%" in out, out
    assert "capture is idempotent" in out

    _model(f)
    _goal_and_result(f, vg="vg1", vr="vr1", status="refuted", symbol="capture", prop="idempotent",
                     model="capture_model", label="verify idempotency")

    # A REFUTED result must not read as progress. This is the whole point of the record.
    out = cli(f, "resolve", str(f))
    assert "100%" not in out, f"a refutation must not count as done:\n{out}"

    # The developer fixes the code and the property is re-established.
    _goal_and_result(f, vg="vg1", vr="vr2", status="proved", symbol="capture", prop="idempotent",
                     model="capture_model", label="re-verify after the fix")

    out = cli(f, "resolve", str(f))
    assert "100%" in out, f"the goal should read met once the property is proved:\n{out}"
    # BOTH results stay: the refutation is why the fix exists.
    ids = {a["artifact_id"] for a in _read(f)["artifacts"]}
    assert {"vr1", "vr2"} <= ids

    out = cli(f, "next", str(f))
    assert "capture is idempotent" not in out, f"nothing left to do on a met criterion:\n{out}"


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# STORY 2  "A reviewer asks about the gap we waived."
# ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_story_a_gap_is_waived_then_contested_then_settled(trace):
    f = trace
    _model(f)
    cli(f, "residual", "add", str(f), "--kind", "limitation", "--severity", "high",
        "--statement", "Idempotency holds only for single-threaded application.",
        "--suggested-check", "Add a concurrency model and re-verify.",
        "--introduced-by", "1", "--target-type", "artifact", "--target-id", "capture_model")

    # The gap is open, and `next` tells the reader what closing it would take.
    out = cli(f, "next", str(f))
    assert "Add a concurrency model" in out, out

    out = cli(f, "residuals", str(f))
    assert "open" in out and "1 open" in out

    # An engineer accepts it as a documented limitation, with reasoning.
    cli(f, "residual", "resolve", str(f), "r1", "--status", "waived",
        "--justification", "The gateway serialises per intent, so the interleaving cannot arise.",
        "--by", "eng-lead")
    out = cli(f, "residuals", str(f))
    assert "waived by eng-lead" in out, out
    assert "The gateway serialises per intent" in out
    assert "0 open" in out
    assert "1 closed" in out
    # `next` stops nagging about a gap that has been dealt with.
    assert "Add a concurrency model" not in cli(f, "next", str(f))

    # A reviewer says the reasoning is wrong. The waiver is NOT removed.
    cli(f, "residual", "contest", str(f), "rr1",
        "--reason", "It serialises per intent, not per customer; two intents touch one balance.",
        "--by", "security-review")
    out = cli(f, "residuals", str(f))
    assert "CONTESTED" in out, f"the waiver must read as contested:\n{out}"
    assert "The gateway serialises per intent" in out, "the justification stays readable"
    assert "It serialises per intent, not per customer" in out, "so does the objection"
    # And the gap is open business again.
    assert "Add a concurrency model" in cli(f, "next", str(f))

    # The team checks and the objection does not hold. The original waiver stands again.
    cli(f, "residual", "resolve", str(f), "r2", "--status", "addressed",
        "--justification", "Confirmed with payments: the ledger row-locks the balance.",
        "--by", "eng-lead")
    out = cli(f, "residuals", str(f))
    assert "CONTESTED" not in out
    assert "waived by eng-lead" in out
    assert "Add a concurrency model" not in cli(f, "next", str(f))

    # Every turn of the argument is still in the record.
    for phrase in ("The gateway serialises per intent",
                   "It serialises per intent, not per customer",
                   "Confirmed with payments"):
        assert phrase in out or phrase in cli(f, "residuals", str(f)), phrase


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# STORY 3  "We can't meet one criterion before the release."
# ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_story_a_criterion_is_withdrawn_before_release(trace, tmp_path):
    f = trace
    cli(f, "goal", "set", str(f), "--intent", "ship the capture rewrite", "--id", "g")
    for label, sym in (("capture is idempotent", "capture"), ("refunds are bounded", "refund")):
        cli(f, "goal", "accept", str(f), "--goal", "g", "--kind", "property",
            "--label", label, "--symbol", sym, "--property", "p")
    _model(f)
    _goal_and_result(f, vg="vg1", vr="vr1", status="proved", symbol="capture", prop="p",
                     model="capture_model", label="verify idempotency")

    out = cli(f, "resolve", str(f))
    assert "50%" in out, f"one of two met:\n{out}"

    before = tmp_path / "before.json"
    before.write_text(f.read_text())

    # The second criterion will not land this release. Withdrawing it needs a reason.
    out = cli(f, "goal", "drop", str(f), "s2", "--goal", "g", expect=2)
    assert "--reason" in out, "withdrawing without a reason must be refused"

    cli(f, "goal", "drop", str(f), "s2", "--goal", "g",
        "--reason", "Refund bounds move to the next release; tracked in PAY-1182.",
        "--by", "eng-lead")

    # It reads 100% - and the reader is told, in the same breath, that the bar moved.
    out = cli(f, "resolve", str(f))
    assert "100%" in out
    assert "definition of done was amended" in out, f"100% must not stand unqualified:\n{out}"
    assert "which was not met" in out, out
    assert "PAY-1182" in out, "the reason a reader needs is right there"

    # And comparing against the earlier record reports the loss.
    out = cli(f, "integrity", str(before), str(f), expect=3)
    assert "gone from the definition of done" in out, out

    # The withdrawn criterion is still readable in full.
    was = [a for a in _read(f)["artifacts"] if a["artifact_type"] == "GoalAmendment"][0]
    assert was["payload"]["was"]["label"] == "refunds are bounded"


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# STORY 4  "Hand it to someone who wasn't there."
# ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_story_a_stranger_can_read_the_finished_record(trace):
    f = trace
    cli(f, "goal", "set", str(f), "--intent", "make capture idempotent", "--id", "g")
    cli(f, "goal", "accept", str(f), "--goal", "g", "--kind", "property",
        "--label", "capture is idempotent", "--symbol", "capture", "--property", "idempotent")
    _model(f)
    _goal_and_result(f, vg="vg1", vr="vr1", status="proved", symbol="capture", prop="idempotent",
                     model="capture_model", label="verify idempotency")
    cli(f, "residual", "add", str(f), "--kind", "assumption", "--severity", "medium",
        "--statement", "Assumes the gateway retries at most three times.",
        "--suggested-check", "Confirm the retry budget with payments.", "--introduced-by", "1")
    cli(f, "complete", str(f), "--summary", "capture is idempotent; retry budget assumed")

    # Every reader runs, agrees the work is done, and agrees a gap is outstanding.
    assert "Valid trace" in cli(f, "validate", str(f))
    assert "100%" in cli(f, "resolve", str(f))

    residuals = cli(f, "residuals", str(f))
    assert "1 open" in residuals
    assert "Assumes the gateway retries" in residuals

    nxt = cli(f, "next", str(f))
    assert "Confirm the retry budget" in nxt, f"the one outstanding thing must be the next thing:\n{nxt}"

    ov = cli(f, "overview", str(f))
    assert "Traceback" not in ov
    # The overview's gap count and the residual surface must tell the same story - they are two
    # renderings of one fact, and they have disagreed before.
    parsed = json.loads(ov) if ov.strip().startswith("{") else None
    if parsed:
        assert sum(parsed["counts"]["gaps"].values()) >= 1, ov


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# STORY 5  "The gate has to mean something."
# ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_story_the_gate_speaks_plainly(trace):
    f = trace
    _model(f)
    cli(f, "residual", "add", str(f), "--kind", "limitation", "--severity", "critical",
        "--statement", "The concurrent path is unverified.", "--introduced-by", "1",
        "--suggested-check", "Model it and re-verify.")
    cli(f, "complete", str(f), "--summary", "partial")

    out = cli(f, "check", str(f), expect=None)
    # Whatever the verdict, the summary must not contradict itself or print a negative count - the
    # shape of a real bug here ("-2 advisory", from counting syntax rejections twice).
    assert "Traceback" not in out
    assert "-1 " not in out and "-2 " not in out, f"negative count in the summary:\n{out}"

    grade = cli(f, "grade", str(f), expect=None)
    assert "Traceback" not in grade
    # `grade` measures how good the RECORD is, `check` is the gate on the work - two different
    # questions, and they must not contradict each other about the negative space.
    assert "negative space" in grade.lower(), grade

    # The critical gap is named where a reader looks for outstanding work.
    assert "concurrent path is unverified" in cli(f, "residuals", str(f)).lower()
    assert "Model it and re-verify" in cli(f, "next", str(f))


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# STORY 6  "The code moved under the proof."
# ─────────────────────────────────────────────────────────────────────────────────────────────────

def _model_rev(f, *, aid, src, source_node="src.py", label="formalize"):
    """A formalization revision with INLINE source. Freshness recomputes a dependency-closure checksum
    from this, so a model without it can only be judged by heuristic - the producer contract."""
    t = _read(f)
    nid = max([a["id"] for a in t.get("actions") or []] or [0]) + 1
    t.setdefault("actions", []).append({
        "id": nid, "type": "Formalize", "category": "reasoning", "rationale": label,
        "inputs": [source_node], "outputs": [aid]})
    t.setdefault("artifacts", []).append({
        "artifact_id": aid, "artifact_type": "IMLModel", "name": aid, "producer_action_id": nid,
        "derived_from": [source_node], "payload": {"iml_code": src}})
    _write(f, t)
    return nid


def test_story_a_proof_goes_stale_when_its_model_changes(trace):
    f = trace
    t = _read(f)
    t.setdefault("artifacts", []).append(
        {"artifact_id": "src.py", "artifact_type": "SourceCode", "name": "src.py"})
    _write(f, t)

    cli(f, "goal", "set", str(f), "--intent", "keep capture idempotent", "--id", "g")
    cli(f, "goal", "accept", str(f), "--goal", "g", "--kind", "property",
        "--label", "capture is idempotent", "--symbol", "capture", "--property", "idempotent")

    _model_rev(f, aid="m1", src="let fee x = x / 10\nlet capture p = if p.done then p else fee p\n")
    _goal_and_result(f, vg="vg1", vr="vr1", status="proved", symbol="capture", prop="idempotent",
                     model="m1", label="verify idempotency")

    out = cli(f, "resolve", str(f))
    assert "100%" in out, out
    assert "Nothing to do" in cli(f, "next", str(f))

    # Someone edits a function the proof DEPENDS on - not the proved one. The closure moved, so the
    # standing proof is no longer about the code that is there.
    _model_rev(f, aid="m2", src="let fee x = x / 5\nlet capture p = if p.done then p else fee p\n",
               label="re-formalize after the fee change")

    out = cli(f, "residuals", str(f), "--derived")
    assert "stale" in out.lower(), f"a proof over changed code must surface as stale:\n{out}"

    nxt = cli(f, "next", str(f))
    assert "Nothing to do" not in nxt, f"stale evidence is work:\n{nxt}"
    assert "re-run" in nxt.lower() or "refresh" in nxt.lower() or "stale" in nxt.lower(), nxt

    # Re-running the proof against the current model heals it.
    _goal_and_result(f, vg="vg1", vr="vr2", status="proved", symbol="capture", prop="idempotent",
                     model="m2", label="re-verify against the current model")
    out = cli(f, "residuals", str(f), "--derived")
    assert "stale" not in out.lower(), f"a re-proof must heal the guard:\n{out}"
    assert "100%" in cli(f, "resolve", str(f))


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# STORY 7  "Someone found a counterexample to something we proved."
# ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_story_a_defeater_blocks_a_proved_criterion(trace):
    f = trace
    cli(f, "goal", "set", str(f), "--intent", "prove the amount invariant", "--id", "g")
    cli(f, "goal", "accept", str(f), "--goal", "g", "--kind", "property",
        "--label", "amounts are bounded", "--symbol", "capture", "--property", "bounded")
    _model(f)
    _goal_and_result(f, vg="vg1", vr="vr1", status="proved", symbol="capture", prop="bounded",
                     model="capture_model", label="verify the bound")
    assert "100%" in cli(f, "resolve", str(f))

    # A reviewer finds counter-evidence against the PROOF ITSELF. A contested claim is not established.
    cli(f, "residual", "add", str(f), "--kind", "defeater", "--defeater-kind", "rebuts",
        "--severity", "critical", "--target-type", "artifact", "--target-id", "vr1",
        "--statement", "The model omits the partial-capture path, where the bound does not hold.",
        "--suggested-check", "Model partial capture and re-verify.", "--introduced-by", "1")

    out = cli(f, "resolve", str(f))
    assert "100%" not in out, f"a contested proof must not read as done:\n{out}"
    assert "✗" in out or "blocked" in out.lower(), out

    nxt = cli(f, "next", str(f))
    assert "Model partial capture" in nxt, f"the reader must be told what would settle it:\n{nxt}"

    # The gap is closed by evidence, and the criterion is established again.
    cli(f, "residual", "resolve", str(f), "r1", "--status", "addressed",
        "--justification", "Partial capture modelled and the bound re-proved.",
        "--by", "eng-lead")
    assert "100%" in cli(f, "resolve", str(f))


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# STORY 8  "CI has to say yes or no."
# ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_story_the_policy_gate_fails_then_passes(trace):
    f = trace
    _model(f)
    # The real path a person takes. Two shortcuts were tried first and both were correctly refused:
    # a hand-authored policy, and the gallery FILE copied in - the gallery's on-disk shape is not the
    # trace's policy shape, and `policies add` is what converts it. The gate rejecting a malformed
    # rule instead of pretending to evaluate it is the behaviour you want.
    r = subprocess.run([sys.executable, "-m", "ponens.cli", "policies", "add",
                        "no_open_critical_residuals", "--into", str(f)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    cli(f, "residual", "add", str(f), "--kind", "limitation", "--severity", "critical",
        "--statement", "The concurrent path is unverified.",
        "--suggested-check", "Model it and re-verify.", "--introduced-by", "1")
    cli(f, "complete", str(f), "--summary", "work in progress")

    fail = cli(f, "check", str(f), expect=None)
    assert "Traceback" not in fail
    assert "no_open_critical_residuals" in fail, fail
    assert "SYNTAX" not in fail, f"a gallery policy must not be rejected as malformed:\n{fail}"
    assert "1 failed" in fail or "FAIL" in fail, f"an open critical gap must fail the gate:\n{fail}"

    # The team accepts the gap, with reasoning. The gate is what changes, and only because of that.
    cli(f, "residual", "resolve", str(f), "r1", "--status", "waived",
        "--justification", "Single-threaded deployment for this release; tracked in PAY-1200.",
        "--by", "eng-lead")

    ok = cli(f, "check", str(f), expect=None)
    assert "Traceback" not in ok
    assert "0 failed" in ok or "1 passed" in ok, f"the gate must respond to the decision:\n{ok}"
    # And the reason the gate flipped is readable, not implicit - a gate that changes its mind with
    # no recorded reason is the thing this whole format exists to prevent.
    assert "PAY-1200" in cli(f, "residuals", str(f))


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# STORY 9  "A reviewer says the definition of done is wrong."
# ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_story_criteria_are_reviewed_then_re_reviewed(trace):
    f = trace
    cli(f, "goal", "set", str(f), "--intent", "make capture idempotent", "--id", "g")
    cli(f, "goal", "accept", str(f), "--goal", "g", "--kind", "property",
        "--label", "capture is idempotent", "--symbol", "capture", "--property", "idempotent")

    out = cli(f, "goal", "ls", str(f))
    assert "uncertified" in out.lower(), f"unreviewed criteria must say so:\n{out}"

    cli(f, "goal", "certify", str(f), "--goal", "g", "--by", "reviewer",
        "--verdict", "changes-requested", "--note", "idempotency alone does not cover refunds")
    out = cli(f, "goal", "ls", str(f))
    assert "certified" not in out.lower() or "uncertified" in out.lower(), \
        f"changes-requested must not read as certified:\n{out}"

    # The team adds what was missing and the reviewer approves.
    cli(f, "goal", "accept", str(f), "--goal", "g", "--kind", "property",
        "--label", "refunds are bounded", "--symbol", "refund", "--property", "bounded")
    out = cli(f, "goal", "certify", str(f), "--goal", "g", "--by", "reviewer", "--verdict", "approved",
              "--note", "covers refunds now")
    assert "supersedes changes-requested" in out, f"the earlier verdict must be named:\n{out}"

    out = cli(f, "goal", "ls", str(f))
    assert "uncertified" not in out.lower(), out

    # Both verdicts are in the record - an approval that erased a rejection is not a review trail.
    from ponens import lineage
    ams = [a for a in lineage.amendments_of(_read(f), "g") if a["change"] == "criteria_reviewed"]
    assert [a["was"]["verdict"] if a.get("was") else None for a in ams] == [None, "changes-requested"]


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# STORY 10  "Put it in the PR."
# ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_story_the_report_matches_the_record(trace):
    f = trace
    cli(f, "goal", "set", str(f), "--intent", "make capture idempotent", "--id", "g")
    cli(f, "goal", "accept", str(f), "--goal", "g", "--kind", "property",
        "--label", "capture is idempotent", "--symbol", "capture", "--property", "idempotent")
    _model(f)
    _goal_and_result(f, vg="vg1", vr="vr1", status="proved", symbol="capture", prop="idempotent",
                     model="capture_model", label="verify idempotency")
    cli(f, "residual", "add", str(f), "--kind", "limitation", "--severity", "high",
        "--statement", "Concurrent capture is not modelled.",
        "--suggested-check", "Add a concurrency model.", "--introduced-by", "1")
    cli(f, "complete", str(f), "--summary", "capture proved idempotent; concurrency out of scope")

    report = cli(f, "report", str(f), expect=None)
    assert "Traceback" not in report
    # A report that omits the negative space is the failure mode this whole format exists to prevent.
    assert "concurrent" in report.lower(), f"the report must carry the gap:\n{report}"
    # And it must not claim more than the record holds.
    assert "refuted" not in report.lower()


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# STORY 11  "The function the proof was about is gone."
# ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_story_a_proof_detaches_when_its_symbol_is_deleted(trace):
    # Distinct from STALE. Stale means the code the proof was about CHANGED; detached means it is no
    # longer there at all, so there is nothing to re-run. A reader must be able to tell the two apart:
    # one is "re-verify", the other is "this evidence is about code that no longer exists".
    f = trace
    t = _read(f)
    t.setdefault("artifacts", []).append(
        {"artifact_id": "src.py", "artifact_type": "SourceCode", "name": "src.py"})
    _write(f, t)

    _model_rev(f, aid="m1", src="let fee x = x / 10\nlet legacy_capture p = fee p\n")
    _goal_and_result(f, vg="vg1", vr="vr1", status="proved", symbol="legacy_capture",
                     prop="idempotent", model="m1", label="verify the legacy path")

    out = cli(f, "residuals", str(f), "--derived")
    assert "detached" not in out.lower()

    # The function is deleted in a later revision of the SAME model.
    _model_rev(f, aid="m2", src="let fee x = x / 10\n", label="drop the legacy capture path")

    out = cli(f, "residuals", str(f), "--derived")
    assert "detached" in out.lower(), f"evidence about deleted code must read as detached:\n{out}"
    assert "stale" not in out.lower(), "detached is not stale - there is nothing to re-run"


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# STORY 12  "What do we already know about this function?"
# ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_story_the_record_answers_questions_about_a_symbol(trace):
    # The point of a record is that the next person - or the next turn - can CONSULT it instead of
    # working the answer out again. If the index and the detail disagree, consulting it is worse than
    # not having it.
    f = trace
    t = _read(f)
    t.setdefault("artifacts", []).append(
        {"artifact_id": "src.py", "artifact_type": "SourceCode", "name": "src.py"})
    _write(f, t)
    _model_rev(f, aid="m1", src="let fee x = x / 10\nlet capture p = fee p\n")
    _goal_and_result(f, vg="vg1", vr="vr1", status="proved", symbol="capture", prop="idempotent",
                     model="m1", label="verify idempotency")
    cli(f, "residual", "add", str(f), "--kind", "limitation", "--severity", "high",
        "--statement", "Concurrent capture is not modelled.",
        "--suggested-check", "Add a concurrency model.", "--introduced-by", "1",
        "--target-type", "artifact", "--target-id", "vr1")

    index = cli(f, "symbols", str(f))
    assert "capture" in index, index
    assert "proved" in index, index
    assert "gap" in index.lower(), f"the index must admit the gap, not just the proof:\n{index}"

    detail = cli(f, "symbol", str(f), "capture")
    assert "Traceback" not in detail
    assert "Concurrent capture is not modelled" in detail, \
        f"the detail must name the gap the index counted:\n{detail}"

    # And the two must agree about freshness. A change under the proof moves BOTH or neither.
    _model_rev(f, aid="m2", src="let fee x = x / 5\nlet capture p = fee p\n", label="fee change")
    index2 = cli(f, "symbols", str(f))
    detail2 = cli(f, "symbol", str(f), "capture")
    stale_in_index = "out of date" in index2.lower() or "stale" in index2.lower()
    stale_in_detail = "out of date" in detail2.lower() or "stale" in detail2.lower()
    assert stale_in_index == stale_in_detail, \
        f"index and detail disagree about freshness:\n--- index ---\n{index2}\n--- detail ---\n{detail2}"
    assert stale_in_index, f"a proof over changed code must read as out of date:\n{index2}"


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# STORY 13  "Two people worked on it. Combine the records."
# ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_story_merging_two_branches_flags_what_must_be_re_reasoned(trace, tmp_path):
    f = trace
    t = _read(f)
    t.setdefault("artifacts", []).append(
        {"artifact_id": "src.py", "artifact_type": "SourceCode", "name": "src.py"})
    _write(f, t)
    _model_rev(f, aid="m1", src="let fee x = x / 10\nlet capture p = fee p\n")
    _goal_and_result(f, vg="vg1", vr="vr1", status="proved", symbol="capture", prop="idempotent",
                     model="m1", label="verify idempotency")
    cli(f, "complete", str(f), "--summary", "capture proved idempotent")

    # A colleague changed the fee function on their branch. Their record is honest about their work;
    # the question the merge has to answer is what it does to OURS.
    theirs = tmp_path / "theirs.json"
    theirs.write_text(f.read_text())
    _model_rev(theirs, aid="m2", src="let fee x = x / 5\nlet capture p = fee p\n",
               label="change the fee basis")

    report = json.loads(cli(f, "merge", str(f), str(theirs)))
    # The merge has to say WHAT it disturbed and WHY, not just that something changed.
    assert "fee" in report["delta"]["changed"], report["delta"]
    assert "capture" in report["delta"]["changed"], "the proved symbol is in the closure of the change"
    rer = report["rereason"]
    assert rer, f"a proof over a changed dependency must be flagged for re-reasoning:\n{report}"
    assert any("capture" in r["statement"] for r in rer), rer
    assert not report["carried_forward"], "nothing may be carried forward over a disturbed closure"

    # The materialized merge is a real record: it validates, and it is honest about what it inherited.
    merged = tmp_path / "merged.json"
    cli(f, "merge", str(f), str(theirs), "--combine", "-o", str(merged))
    assert merged.exists()
    assert "Valid trace" in cli(merged, "validate", str(merged))

    surface = cli(merged, "residuals", str(merged), "--derived")
    assert "needs_rereasoning" in surface, f"the merge's own finding must be in the record:\n{surface}"
    assert "stale_evidence" in surface, f"and so must the staleness it implies:\n{surface}"
    assert "Re-run it against the current capture" in surface, "with what to do about it"

    # And the to-do list says the same thing the surface does.
    nxt = cli(merged, "next", str(merged))
    assert "Traceback" not in nxt
    assert "re-run" in nxt.lower() or "out of date" in nxt.lower() or "capture" in nxt.lower(), \
        f"the merge's finding must reach the to-do list:\n{nxt}"


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# BINDINGS: "this code implements that published spec"
#
# A binding is a claim of a different kind from a proof. A proof says the code has a property; a
# binding says the code implements SOMEONE ELSE'S model, pinned at a version. That makes its evidence
# go out of date for a reason the closure machinery cannot see: not because the code moved, but
# because the catalogue did.
# ─────────────────────────────────────────────────────────────────────────────────────────────────

REF = "ref:gallery:stripe/refunds@2024-06-20"


def _bind(f, *, ref=REF, version="2024-06-20", checksum="c1"):
    """Declare the binding: the catalogue entry this repo claims to implement, at a pinned version."""
    t = _read(f)
    t.setdefault("reference_artifacts", []).append({
        "reference_artifact_id": ref, "name": "Stripe refunds", "domain": "payments",
        "artifact_type": "RefFormalModel", "version": version, "payload": {"checksum": checksum}})
    _write(f, t)


def _conformance(f, *, aid, ref=REF, status="passed", version="2024-06-20", checksum="c1",
                 target="can_refund", entry="refund_allowed"):
    """What a conformance oracle deposits: the verdict AND what it saw of the reference."""
    t = _read(f)
    nid = max([a["id"] for a in t.get("actions") or []] or [0]) + 1
    t.setdefault("actions", []).append({
        "id": nid, "type": "ConformanceCheck", "category": "reasoning",
        "rationale": f"check {target} against {ref}", "inputs": [ref], "outputs": [aid]})
    t.setdefault("artifacts", []).append({
        "artifact_id": aid, "artifact_type": "ConformanceResult", "name": aid,
        "producer_action_id": nid, "derived_from": [ref],
        "payload": {"reference_artifact_id": ref, "target_symbol": target, "entry_symbol": entry,
                    "status": status, "evidence_strength": "tests",
                    "reference_version": version, "reference_checksum": checksum,
                    "oracle": {"id": "codelogician", "oracle_type": "tester",
                               "evidence_strength": "tests"}}})
    _write(f, t)
    return nid


def _reference_goal(f, ref=REF):
    """A binding criterion is TYPED - it names the evidence artifact AND the reference it must be
    judged against. `goal accept` only authors the untyped kind, so the real path is `goal set --json`."""
    goal = {"id": "g", "intent": "the refund path implements the Stripe model", "scope": [],
            "status": "active",
            "acceptance": [{"id": "s1", "kind": "conformance", "required": True,
                            "label": f"the refund path conforms to {ref}",
                            "evidence": {"artifact": "ConformanceResult"}, "reference": ref,
                            "binding": {}}]}
    p = f.parent / "goal.json"
    p.write_text(json.dumps(goal))
    cli(f, "goal", "set", str(f), "--id", "g", "--json", str(p))


# STORY 14  "We claim this code implements the Stripe refunds spec."

def test_story_a_binding_is_met_only_by_evidence_against_that_reference(trace):
    f = trace
    _bind(f)
    _reference_goal(f)

    assert "0%" in cli(f, "resolve", str(f)), "an unbacked binding claim is not met"
    nxt = cli(f, "next", str(f))
    assert REF in nxt, f"the reader must be told which reference is unbacked:\n{nxt}"

    # A conformance check against a DIFFERENT entry does not satisfy this binding.
    _conformance(f, aid="cf_other", ref="ref:gallery:stripe/disputes@2024-06-20")
    assert "0%" in cli(f, "resolve", str(f)), \
        "conformance to another entry must not satisfy this binding"

    # The real check does.
    _conformance(f, aid="cf1")
    assert "100%" in cli(f, "resolve", str(f))

    # And a FAILED check does not - a result that exists but says no is not evidence for yes.
    g = tmp = None  # noqa: F841  (kept explicit: the failing case gets its own record below)


def test_story_a_failed_conformance_does_not_satisfy_a_binding(trace):
    f = trace
    _bind(f)
    _reference_goal(f)
    _conformance(f, aid="cf1", status="failed")
    out = cli(f, "resolve", str(f))
    assert "100%" not in out, f"a failing conformance must not read as met:\n{out}"


# STORY 15  "The spec we bound to published a new version."

def test_story_the_catalogue_moves_under_a_binding(trace):
    f = trace
    _bind(f)
    _reference_goal(f)
    _conformance(f, aid="cf1")
    assert "100%" in cli(f, "resolve", str(f))
    assert "Nothing to do" in cli(f, "next", str(f))

    # Stripe publishes a new version of the entry. The CODE did not move; the model did - which the
    # dependency-closure machinery cannot see, because it only watches our own source.
    t = _read(f)
    t["reference_artifacts"][0]["version"] = "2025-01-15"
    t["reference_artifacts"][0]["payload"]["checksum"] = "c2"
    _write(f, t)

    surface = cli(f, "residuals", str(f), "--derived")
    assert "out of date" in surface.lower() or "stale" in surface.lower(), \
        f"a binding judged against a moved model must go out of date:\n{surface}"
    assert "2024-06-20" in surface and "2025-01-15" in surface, \
        f"the reader must see WHICH way the model moved:\n{surface}"

    nxt = cli(f, "next", str(f))
    assert "Nothing to do" not in nxt, f"a binding gone out of date is work:\n{nxt}"
    assert "Re-establish conformance" in nxt or REF in nxt, nxt

    # Re-checking against the new version heals it.
    _conformance(f, aid="cf2", version="2025-01-15", checksum="c2")
    surface = cli(f, "residuals", str(f), "--derived")
    assert "out of date" not in surface.lower(), f"a re-check must heal the guard:\n{surface}"
    assert "100%" in cli(f, "resolve", str(f))


# STORY 16  "Someone removed the binding."

def test_story_a_removed_binding_detaches_its_evidence(trace):
    f = trace
    _bind(f)
    _conformance(f, aid="cf1")
    assert "detached" not in cli(f, "residuals", str(f), "--derived").lower()

    # The binding is dropped from the record. The conformance result is now a claim about nothing.
    t = _read(f)
    t["reference_artifacts"] = []
    _write(f, t)

    surface = cli(f, "residuals", str(f), "--derived")
    assert "detached" in surface.lower(), \
        f"evidence whose reference is gone must read as detached:\n{surface}"
    assert "Restore the reference" in surface or "retire the evidence" in surface, \
        f"and say what to do about it:\n{surface}"

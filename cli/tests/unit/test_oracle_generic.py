"""ORACLE_SPEC v0.2 — the oracle as a GENERIC type: an open mechanism set, per-result attribution, the
evidence fingerprint + probe (freshness for any oracle's evidence), the Observation artifact, the
evidence predicates in policies, graded resolution in enrich, and strength-aware merge.

The load-bearing instance is the reference-data store: a DATABASE is an oracle, on equal footing with
the ImandraX reasoner, graded `attested` and never higher, and its evidence goes stale when the source
republishes — not when code changes."""
import datetime as dt
import sqlite3

import pytest

from ponens import oracles as oc
from ponens import goals as goalops
from ponens import trace as traceops
from ponens import policy_compiler as pc
from ponens import merge as mergeops
from ponens.sdk import Session


# ---------------------------------------------------------------- taxonomy: open set, fixed strength

def test_monitor_is_a_standard_type_and_the_set_is_open():
    assert "monitor" in oc.ORACLE_TYPES
    assert oc.check_oracle_type("monitor") is None
    # A non-standard name is admissible — a WARNING, never a rejection — and silent when it specializes.
    w = oc.check_oracle_type("datasource")
    assert w and "non-standard" in w
    assert oc.check_oracle_type("datasource", specializes="monitor") is None
    assert oc.check_oracle_type(None) == "missing oracle_type"


def test_strength_order_is_locked_and_at_least_is_false_for_unranked():
    assert oc.EVIDENCE_STRENGTH == ("proof", "sat", "tests", "static_analysis", "attested")
    assert oc.strength_at_least("proof", "tests")
    assert oc.strength_at_least("tests", "tests")
    assert not oc.strength_at_least("attested", "tests")
    assert not oc.strength_at_least(None, "attested")       # unranked never satisfies a minimum


def test_action_type_follows_the_mechanism():
    assert oc.action_type_for("reasoner") == "Verify"
    assert oc.action_type_for("monitor") == "Observe"
    assert oc.action_type_for("datasource", specializes="monitor") == "Observe"
    assert oc.action_type_for("whatever") == "Verify"        # a producer that cannot distinguish


# ---------------------------------------------------------------- attribution (§3)

def test_attribution_is_derived_from_engine_on_pre_1_12_payloads():
    att = oc.attribution_of({"status": "proved", "engine": "imandrax", "engine_version": "1.4",
                             "evidence_strength": "proof"})
    assert att == {"id": "imandrax", "oracle_type": "reasoner", "version": "1.4", "evidence_strength": "proof"}
    assert oc.attribution_of({"status": "proved"}) is None
    assert oc.strength_of({"oracle": {"id": "x", "oracle_type": "judge", "evidence_strength": "attested"}}) == "attested"
    assert oc.strength_of({"oracle": {"id": "x", "oracle_type": "judge", "evidence_strength": "bogus"}}) is None


def test_codelogician_oracle_stamps_attribution_and_generic_fingerprint():
    fake = lambda target, context=None: {"status": "proved", "engine": "imandrax", "engine_version": "1.4",
                                         "result": "ok", "reasoning_fingerprint": "abc123"}
    art = oc.CodeLogicianOracle(runner=fake, version="1.4").invoke({"iml_code": "let f x = x", "target_symbol": "f"})[0]
    p = art["payload"]
    assert p["oracle"] == {"id": "codelogician", "oracle_type": "reasoner", "engine": "imandrax", "evidence_strength": "proof", "version": "1.4"}
    fp = oc.fingerprint_of(p)
    assert fp["subject_checksum"] == "abc123" and fp["subject_ref"] == "f" and fp["oracle_id"] == "codelogician"
    # The reasoner profile names ride along for pre-1.12 consumers.
    assert p["fingerprint"]["task_checksum"] == "abc123" and p["fingerprint"]["target_symbol"] == "f"


def test_honesty_rule_no_strength_on_unknown_and_never_stronger_than_capability():
    art = oc.CodeLogicianOracle(runner=lambda t, c=None: {"status": "unknown"}).invoke({"goal": "g"})[0]
    assert "evidence_strength" not in art["payload"]["oracle"]
    with pytest.raises(ValueError):
        oc.AttestorOracle().attribution("proof")             # an attestor cannot grade a result `proof`


# ---------------------------------------------------------------- the database as an oracle (§5, §8)

def _calendar(mapping=None, **kw):
    rows = mapping if mapping is not None else {"holidays-2026": ["2026-12-25", "2026-12-26"]}
    return oc.ReferenceDataOracle.from_mapping("calendar-db", "calendar", rows, version="schema-7", **kw), rows


def test_reference_data_oracle_produces_an_attested_observation_with_a_fingerprint():
    o, _ = _calendar()
    art = o.invoke({"query": "holidays-2026", "statement": "TARGET holidays for 2026", "valid_until": "2026-12-31T23:59:59Z"})[0]
    assert art["artifact_type"] == "Observation" and art["artifact_role"] == "AuditEvidenceRole"
    p = art["payload"]
    assert p["statement"] == "TARGET holidays for 2026" and p["source"] == "calendar" and p["query"] == "holidays-2026"
    assert p["value"] == ["2026-12-25", "2026-12-26"] and p["observed_at"]
    assert p["oracle"] == {"id": "calendar-db", "oracle_type": "monitor", "evidence_strength": "attested", "version": "schema-7"}
    fp = p["fingerprint"]
    assert fp["subject_checksum"].startswith("sha256:") and fp["subject_ref"].startswith("calendar:")
    assert fp["valid_until"] == "2026-12-31T23:59:59Z" and fp["oracle_id"] == "calendar-db"


def test_observation_goes_stale_when_the_source_republishes_not_when_code_changes():
    o, rows = _calendar()
    p = o.invoke({"query": "holidays-2026"})[0]["payload"]
    ref = p["fingerprint"]["subject_ref"]
    assert oc.freshness_of(p, current=o.probe(ref)) == oc.FRESH
    rows["holidays-2026"] = ["2026-12-25"]                   # the calendar is republished
    assert oc.freshness_of(p, current=o.probe(ref)) == oc.STALE
    del rows["holidays-2026"]                                 # the subject is gone
    assert o.probe(ref) == {"detached": True}
    assert oc.freshness_of(p, current=o.probe(ref)) == oc.DETACHED


def test_freshness_rule_unknown_valid_until_and_version():
    o, _ = _calendar()
    p = o.invoke({"query": "holidays-2026", "valid_until": "2026-12-31T23:59:59Z"})[0]["payload"]
    # No current fingerprint: time-boxed validity decides.
    assert oc.freshness_of(p, current=None, now="2026-09-11T00:00:00Z") == oc.FRESH
    assert oc.freshness_of(p, current=None, now="2027-01-01T00:00:00Z") == oc.STALE
    # No current fingerprint and no validity: Unknown — neither fresh nor stale.
    q = o.invoke({"query": "holidays-2026"})[0]["payload"]
    assert oc.freshness_of(q, current=None) == oc.UNKNOWN
    # An advanced oracle version obsoletes even an exact checksum match.
    cur = dict(q["fingerprint"], oracle_version="schema-8")
    assert oc.freshness_of(q, current=cur) == oc.STALE
    # Payloads without any fingerprint are not decided here.
    assert oc.freshness_of({"status": "proved"}, current=None) == oc.UNKNOWN


def test_reference_data_oracle_over_sqlite(tmp_path):
    db = tmp_path / "ref.sqlite"
    con = sqlite3.connect(db)
    con.execute("create table holidays(cal text, day text)")
    con.execute("insert into holidays values ('TARGET','2026-12-25')")
    con.commit(); con.close()
    o = oc.ReferenceDataOracle.from_sqlite("calendar-db", str(db), source="calendar")
    sql = "select day from holidays where cal='TARGET' order by day"
    p = o.invoke({"query": sql})[0]["payload"]
    assert p["value"] == [{"day": "2026-12-25"}]
    ref = p["fingerprint"]["subject_ref"]
    assert oc.freshness_of(p, current=o.probe(ref)) == oc.FRESH
    con = sqlite3.connect(db); con.execute("insert into holidays values ('TARGET','2026-12-26')"); con.commit(); con.close()
    assert oc.freshness_of(p, current=o.probe(ref)) == oc.STALE
    con = sqlite3.connect(db); con.execute("drop table holidays"); con.commit(); con.close()
    assert oc.freshness_of(p, current=o.probe(ref)) == oc.DETACHED
    # A query the store cannot answer yields an unranked, unestablished observation (honesty rule).
    bad = o.invoke({"query": "select * from nope"})[0]["payload"]
    assert bad["status"] == "unknown" and "evidence_strength" not in bad["oracle"]


# ---------------------------------------------------------------- the rest of the spectrum (§8)

def test_tester_judge_and_attestor_reference_oracles():
    t = oc.SubprocessTesterOracle(runner=lambda cmd, cwd=None, timeout=None: {"exit_code": 0, "stdout": "1 passed"})
    art = t.invoke({"command": ["pytest", "-q"], "subject_ref": "tests/test_x.py"})[0]
    assert art["artifact_type"] == "CommandResult" and art["payload"]["status"] == "passed"
    assert art["payload"]["oracle"]["evidence_strength"] == "tests"
    assert art["payload"]["fingerprint"]["subject_ref"] == "tests/test_x.py"
    failing = oc.SubprocessTesterOracle(runner=lambda cmd, cwd=None, timeout=None: {"exit_code": 1}).invoke("pytest")[0]
    assert failing["payload"]["status"] == "failed" and failing["payload"]["oracle"]["evidence_strength"] == "tests"
    errored = oc.SubprocessTesterOracle(runner=lambda *a, **k: (_ for _ in ()).throw(OSError("no such runner"))).invoke("x")[0]
    assert errored["payload"]["status"] == "error" and "evidence_strength" not in errored["payload"]["oracle"]

    j = oc.CallableJudgeOracle("llm-judge", lambda t: {"verdict": "acceptable", "score": 0.8, "note": "fine"})
    note = j.invoke({"content": "def f(): pass", "rubric": "readable"})[0]
    assert note["artifact_type"] == "AnalysisNote" and note["payload"]["oracle"]["oracle_type"] == "judge"
    assert note["payload"]["oracle"]["evidence_strength"] == "attested" and note["payload"]["score"] == 0.8

    a = oc.AttestorOracle(signer="reviewer@example.com").invoke({"claim_ref": "a3-result-1", "role": "auditor"})[0]
    assert a["artifact_type"] == "UserApproval" and a["payload"]["disposition"] == "approved"
    assert a["payload"]["oracle"] == {"id": "attestor", "oracle_type": "attestor", "evidence_strength": "attested"}


def test_registry_lists_the_spectrum_and_filters_by_type():
    ids = {o.id for o in oc.list_oracles()}
    assert {"codelogician", "subprocess-tester", "attestor"} <= ids
    assert [o.id for o in oc.list_oracles("tester")] == ["subprocess-tester"]
    o, _ = _calendar()
    oc.register_oracle(o)
    try:
        assert "calendar-db" in {x.id for x in oc.list_oracles("monitor")}
        assert oc.get_oracle("calendar-db").can_probe and not oc.get_oracle("attestor").can_probe
    finally:
        oc.unregister_oracle("calendar-db")


# ---------------------------------------------------------------- SDK: typed actions, probe, freshness

def test_sdk_records_an_observe_action_for_a_monitor_and_can_probe_it():
    o, rows = _calendar()
    with Session(model="m", assistant="t") as s:
        model = s.artifact("IMLModel", name="model", payload={"formal_code": "let settle d = d"})
        [obs] = s.observe({"query": "holidays-2026"}, oracle=o, derived_from=model)
        act = next(a for a in s.trace["actions"] if obs in a["outputs"])
        assert act["type"] == "Observe" and act["category"] == "reasoning"
        assert s.freshness(obs) == oc.FRESH
        rows["holidays-2026"] = []
        assert s.freshness(obs) == oc.STALE
        errs, _w = traceops.validate_trace(s.trace)
        assert errs == []


# ---------------------------------------------------------------- validate: open type, fixed strength

def test_validate_warns_on_non_standard_type_and_errors_on_bad_strength():
    t = traceops.create_empty_trace(model="m", assistant="t")
    t["artifacts"] = [
        {"artifact_id": "o1", "artifact_type": "Observation", "derived_from": [],
         "payload": {"statement": "x", "source": "db", "observed_at": "2026-01-01T00:00:00Z",
                     "oracle": {"id": "db", "oracle_type": "datasource", "evidence_strength": "attested"}}},
        {"artifact_id": "v1", "artifact_type": "VerificationResult", "derived_from": [],
         "payload": {"status": "proved", "oracle": {"id": "x", "oracle_type": "reasoner", "evidence_strength": "huge"}}},
        {"artifact_id": "u1", "artifact_type": "VerificationResult", "derived_from": [],
         "payload": {"status": "unknown", "oracle": {"id": "x", "oracle_type": "reasoner", "evidence_strength": "proof"}}},
        {"artifact_id": "o2", "artifact_type": "Observation", "derived_from": [],
         "payload": {"statement": "x", "source": "db", "oracle": {"id": "db", "oracle_type": "monitor", "evidence_strength": "proof"}}},
    ]
    errors, warnings = traceops.validate_trace(t)
    assert any("o1" in w and "non-standard oracle_type 'datasource'" in w for w in warnings)
    assert any("v1" in e and "invalid evidence_strength 'huge'" in e for e in errors)
    assert any("u1" in w and "honesty rule" in w for w in warnings)
    assert any("o2" in e and "never higher" in e for e in errors)
    assert not any("o1" in e for e in errors)                 # an unknown mechanism name is NOT an error


# ---------------------------------------------------------------- policies: the evidence predicates (§6)

def _trace_with(art_payload, art_type="Observation", action_type="Observe"):
    t = traceops.create_empty_trace(model="m", assistant="t")
    t["actions"] = [{"id": 1, "type": action_type, "category": "reasoning", "rationale": "r", "inputs": [], "outputs": ["e1"]}]
    t["artifacts"] = [{"artifact_id": "e1", "artifact_type": art_type, "derived_from": [], "producer_action_id": 1,
                       "payload": art_payload}]
    t["outcome"] = {"type": "ProcessCompleted"}
    return t


def _holds(formula, t):
    _name, node, _level = pc.compile_policy({"policy_id": "p", "name": "p", "formula": formula})
    return traceops.evaluate_formula(node, t)


def test_evidence_predicates_evaluate_over_the_attribution_block():
    obs = {"statement": "x", "source": "calendar", "observed_at": "2026-01-01T00:00:00Z",
           "oracle": {"id": "calendar-db", "oracle_type": "monitor", "evidence_strength": "attested"}}
    t = _trace_with(obs)
    assert _holds("G(Observation -> oracle_type(monitor))", t)
    assert _holds("G(Observation -> produced_by(calendar-db))", t)       # hyphenated ids parse
    assert _holds("G(Observation -> strength_at_least(attested))", t)
    assert not _holds("G(Observation -> strength_at_least(tests))", t)
    assert not _holds("G(Observation -> oracle_type(reasoner))", t)
    # A specialization refines its standard name.
    t2 = _trace_with(dict(obs, oracle={"id": "db", "oracle_type": "datasource", "specializes": "monitor",
                                       "evidence_strength": "attested"}))
    assert _holds("G(Observation -> oracle_type(monitor))", t2)
    # Pre-1.12 payloads: attribution derived from `engine`.
    t3 = _trace_with({"status": "proved", "engine": "imandrax", "evidence_strength": "proof"},
                     art_type="VerificationResult", action_type="Verify")
    assert _holds("G(VerificationResult -> strength_at_least(proof) && oracle_type(reasoner) && produced_by(imandrax))", t3)
    # A result with no strength never satisfies a minimum.
    t4 = _trace_with({"status": "unknown", "engine": "imandrax"}, art_type="VerificationResult", action_type="Verify")
    assert not _holds("G(VerificationResult -> strength_at_least(attested))", t4)


def test_evidence_predicates_pass_the_policy_linter():
    ok = pc.check_all_policies([{"policy_id": "p", "name": "p", "severity": "warning", "scope": "trace",
                                 "kind": "trace_invariant",
                                 "formula": "G(Observation -> oracle_type(monitor) && strength_at_least(attested))"}])
    assert ok


# ---------------------------------------------------------------- enrich: graded, fresh-or-not resolution

def _proof_and_observation_trace(o):
    t = traceops.create_empty_trace(model="m", assistant="t")
    t["actions"] = [
        {"id": 1, "type": "Formalize", "category": "reasoning", "rationale": "r", "inputs": [], "outputs": ["m1"]},
        {"id": 2, "type": "Verify", "category": "reasoning", "rationale": "r", "inputs": ["m1"], "outputs": ["g1", "v1"]},
        {"id": 3, "type": "Observe", "category": "reasoning", "rationale": "r", "inputs": ["m1"], "outputs": []},
    ]
    obs = o.invoke({"query": "holidays-2026", "statement": "calendar matches", "target_symbol": "settle"})[0]
    obs.update({"artifact_id": "o1", "derived_from": ["m1"], "producer_action_id": 3})
    t["actions"][2]["outputs"] = ["o1"]
    t["artifacts"] = [
        {"artifact_id": "m1", "artifact_type": "IMLModel", "derived_from": [],
         "producer_action_id": 1, "payload": {"formal_code": "let settle d = d\n", "symbols": ["settle"]}},
        {"artifact_id": "g1", "artifact_type": "VerificationGoal", "derived_from": ["m1"], "producer_action_id": 2,
         "payload": {"goal_id": 1, "target_symbol": "settle", "description": "settle never books on a holiday"}},
        {"artifact_id": "v1", "artifact_type": "VerificationResult", "derived_from": ["g1"], "producer_action_id": 2,
         "payload": {"goal_id": 1, "goal_artifact_id": "g1", "status": "proved", "engine": "imandrax",
                     "evidence_strength": "proof"}},
        obs,
    ]
    t["goals"] = [{"id": "goal-1", "intent": "settle is safe against the official calendar", "scope": ["settle"],
                   "acceptance": [
                       {"id": "s1", "component": {"function": "settle"}, "evidence": {"artifact": "VerificationResult"}, "required": True},
                       {"id": "s2", "component": {"function": "settle"}, "evidence": {"artifact": "Observation"}, "required": True},
                   ]}]
    t["outcome"] = {"type": "ProcessCompleted"}
    return t


def test_enrich_reports_strength_freshness_and_the_weakest_link():
    o, rows = _calendar()
    t = _proof_and_observation_trace(o)
    oc.register_oracle(o)
    try:
        e = goalops.enrich(t)
        g = e["goals"][0]
        by_id = {it["id"]: it for it in g["acceptance"]}
        assert by_id["s1"]["status"] == "done" and by_id["s1"]["evidence_strength"] == "proof"
        assert by_id["s2"]["status"] == "done" and by_id["s2"]["evidence_strength"] == "attested"
        assert by_id["s2"]["freshness"] == "fresh"
        assert g["min_strength"] == "attested"                # met, but only as strong as its weakest leg
        assert g["faithfulness"]["met"] is True

        rows["holidays-2026"] = ["2026-12-25"]                 # the calendar is republished
        e2 = goalops.enrich(t)
        s2 = next(it for it in e2["goals"][0]["acceptance"] if it["id"] == "s2")
        assert s2["freshness"] == "stale" and s2["at_risk"] is True
        assert any(r["residual_id"] == "stale-o1" and r["derived"] for r in e2["residuals"])
        s1 = next(it for it in e2["goals"][0]["acceptance"] if it["id"] == "s1")
        assert "at_risk" not in s1                             # the proof itself is untouched
    finally:
        oc.unregister_oracle("calendar-db")


def test_enrich_reports_unknown_freshness_when_the_oracle_is_not_registered():
    o, _ = _calendar()
    t = _proof_and_observation_trace(o)                      # calendar-db NOT registered: cannot probe
    e = goalops.enrich(t)
    s2 = next(it for it in e["goals"][0]["acceptance"] if it["id"] == "s2")
    assert s2["status"] == "done" and s2["freshness"] == "unknown" and s2.get("freshness_note")
    assert not any(r["residual_id"] == "stale-o1" for r in e["residuals"])


# ---------------------------------------------------------------- merge: prefer the stronger result (§6)

def _standing(trace_id, strength, step, src="let f x = x + 1\n"):
    t = traceops.create_empty_trace(model="m", assistant="t")
    t["trace_id"] = trace_id
    t["actions"] = [{"id": i, "type": ty, "category": "reasoning", "rationale": "r", "inputs": [], "outputs": []}
                    for i, ty in ((1, "Formalize"), (step, "Verify"))]
    t["artifacts"] = [
        {"artifact_id": "m1", "artifact_type": "IMLModel", "derived_from": [], "producer_action_id": 1,
         "payload": {"formal_code": src}},
        {"artifact_id": f"g-{trace_id}", "artifact_type": "VerificationGoal", "derived_from": ["m1"], "producer_action_id": step,
         "payload": {"goal_id": 1, "target_symbol": "f", "description": "f grows"}},
        {"artifact_id": f"v-{trace_id}", "artifact_type": "VerificationResult", "derived_from": [f"g-{trace_id}"],
         "producer_action_id": step,
         "payload": {"goal_id": 1, "goal_artifact_id": f"g-{trace_id}", "status": "sat" if strength == "sat" else "proved",
                     "engine": "imandrax", "evidence_strength": strength}},
    ]
    t["outcome"] = {"type": "ProcessCompleted"}
    return t


def test_merge_prefers_the_stronger_standing_result_and_carries_it_in_combine():
    ours = _standing("ours", "sat", step=2)
    theirs = _standing("theirs", "proof", step=2)
    report = mergeops.merge(ours, theirs)
    [c] = report["carried_forward"]
    assert c["strength"] == "sat" and c["theirs_strength"] == "proof" and c["preferred"] == "theirs"
    merged = mergeops.combine(ours, theirs)
    cf = next(a for a in merged["artifacts"] if a["artifact_type"] == "CarriedForward")
    assert cf["payload"]["preferred_result_id"] == "v-theirs" and "v-theirs" in cf["derived_from"]
    assert any(a["artifact_id"] == "v-theirs" for a in merged["artifacts"])
    # Equal strength: the later result wins; ours when it is at least as late.
    same = mergeops.merge(_standing("ours", "proof", step=5), _standing("theirs", "proof", step=2))
    assert same["carried_forward"][0]["preferred"] == "ours"


# ---------------------------------------------------------------- the `oracle` / `reasoner` field is enforced

def _vr_trace(oracle_block=None, engine=None, action_type="Verify"):
    t = traceops.create_empty_trace(model="m", assistant="t")
    payload = {"status": "proved"}
    if engine:
        payload["engine"] = engine
    if oracle_block:
        payload["oracle"] = oracle_block
    t["actions"] = [
        {"id": 1, "type": "Formalize", "category": "reasoning", "rationale": "r", "inputs": [], "outputs": ["m1"]},
        {"id": 2, "type": action_type, "category": "reasoning", "rationale": "r", "inputs": ["m1"], "outputs": ["v1"]},
    ]
    t["artifacts"] = [
        {"artifact_id": "m1", "artifact_type": "IMLModel", "derived_from": [], "producer_action_id": 1, "payload": {}},
        {"artifact_id": "v1", "artifact_type": "VerificationResult", "derived_from": ["m1"], "producer_action_id": 2, "payload": payload},
    ]
    t["outcome"] = {"type": "ProcessCompleted"}
    return t


def test_oracle_field_desugars_into_the_formula():
    p = {"policy_id": "p", "name": "formalize_before_verify_x", "reasoner": "codelogician", "formula": "G(Verify -> P(Formalize))"}
    assert pc.effective_formula(p) == "(G(Verify -> P(Formalize))) && G(Verify -> (produced_by(codelogician) || oracle_type(codelogician)))"
    # `oracle` is the 0.2 name; a formula naming no evidence atom is scoped to the reasoning result types.
    q = {"policy_id": "q", "name": "q", "oracle": "imandrax", "formula": "G(Formalize -> F(Commit))"}
    assert "G(VerificationResult -> (produced_by(imandrax) || oracle_type(imandrax)))" in pc.effective_formula(q)
    assert "G(ConformanceResult -> " in pc.effective_formula(q)
    # Absent field: identity.
    assert pc.effective_formula({"name": "n", "formula": "G(Verify -> P(Formalize))"}) == "G(Verify -> P(Formalize))"


def test_oracle_field_is_enforced_at_check_time():
    pol = {"policy_id": "p", "name": "p", "reasoner": "codelogician", "severity": "error",
           "formula": "G(Verify -> P(Formalize))"}
    cl = {"id": "codelogician", "oracle_type": "reasoner", "evidence_strength": "proof"}
    # A CodeLogician result: attributed to the oracle id, or only via the legacy `engine` it drives.
    assert traceops.evaluate_policy(pol, _vr_trace(oracle_block=cl, engine="imandrax"))[0] == "passed"
    assert traceops.evaluate_policy(pol, _vr_trace(engine="imandrax"))[0] == "passed"          # pre-1.12 payload
    assert traceops.evaluate_policy(dict(pol, reasoner="imandrax"), _vr_trace(oracle_block=cl, engine="imandrax"))[0] == "passed"
    # Another engine, or no attribution at all: the requirement is NOT met.
    lean = {"id": "lean", "oracle_type": "reasoner", "evidence_strength": "proof"}
    assert traceops.evaluate_policy(pol, _vr_trace(oracle_block=lean, engine="lean"))[0] == "failed"
    assert traceops.evaluate_policy(pol, _vr_trace())[0] == "failed"
    # The same trace passes the policy without the field — the field is what added the requirement.
    assert traceops.evaluate_policy({k: v for k, v in pol.items() if k != "reasoner"}, _vr_trace())[0] == "passed"
    # The field may name a MECHANISM instead of an id.
    assert traceops.evaluate_policy(dict(pol, reasoner="reasoner"), _vr_trace(oracle_block=lean))[0] == "passed"
    assert traceops.evaluate_policy(dict(pol, reasoner="monitor"), _vr_trace(oracle_block=lean))[0] == "failed"

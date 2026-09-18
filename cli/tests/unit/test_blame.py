"""`ponens trace blame` — evidence per symbol: best standing result, strength, freshness, residuals."""
from ponens import blame as bl
from ponens import trace as traceops
from ponens import oracles as oc


def _trace():
    t = traceops.create_empty_trace(model="m", assistant="t")
    t["actions"] = [{"id": i, "type": ty, "category": "reasoning", "rationale": "r", "inputs": [], "outputs": []}
                    for i, ty in ((1, "Formalize"), (2, "Verify"), (3, "Verify"), (4, "Observe"), (5, "Verify"))]
    t["artifacts"] = [
        {"artifact_id": "m1", "artifact_type": "IMLModel", "derived_from": [], "producer_action_id": 1,
         "payload": {"formal_code": "let helper x = x\nlet settle d = helper d\nlet refund a = a\n", "symbols": ["helper", "settle", "refund"]}},
        {"artifact_id": "g1", "artifact_type": "VerificationGoal", "derived_from": ["m1"], "producer_action_id": 2,
         "payload": {"goal_id": 1, "target_symbol": "settle", "description": "no holiday booking"}},
        {"artifact_id": "v1", "artifact_type": "VerificationResult", "derived_from": ["g1"], "producer_action_id": 2,
         "payload": {"goal_id": 1, "goal_artifact_id": "g1", "status": "sat", "engine": "imandrax", "evidence_strength": "sat"}},
        {"artifact_id": "v2", "artifact_type": "VerificationResult", "derived_from": ["g1"], "producer_action_id": 3,
         "payload": {"goal_id": 1, "goal_artifact_id": "g1", "status": "proved", "engine": "imandrax", "evidence_strength": "proof"}},
        {"artifact_id": "o1", "artifact_type": "Observation", "derived_from": ["m1"], "producer_action_id": 4,
         "payload": {"statement": "calendar ok", "source": "calendar", "observed_at": "2026-01-01T00:00:00Z", "status": "observed",
                     "target_symbol": "settle", "oracle": {"id": "calendar-db", "oracle_type": "monitor", "evidence_strength": "attested"},
                     "fingerprint": {"subject_checksum": "sha256:aa", "subject_ref": "calendar:q1", "oracle_id": "calendar-db"}}},
        {"artifact_id": "g2", "artifact_type": "VerificationGoal", "derived_from": ["m1"], "producer_action_id": 5,
         "payload": {"goal_id": 2, "target_symbol": "refund", "description": "never over-refunds"}},
        {"artifact_id": "v3", "artifact_type": "VerificationResult", "derived_from": ["g2"], "producer_action_id": 5,
         "payload": {"goal_id": 2, "goal_artifact_id": "g2", "status": "refuted", "engine": "imandrax", "evidence_strength": "proof",
                     "counterexample": "a = -1"}},
        {"artifact_id": "r1", "artifact_type": "Residual", "derived_from": ["v3"], "producer_action_id": 5,
         "payload": {"kind": "open_question", "severity": "medium", "status": "open", "statement": "negative amounts?"}},
    ]
    t["outcome"] = {"type": "ProcessCompleted"}
    return t


def test_best_evidence_is_the_strongest_fresh_result_per_symbol():
    b = bl.blame(_trace())
    assert set(b["symbols"]) == {"settle", "refund"}
    s = b["symbols"]["settle"]
    assert s["best"]["artifact_id"] == "v2" and s["best"]["strength"] == "proof" and s["best"]["freshness"] == "fresh"
    assert [r["artifact_id"] for r in s["results"]] == ["v2", "v1", "o1"]        # proof > sat > attested
    assert s["results"][2]["oracle"] == "calendar-db" and s["results"][2]["freshness"] == "unknown"  # not probe-able here
    r = b["symbols"]["refund"]
    assert r["best"]["status"] == "refuted" and r["best"]["counterexample"] == "a = -1"
    assert r["residuals"] == [{"residual_id": "r1", "kind": "open_question", "severity": "medium", "statement": "negative amounts?"}]
    assert b["unattributed"] == []


def test_stale_results_lose_to_fresh_ones_and_extension_freshness_is_honored():
    t = _trace()
    t["artifact_freshness"] = {"v2": "stale"}           # the extension's hash-based verdict, keyed by ref
    b = bl.blame(t)
    s = b["symbols"]["settle"]
    assert s["best"]["artifact_id"] == "v1"              # the fresh sat beats the stale proof
    assert next(r for r in s["results"] if r["artifact_id"] == "v2")["freshness"] == "stale"
    # A registered oracle makes the observation's freshness decidable.
    o = oc.ReferenceDataOracle.from_mapping("calendar-db", "calendar", {"q1": [1]})
    oc.register_oracle(o)
    try:
        o.invoke({"query": "q1"})                        # remembers the query for probe()
        # subject_ref must match the oracle's minted ref for the probe to find the query
        t["artifacts"][4]["payload"]["fingerprint"]["subject_ref"] = o.subject_ref("q1")
        t["artifacts"][4]["payload"]["fingerprint"]["subject_checksum"] = o._fingerprint("q1", [1], "x", None)["subject_checksum"]
        fresh = next(r for r in bl.blame(t)["symbols"]["settle"]["results"] if r["artifact_id"] == "o1")["freshness"]
        assert fresh == "fresh"
    finally:
        oc.unregister_oracle("calendar-db")


def test_render_is_one_line_per_symbol():
    out = bl.render(bl.blame(_trace()))
    assert "settle  proof           proved" in out.replace("  ", "  ")
    assert "refund" in out and "1 open gap" in out


def test_cli_registration_and_json(capsys):
    import argparse, json
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers()
    bl.register(sub)
    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
    json.dump(_trace(), open(path, "w"))
    args = parser.parse_args(["blame", path, "--json", "--symbol", "refund"])
    assert args.func(args) == 0
    out = json.loads(capsys.readouterr().out)
    assert list(out["symbols"]) == ["refund"]

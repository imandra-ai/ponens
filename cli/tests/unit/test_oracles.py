"""Oracles — the invocable evidence-producer abstraction (ORACLE_SPEC v0.1): the taxonomy, the
in-process registry, the CodeLogician oracle (driving codelogician-lite → ImandraX), and the
parsing of a real `check-vg --json` result into graded VerificationResults."""
from ponens import oracles as oc


def test_evidence_strength_is_a_total_order_strongest_first():
    assert oc.EVIDENCE_STRENGTH[0] == "proof"
    assert oc.strength_rank("proof") < oc.strength_rank("tests") < oc.strength_rank("attested")
    # Unknown strengths sort last (never beat a real one).
    assert oc.strength_rank("made-up") == len(oc.EVIDENCE_STRENGTH)


def test_reasoner_is_the_formal_subtype_of_oracle():
    assert "reasoner" in oc.ORACLE_TYPES
    assert oc.oracle_type_for_kind("formal_verification") == "reasoner"
    assert oc.oracle_type_for_kind("smt") == "reasoner"
    assert oc.oracle_type_for_kind(None) == "reasoner"  # default


def test_codelogician_oracle_is_registered_and_proof_strength():
    o = oc.get_oracle("codelogician")
    assert isinstance(o, oc.CodeLogicianOracle)
    assert o.oracle_type == "reasoner"
    assert o.evidence_strength == "proof"
    assert "VerificationResult" in o.produces
    assert any(x.id == "codelogician" for x in oc.list_oracles())


def test_invoke_proved_yields_proof_strength_result():
    # Inject a fake runner so the test is hermetic (no codelogician-lite needed).
    fake = lambda target, context=None: {
        "status": "proved", "engine": "imandrax",
        "result": "1 VG(s): proved", "reasoning_fingerprint": "abc123",
    }
    o = oc.CodeLogicianOracle(runner=fake)
    arts = o.invoke({"iml_code": "let f x = x + 1", "goal": "increases", "target_symbol": "f"})
    assert len(arts) == 1
    art = arts[0]
    assert art["artifact_type"] == "VerificationResult"
    assert art["artifact_role"] == "ProofRole"
    assert art["payload"]["status"] == "proved"
    assert art["payload"]["evidence_strength"] == "proof"  # graded from the verdict
    assert art["payload"]["target_symbol"] == "f"
    assert art["name"] == "verify:increases"


def test_invoke_refuted_carries_counterexample_and_is_definitive():
    fake = lambda target, context=None: {
        "status": "refuted", "engine": "imandrax", "result": "1 VG(s): refuted",
        "reasoning_fingerprint": "dead", "counterexample": "x = 0",
    }
    art = oc.CodeLogicianOracle(runner=fake).invoke({"iml_code": "...", "goal": "g"})[0]
    assert art["payload"]["status"] == "refuted"
    assert art["payload"]["evidence_strength"] == "proof"       # a counterexample is definitive
    assert art["payload"]["counterexample"] == "x = 0"
    assert art["artifact_role"] == "CounterexampleRole"


def test_invoke_unknown_is_not_labeled_with_a_strength():
    # Default runner with no iml_code / no tool -> unknown, and NO evidence_strength claim.
    art = oc.CodeLogicianOracle().invoke({"goal": "nothing to check"})[0]
    assert art["payload"]["status"] == "unknown"
    assert "evidence_strength" not in art["payload"]           # never overstate


def test_check_vg_json_parsing_against_the_real_schema():
    # Shapes taken verbatim from `codelogician-lite check-vg --json`.
    assert oc._eval_ok("Success") is True
    assert oc._eval_ok({"success": True}) is True
    assert oc._eval_ok({"success": False}) is False
    assert oc._verdict_of({"proved": {"proof_pp": "..."}, "refuted": None}) == "proved"
    assert oc._verdict_of({"refuted": {"model_str": "x=0"}, "proved": None}) == "refuted"
    assert oc._verdict_of({"verified_upto": {"depth": 5}}) == "sat"
    assert oc._verdict_of({"unknown": None, "proved": None}) == "unknown"
    assert oc._aggregate(["proved", "proved"]) == "proved"
    assert oc._aggregate(["proved", "refuted"]) == "refuted"
    assert oc._aggregate(["proved", "sat"]) == "sat"
    assert oc._aggregate([]) == "unknown"
    assert oc._counterexample({"refuted": {"model_str": "x = 0"}}) == "x = 0"

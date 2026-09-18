"""Bindings in the record (TRACE_SPEC §11.2–11.3): conformance evidence tied to a REFERENCE artifact —
the criterion resolves only against it, the evidence goes stale when the reference moves, the
`conforms_to` predicate selects it, and validation rejects a dangling reference id."""
import copy

from ponens import goals as goalops
from ponens import policy_compiler as pc
from ponens import trace as traceops

REF = "ref:atlas:mifir-rts22-art4@onshored · 2017/590"


def _trace(ref_version="onshored · 2017/590", checksum="c1", with_reference=True):
    t = traceops.create_empty_trace(model="m", assistant="t")
    t["actions"] = [
        {"id": 1, "type": "Formalize", "category": "reasoning", "rationale": "r", "inputs": [], "outputs": ["m1"]},
        {"id": 2, "type": "Verify", "category": "reasoning", "rationale": "some other property", "inputs": ["m1"], "outputs": ["g1", "v1"]},
        {"id": 3, "type": "Verify", "category": "reasoning", "rationale": "conformance", "inputs": [REF, "m1"], "outputs": ["c1"]},
    ]
    t["artifacts"] = [
        {"artifact_id": "m1", "artifact_type": "IMLModel", "derived_from": [], "producer_action_id": 1,
         "payload": {"formal_code": "let is_transmitted l = true\n", "symbols": ["is_transmitted"]}},
        {"artifact_id": "g1", "artifact_type": "VerificationGoal", "derived_from": ["m1"], "producer_action_id": 2,
         "payload": {"goal_id": 1, "target_symbol": "is_transmitted", "description": "terminates"}},
        {"artifact_id": "v1", "artifact_type": "VerificationResult", "derived_from": ["g1"], "producer_action_id": 2,
         "payload": {"goal_id": 1, "goal_artifact_id": "g1", "status": "proved", "engine": "imandrax", "evidence_strength": "proof"}},
        {"artifact_id": "c1", "artifact_type": "ConformanceResult", "derived_from": [REF, "m1"], "producer_action_id": 3,
         "payload": {"reference_artifact_id": REF, "target_artifact_id": "m1", "target_symbol": "is_transmitted",
                     "entry_symbol": "transmitted_strict", "status": "passed", "engine": "imandrax", "evidence_strength": "proof",
                     "oracle": {"id": "codelogician", "oracle_type": "reasoner", "evidence_strength": "proof"},
                     "reference_version": "onshored · 2017/590", "reference_checksum": "c1"}},
    ]
    if with_reference:
        t["reference_artifacts"] = [{"reference_artifact_id": REF, "name": "RTS 22 Art 4", "artifact_type": "RefFormalModel",
                                     "version": ref_version, "payload": {"checksum": checksum}}]
    t["outcome"] = {"type": "ProcessCompleted"}
    return t


def _goal(reference=REF, evidence="ConformanceResult"):
    return {"id": "binding:rts22", "intent": "conform", "scope": ["is_transmitted"], "status": "active",
            "acceptance": [{"id": "a1", "kind": "conformance", "label": "conforms", "required": True,
                            "component": {"function": "is_transmitted"}, "evidence": {"artifact": evidence},
                            **({"reference": reference} if reference else {})}]}


def _status(t, goal):
    t = copy.deepcopy(t)
    t["goals"] = [goal]
    enriched = goalops.enrich(t)
    return enriched["goals"][0]["acceptance"][0]


def test_criterion_with_a_reference_resolves_only_on_evidence_against_that_reference():
    t = _trace()
    a = _status(t, _goal())
    assert a["status"] == "done" and a.get("evidence_ref") == "c1"
    # the same criterion against a DIFFERENT reference: the standing conformance does not count
    other = _status(t, _goal(reference="ref:atlas:psd2-exemptions"))
    assert other["status"] == "todo" and not other.get("evidence_ref")
    # and a proof of some other property of the symbol never satisfies a referenced criterion
    t2 = _trace(); t2["artifacts"] = [a_ for a_ in t2["artifacts"] if a_["artifact_id"] != "c1"]; t2["actions"][2]["outputs"] = []
    assert _status(t2, _goal())["status"] == "todo"
    # without a reference the criterion keeps today's semantics (any ConformanceResult rooted in the symbol)
    assert _status(t, _goal(reference=None))["status"] == "done"
    # a PROJECT-level criterion: a reference, no component — met by any conformance against that reference
    proj = _goal(); proj["acceptance"][0].pop("component")
    assert _status(t, proj)["status"] == "done" and _status(t, proj).get("evidence_ref") == "c1"
    proj_other = _goal(reference="ref:atlas:psd2-exemptions"); proj_other["acceptance"][0].pop("component")
    assert _status(t, proj_other)["status"] == "todo"
    # no reference and no component is not a typed criterion at all (legacy path, stays todo)
    neither = _goal(reference=None); neither["acceptance"][0].pop("component")
    assert _status(t, neither)["status"] == "todo"


def test_reference_freshness_stale_when_the_reference_moved_and_healed_by_a_rerun():
    fresh = goalops.reference_freshness(_trace())
    assert fresh == []
    moved = goalops.reference_freshness(_trace(ref_version="onshored · 2017/590 · rev 2"))
    assert [r["residual_id"] for r in moved] == ["stale-ref-c1"]
    assert moved[0]["kind"] == "stale_evidence" and moved[0]["target"] == {"target_type": "artifact", "target_id": "c1"}
    assert "version onshored · 2017/590 → onshored · 2017/590 · rev 2" in moved[0]["statement"]
    content = goalops.reference_freshness(_trace(checksum="c2"))
    assert len(content) == 1 and "model content changed" in content[0]["statement"]
    gone = goalops.reference_freshness(_trace(with_reference=False))
    assert [r["kind"] for r in gone] == ["detached_evidence"]
    # it rides into stale_evidence, so enrich reports the criterion at risk under the governed role
    assert any(r["residual_id"] == "stale-ref-c1" for r in goalops.stale_evidence(_trace(ref_version="x")))
    # a later result against the NEW version heals the guard
    t = _trace(ref_version="onshored · 2017/590 · rev 2")
    t["actions"].append({"id": 4, "type": "Verify", "category": "reasoning", "rationale": "re-conform", "inputs": [REF, "m1"], "outputs": ["c2"]})
    c2 = copy.deepcopy(t["artifacts"][-1]); c2["artifact_id"] = "c2"; c2["producer_action_id"] = 4
    c2["payload"]["reference_version"] = "onshored · 2017/590 · rev 2"
    t["artifacts"].append(c2)
    assert goalops.reference_freshness(t) == []


def test_conforms_to_predicate_parses_with_an_opaque_id_and_selects_the_conformance_action():
    exact = f"G(Verify -> conforms_to({REF}))"
    _name, _errs, _warns = pc.check_policy({"name": "p", "policy_id": "p", "formula": exact, "severity": "error", "scope": "trace", "kind": "trace_invariant"})
    assert _errs == []
    t = _trace()
    # action 2 is a Verify with NO conformance evidence → the policy fails on it; scope the rule to action 3
    scoped = f"G(Verify && conformance -> conforms_to({REF}))"
    def ev(formula):
        return traceops.evaluate_policy({"name": "p", "policy_id": "p", "formula": formula, "severity": "error", "scope": "trace", "kind": "trace_invariant"}, t)[0]
    assert ev(scoped) == "passed"
    unversioned = "G(Verify && conformance -> conforms_to(ref:atlas:mifir-rts22-art4))"
    assert ev(unversioned) == "passed"
    wrong = "G(Verify && conformance -> conforms_to(ref:atlas:psd2-exemptions))"
    assert ev(wrong) == "failed"
    # and it composes with the strength ladder
    strong = f"G(Verify && conformance -> conforms_to({REF}) && strength_at_least(proof))"
    assert ev(strong) == "passed"


def test_validate_rejects_a_conformance_result_whose_reference_is_unknown():
    assert traceops.soundness_errors(_trace()) == []
    t = _trace(with_reference=False)
    errs = traceops.soundness_errors(t)
    assert any("reference_artifact_id" in e and REF in e for e in errs), errs

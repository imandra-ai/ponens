"""ponens.sdk — the thin runtime SDK: a Session builds a valid trace incrementally, verify()
invokes an oracle inline with lineage, and the context manager validates + saves on exit."""
import json

from ponens import sdk
from ponens import oracles as oc
from ponens import trace as trace_mod


def test_session_builds_a_structurally_valid_trace(tmp_path):
    s = sdk.Session(model="claude-opus", assistant="test-agent",
                    intent="prove charge() is idempotent")
    a = s.action("EditFile", label="edit pricing.py", rationale="fix the retry path",
                 evidence=[{"type": "FileRef", "ref": "pricing.py"}])
    art = s.artifact("IMLModel", name="pricing.iml", content="let charge x = x",
                     format="iml", producer_action_id=a)
    s.residual("assumption", "gateway returns within 30s", severity="low")
    s.outcome("ProcessCompleted")

    errors, _ = s.validate()
    assert errors == []
    # The producer action now lists the artifact as an output (lineage wiring).
    assert art in s.trace["actions"][0]["outputs"]
    # Content was externalized to the object store, not inlined.
    assert s.trace["artifacts"][0]["content_ref"].startswith("sha256:")
    # The intent became a goal.
    assert s.trace["goals"][0]["intent"].startswith("prove charge")


def test_verify_records_action_and_graded_evidence_with_lineage():
    fake = lambda target, context=None: {
        "status": "proved", "engine": "imandrax",
        "result": "Success: 1/1 POs succeeded", "reasoning_fingerprint": "f00d",
    }
    s = sdk.Session(assistant="test-agent")
    model = s.artifact("IMLModel", name="pricing.iml", payload={"iml_code": "let f x = x"})
    ids = s.verify({"iml_code": "let f x = x", "goal": "idempotent"},
                   oracle=oc.CodeLogicianOracle(runner=fake), derived_from=model)

    assert len(ids) == 1
    vr = next(x for x in s.trace["artifacts"] if x["artifact_id"] == ids[0])
    assert vr["artifact_type"] == "VerificationResult"
    assert vr["payload"]["evidence_strength"] == "proof"
    # Lineage: the result derives from the model it verified.
    assert model in vr["derived_from"]
    # A Verify action was recorded and produced the result.
    verify_action = next(a for a in s.trace["actions"] if a["type"] == "Verify")
    assert verify_action["category"] == "reasoning"
    assert vr["producer_action_id"] == verify_action["id"]


def test_verify_rejects_unknown_oracle():
    s = sdk.Session()
    try:
        s.verify({"goal": "x"}, oracle="does-not-exist")
        assert False, "expected ValueError for unknown oracle"
    except ValueError as e:
        assert "unknown oracle" in str(e)


def test_context_manager_saves_valid_trace_and_stamps_outcome(tmp_path):
    path = str(tmp_path / "trace.json")
    with sdk.Session(assistant="test-agent", path=path, intent="do a thing") as s:
        s.action("ReadFile", rationale="read the spec")
    # File written, reloads, and passes the structural validator.
    reloaded = trace_mod.load_trace(path)
    assert reloaded["outcome"]["type"] == "ProcessCompleted"
    errors, _ = trace_mod.validate_trace(reloaded)
    assert errors == []
    assert reloaded["assistant"] == "test-agent"


def test_context_manager_records_abort_on_exception(tmp_path):
    path = str(tmp_path / "trace.json")
    try:
        with sdk.Session(assistant="test-agent", path=path) as s:
            s.action("RunCommand", rationale="boom")
            raise RuntimeError("kaboom")
    except RuntimeError:
        pass
    # Aborted runs are still saved, marked ProcessAborted (not silently lost).
    reloaded = trace_mod.load_trace(path)
    assert reloaded["outcome"]["type"] == "ProcessAborted"
    assert "kaboom" in reloaded["outcome"]["summary"]

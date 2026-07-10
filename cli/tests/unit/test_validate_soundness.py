"""Deep-soundness validation (`ponens trace validate --strict`): the semantic invariants that catch
a mis-generated trace even when it is structurally well-typed. See `soundness_errors` in trace.py."""
import json
import os

from ponens.trace import soundness_errors, validate_trace

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "stripe-demo-trace.json")


def _fixture():
    with open(FIXTURE) as f:
        return json.load(f)


def test_reference_fixture_is_sound_and_strict_clean():
    t = _fixture()
    assert validate_trace(t)[0] == []          # structurally valid
    assert soundness_errors(t, strict=True) == []  # and deeply sound (incl. full phase coverage)


# --- Minimal well-formed trace we can perturb one invariant at a time. -------------------------

def _base():
    return {
        "trace_id": "t1",
        "spec_version": "1.1",
        "trigger": {"type": "TaskReceived"},
        "outcome": {"type": "ProcessCompleted"},
        "actions": [
            {"id": 1, "type": "ReadFile", "rationale": "read", "inputs": [], "outputs": ["src"]},
            {"id": 2, "type": "Formalize", "rationale": "formalize", "inputs": ["src"], "outputs": ["model"]},
            {"id": 3, "type": "DefineVG", "rationale": "goal", "inputs": ["model"], "outputs": ["goal"],
             "meta_action_id": "m1"},
            {"id": 4, "type": "Verify", "rationale": "verify", "inputs": ["goal"], "outputs": ["result"],
             "meta_action_id": "m1"},
        ],
        "artifacts": [
            {"artifact_id": "src", "artifact_type": "SourceCode", "producer_action_id": 1, "derived_from": []},
            {"artifact_id": "model", "artifact_type": "IMLModel", "producer_action_id": 2, "derived_from": ["src"]},
            {"artifact_id": "goal", "artifact_type": "VerificationGoal", "producer_action_id": 3,
             "derived_from": ["model"]},
            {"artifact_id": "result", "artifact_type": "VerificationResult", "producer_action_id": 4,
             "derived_from": ["goal"], "payload": {"status": "proved"}},
        ],
        "meta_actions": [
            {"id": "m1", "title": "Verify", "action_ids": [3, 4], "status": "completed", "source": "intent_inferred"},
        ],
        "residuals": [],
        "reference_artifacts": [],
    }


def test_base_is_clean():
    assert soundness_errors(_base(), strict=True) == []


def test_dangling_derived_from_is_flagged():
    t = _base()
    t["artifacts"][1]["derived_from"] = ["ghost"]
    errs = soundness_errors(t)
    assert any("derived_from 'ghost' does not exist" in e for e in errs)


def test_missing_producer_action_is_flagged():
    t = _base()
    t["artifacts"][1]["producer_action_id"] = 999
    errs = soundness_errors(t)
    assert any("producer_action_id 999 does not exist" in e for e in errs)


def test_data_flow_cycle_is_flagged():
    # Action 2 consumes 'goal', which is produced later by action 3.
    t = _base()
    t["actions"][1]["inputs"] = ["goal"]
    errs = soundness_errors(t)
    assert any("data-flow cycle" in e for e in errs)


def test_consumed_but_never_produced_is_flagged():
    t = _base()
    t["actions"][3]["inputs"] = ["nowhere"]
    errs = soundness_errors(t)
    assert any("'nowhere'" in e for e in errs)


def test_result_without_goal_is_flagged():
    t = _base()
    t["artifacts"][3]["derived_from"] = ["model"]  # points at the model, not a goal
    errs = soundness_errors(t)
    assert any("does not derive from a VerificationGoal" in e for e in errs)


def test_goal_without_model_is_flagged():
    t = _base()
    t["artifacts"][2]["derived_from"] = []
    errs = soundness_errors(t)
    assert any("does not derive from an IMLModel" in e for e in errs)


def test_invalid_verdict_status_is_flagged():
    t = _base()
    t["artifacts"][3]["payload"]["status"] = "maybe"
    errs = soundness_errors(t)
    assert any("invalid status 'maybe'" in e for e in errs)


def test_ungrouped_action_only_flagged_under_strict():
    t = _base()
    t["meta_actions"] = []
    for a in t["actions"]:
        a.pop("meta_action_id", None)
    assert soundness_errors(t, strict=False) == []          # coverage is not a universal requirement
    errs = soundness_errors(t, strict=True)
    assert any("not grouped into any phase meta-action" in e for e in errs)

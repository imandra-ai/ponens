"""Revision chains (spec §7.3 `supersedes`) + failed-attempt provenance (CommandResult).

The framework half of the imandra-pi-agent provenance work: an append-only producer emits each
re-analysis as a new revision that `supersedes` its predecessor, and a failed/aborted run as a
CommandResult. ponens must fold the history to the current state, walk the chain, validate that a
`supersedes` resolves, and surface a command result onto its action for policy reasoning."""
from ponens.trace import (
    superseded_ids,
    current_artifacts,
    revision_chain,
    normalize_trace,
    validate_trace,
)


def _trace(artifacts, actions=None):
    return {
        "trace_id": "t1",
        "spec_version": "1.1",
        "trigger": {"type": "TaskReceived"},
        "outcome": {"type": "ProcessCompleted"},
        "actions": actions or [],
        "artifacts": artifacts,
    }


# --- supersedes: fold to current + walk the chain -------------------------------------------------

def _chain():
    # fr2-regions (rev 1) ← fr7-regions (rev 2) ← fr9-regions (rev 3), plus an unrelated current node.
    return _trace([
        {"artifact_id": "fr2-regions", "artifact_type": "StateSpaceAnalysisResult", "derived_from": []},
        {"artifact_id": "fr7-regions", "artifact_type": "StateSpaceAnalysisResult", "derived_from": [],
         "revision": 2, "supersedes": "fr2-regions"},
        {"artifact_id": "fr9-regions", "artifact_type": "StateSpaceAnalysisResult", "derived_from": [],
         "revision": 3, "supersedes": "fr7-regions"},
        {"artifact_id": "v1-result", "artifact_type": "VerificationResult", "derived_from": []},
    ])


def test_superseded_ids_lists_replaced_predecessors():
    assert superseded_ids(_chain()) == {"fr2-regions", "fr7-regions"}


def test_current_artifacts_folds_out_history():
    ids = [a["artifact_id"] for a in current_artifacts(_chain())]
    assert ids == ["fr9-regions", "v1-result"]  # only the latest revision + the unrelated node


def test_revision_chain_walks_newest_to_oldest():
    assert revision_chain("fr9-regions", _chain()) == ["fr9-regions", "fr7-regions", "fr2-regions"]


def test_revision_chain_tolerates_a_list_supersedes():
    t = _trace([
        {"artifact_id": "a1", "artifact_type": "GeneratedTests", "derived_from": []},
        {"artifact_id": "a2", "artifact_type": "GeneratedTests", "derived_from": [], "supersedes": ["a1"]},
    ])
    assert revision_chain("a2", t) == ["a2", "a1"]
    assert superseded_ids(t) == {"a1"}


def test_chain_is_cycle_safe():
    t = _trace([
        {"artifact_id": "a", "artifact_type": "X", "derived_from": [], "supersedes": "b"},
        {"artifact_id": "b", "artifact_type": "X", "derived_from": [], "supersedes": "a"},
    ])
    assert revision_chain("a", t) == ["a", "b"]  # terminates, no infinite loop


# --- validate: a dangling supersedes warns (chain broken), a resolved one is clean ----------------

def test_dangling_supersedes_warns():
    t = _trace([
        {"artifact_id": "a2", "artifact_type": "GeneratedTests", "derived_from": [], "supersedes": "gone"},
    ])
    errors, warnings = validate_trace(t)
    assert errors == []
    assert any("supersedes 'gone' does not exist" in w for w in warnings)


def test_resolved_supersedes_is_clean():
    _, warnings = validate_trace(_chain())
    assert not any("supersedes" in w for w in warnings)


# --- CommandResult: a failed attempt surfaces onto its action ------------------------------------

def test_command_result_normalizes_onto_its_action():
    t = _trace(
        artifacts=[
            {"artifact_id": "fr3-attempt", "artifact_type": "CommandResult", "producer_action_id": 1,
             "derived_from": [], "payload": {"outcome": "failed-admit", "operation": "check", "exit_code": 1}},
        ],
        actions=[{"id": 1, "type": "Attempt", "rationale": "attempt", "inputs": [], "outputs": ["fr3-attempt"]}],
    )
    normalize_trace(t)
    cr = t["actions"][0]["command_result"]
    assert cr["outcome"] == "failed-admit"
    assert cr["exit_code"] == 1

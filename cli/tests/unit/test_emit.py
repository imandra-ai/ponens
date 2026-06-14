"""Unit tests for the session-transcript -> trace emitter (emit.py)."""

from ponens.emit import transcript_to_trace, summarize_actions
from ponens.adapters.claude_code import _bash_action
from ponens.trace import validate_trace


def _a(i, t, f=None, res=None):
    a = {"id": i, "type": t, "category": "activity", "label": t, "rationale": "r",
         "inputs": [], "outputs": [], "evidence": ([{"type": "FileRef", "ref": f}] if f else []),
         "_turn": i}
    if res:
        a["result_summary"] = res
    return a


ENTRIES = [
    {"type": "user", "message": {"content": "add input validation"}},
    {"type": "assistant", "message": {"model": "agent-x", "content": [
        {"type": "text", "text": "Let me read the file first."},
        {"type": "tool_use", "id": "u1", "name": "Read", "input": {"file_path": "form.js"}}]}},
    {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "u1", "content": "file contents", "is_error": False}]}},
    {"type": "assistant", "message": {"content": [
        {"type": "text", "text": "Now edit it."},
        {"type": "tool_use", "id": "u2", "name": "Edit", "input": {"file_path": "form.js"}},
        {"type": "tool_use", "id": "u3", "name": "TaskCreate", "input": {"subject": "x"}}]}},  # skipped
    {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "u4", "name": "Bash",
         "input": {"command": "pytest -q", "description": "run tests"}}]}},
    {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "u4", "content": "6 passed", "is_error": False}]}},
    {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "u5", "name": "Bash", "input": {"command": "git commit -m x"}}]}},
]


def test_maps_tools_to_action_types():
    t = transcript_to_trace(ENTRIES)
    assert [a["type"] for a in t["actions"]] == ["ReadFile", "EditFile", "RunTests", "GitCommit"]


def test_skips_meta_tools():
    t = transcript_to_trace(ENTRIES)
    # TaskCreate (u3) is dropped → 4 actions, not 5
    assert t["metrics"]["total_actions"] == 4


def test_trigger_from_first_prompt():
    t = transcript_to_trace(ENTRIES)
    assert t["trigger"]["description"] == "add input validation"


def test_files_modified_collected():
    t = transcript_to_trace(ENTRIES)
    assert t["files_modified"] == ["form.js"]


def test_model_captured():
    assert transcript_to_trace(ENTRIES)["model"] == "agent-x"


def test_rationale_from_leading_text():
    t = transcript_to_trace(ENTRIES)
    assert "read the file" in t["actions"][0]["rationale"]


def test_result_summary_from_tool_result():
    t = transcript_to_trace(ENTRIES)
    run_tests = next(a for a in t["actions"] if a["type"] == "RunTests")
    assert "6 passed" in run_tests["result_summary"]


def test_evidence_fileref_for_reads():
    t = transcript_to_trace(ENTRIES)
    read = t["actions"][0]
    assert read["evidence"][0] == {"type": "FileRef", "ref": "form.js"}


def test_emitted_trace_is_valid():
    errors, _ = validate_trace(transcript_to_trace(ENTRIES))
    assert errors == []


def test_error_result_prefixed():
    entries = [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "x", "name": "Bash", "input": {"command": "ls"}}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "x", "content": "boom", "is_error": True}]}},
    ]
    t = transcript_to_trace(entries)
    assert t["actions"][0]["result_summary"].startswith("ERROR: ")


def test_bash_action_classification():
    assert _bash_action("git commit -m x") == "GitCommit"
    assert _bash_action("python3 -m pytest -q") == "RunTests"
    assert _bash_action("ls -la") == "RunCommand"


# --- summarization ----------------------------------------------------------

def test_summarize_collapses_research_run():
    out = summarize_actions([_a(1, "ReadFile", "a.py"), _a(2, "ReadFile", "b.py"), _a(3, "SearchCode")])
    assert len(out) == 1
    assert out[0]["type"] == "ReadFile"
    assert {"type": "FileRef", "ref": "a.py"} in out[0]["evidence"]


def test_summarize_keeps_tests_and_commits_standalone():
    out = summarize_actions([_a(1, "EditFile", "x.py"), _a(2, "EditFile", "x.py"),
                             _a(3, "RunTests", res="148 passed"), _a(4, "EditFile", "y.py")])
    assert [a["type"] for a in out] == ["EditFile", "RunTests", "EditFile"]
    assert out[1]["result_summary"] == "148 passed"


def test_summarize_renumbers_ids():
    out = summarize_actions([_a(1, "ReadFile", "a"), _a(2, "EditFile", "b")])
    assert [a["id"] for a in out] == [1, 2]


def test_emit_raw_strips_internal_turn_key():
    t = transcript_to_trace(ENTRIES)
    assert all("_turn" not in a for a in t["actions"])


def test_emit_summarize_is_not_larger():
    raw = transcript_to_trace(ENTRIES)
    summ = transcript_to_trace(ENTRIES, summarize=True)
    assert summ["metrics"]["total_actions"] <= raw["metrics"]["total_actions"]
    assert all("_turn" not in a for a in summ["actions"])


# --- motivation / reasoning capture -----------------------------------------

def test_thinking_used_as_rationale():
    entries = [{"type": "assistant", "message": {"content": [
        {"type": "thinking", "thinking": "I need to understand the parser before editing."},
        {"type": "tool_use", "id": "t", "name": "Read", "input": {"file_path": "p.py"}}]}}]
    t = transcript_to_trace(entries)
    assert "understand the parser" in t["actions"][0]["rationale"]


def test_rationale_carries_over_chained_calls():
    entries = [
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Implementing the feature now."},
            {"type": "tool_use", "id": "1", "name": "Edit", "input": {"file_path": "a.py"}}]}},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "2", "name": "Edit", "input": {"file_path": "b.py"}}]}},  # no prose
    ]
    t = transcript_to_trace(entries)
    assert all("Implementing the feature" in a["rationale"] for a in t["actions"])


def test_askuserquestion_becomes_gateway():
    entries = [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "q", "name": "AskUserQuestion",
             "input": {"questions": [{"question": "Which approach?"}]}}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "q", "content": "=Option A selected", "is_error": False}]}},
    ]
    a = transcript_to_trace(entries)["actions"][0]
    assert a["category"] == "gateway" and a["type"] == "ExclusiveDecision"
    assert "Which approach" in a["detail"]


def test_bash_has_reproducibility():
    entries = [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "b", "name": "Bash", "input": {"command": "pytest -q"}}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "b", "content": "6 passed", "is_error": False}]}},
    ]
    a = transcript_to_trace(entries)["actions"][0]
    assert a["reproducibility"]["procedure"]["command"] == "pytest -q"
    assert a["reproducibility"]["expected_output"]["result_summary"] == "6 passed"
    assert a["execution"]["determinism"] == "deterministic"


def test_trace_level_reproducibility():
    assert transcript_to_trace([])["reproducibility"]["status"] == "partially_reproducible"


# --- meta-actions (§8.4) ----------------------------------------------------

META_ENTRIES = [
    {"type": "user", "message": {"content": "build the parser"}},
    {"type": "assistant", "message": {"content": [
        {"type": "text", "text": "Starting the parser."},
        {"type": "tool_use", "id": "tc", "name": "TaskCreate", "input": {"subject": "Implement parser"}},
        {"type": "tool_use", "id": "tu1", "name": "TaskUpdate", "input": {"taskId": "1", "status": "in_progress"}},
        {"type": "tool_use", "id": "e1", "name": "Edit", "input": {"file_path": "parser.py"}}]}},
    {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "e2", "name": "Edit", "input": {"file_path": "parser.py"}},
        {"type": "tool_use", "id": "tu2", "name": "TaskUpdate", "input": {"taskId": "1", "status": "completed"}}]}},
    {"type": "user", "message": {"content": "now add tests for the parser module"}},
    {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "b1", "name": "Bash", "input": {"command": "pytest -q"}}]}},
]


def test_emits_meta_actions_and_spec_1_6():
    t = transcript_to_trace(META_ENTRIES)
    assert t["spec_version"] == "1.6"
    assert len(t["meta_actions"]) == 2


def test_task_tools_are_not_actions():
    # TaskCreate/TaskUpdate drive grouping but are not emitted as actions
    t = transcript_to_trace(META_ENTRIES)
    assert [a["type"] for a in t["actions"]] == ["EditFile", "EditFile", "RunTests"]


def test_plan_declared_meta_action_from_todo():
    m = transcript_to_trace(META_ENTRIES)["meta_actions"][0]
    assert m["source"] == "plan_declared"
    assert m["title"] == "Implement parser"
    assert m["status"] == "completed"
    assert m["action_ids"] == [1, 2]


def test_turn_segmented_meta_action():
    m = transcript_to_trace(META_ENTRIES)["meta_actions"][1]
    assert m["source"] == "turn_segmented"
    assert "add tests" in m["intent"]
    assert m["action_ids"] == [3]


def test_meta_action_id_backrefs_are_consistent():
    t = transcript_to_trace(META_ENTRIES)
    by = {a["id"]: a.get("meta_action_id") for a in t["actions"]}
    for m in t["meta_actions"]:
        for aid in m["action_ids"]:
            assert by[aid] == m["id"]


def test_meta_actions_partition_actions():
    t = transcript_to_trace(META_ENTRIES)
    members = [i for m in t["meta_actions"] for i in m["action_ids"]]
    assert sorted(members) == [a["id"] for a in t["actions"]]
    assert len(members) == len(set(members))   # no action in two meta-actions


def test_trivial_directive_titled_by_first_action():
    entries = [
        {"type": "user", "message": {"content": "yes"}},
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Implementing the caching layer now."},
            {"type": "tool_use", "id": "e", "name": "Edit", "input": {"file_path": "cache.py"}}]}},
    ]
    m = transcript_to_trace(entries)["meta_actions"][0]
    assert "caching layer" in m["title"] and "yes" != m["title"]


def test_meta_actions_survive_summarization():
    t = transcript_to_trace(META_ENTRIES, summarize=True)
    members = [i for m in t["meta_actions"] for i in m["action_ids"]]
    assert sorted(members) == [a["id"] for a in t["actions"]]
    assert all("meta_action_id" in a for a in t["actions"])


# --- synthesized lineage (auto-artifacts) -----------------------------------

def test_synthesizes_lineage_dag():
    from ponens.trace import evaluate_structural
    t = transcript_to_trace(ENTRIES)
    types = {a["artifact_type"] for a in t["artifacts"]}
    assert {"SourceCode", "TestResult", "Commit"} <= types
    # the wired data flow is well-formed (every consumed artifact has an earlier producer)
    assert evaluate_structural("data_flow_integrity", t) is True


def test_edit_produces_versioned_source():
    entries = [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "1", "name": "Edit", "input": {"file_path": "x.py"}}]}},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "2", "name": "Edit", "input": {"file_path": "x.py"}}]}},
    ]
    arts = [a for a in transcript_to_trace(entries)["artifacts"] if a["artifact_type"] == "SourceCode"]
    assert len(arts) == 2
    assert arts[1]["derived_from"] == [arts[0]["artifact_id"]]   # v2 derives from v1


def test_commit_consumes_the_edited_source():
    t = transcript_to_trace(ENTRIES)
    src = next(a for a in t["artifacts"] if a["artifact_type"] == "SourceCode")
    commit = next(a for a in t["actions"] if a["type"] == "GitCommit")
    assert src["artifact_id"] in commit["inputs"]               # commit consumes the code


def test_readonly_session_has_no_artifacts():
    entries = [{"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "r", "name": "Read", "input": {"file_path": "a.py"}}]}}]
    assert transcript_to_trace(entries)["artifacts"] == []

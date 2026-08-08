"""Unit tests for the Codex CLI rollout adapter."""

from ponens.adapters import codex
from ponens.emit import build_trace
from ponens.trace import validate_trace


def _resp(payload):
    return {"type": "response_item", "timestamp": "2026-05-01T00:00:00Z", "payload": payload}


ENTRIES = [
    {"type": "session_meta", "payload": {"cwd": "/repo", "model": "gpt-5.4", "cli_version": "0.1"}},
    {"type": "turn_context", "payload": {"turn_id": "t1", "cwd": "/repo"}},
    # system / permissions chrome -> skipped
    _resp({"type": "message", "role": "developer",
           "content": [{"type": "input_text", "text": "<permissions instructions> ..."}]}),
    # environment chrome (wrapped in a tag) -> skipped, not a directive
    _resp({"type": "message", "role": "user",
           "content": [{"type": "input_text", "text": "<environment_context><cwd>/repo</cwd></environment_context>"}]}),
    # the real user prompt -> directive
    _resp({"type": "message", "role": "user",
           "content": [{"type": "input_text", "text": "add a clamp function and test it"}]}),
    # encrypted reasoning -> skipped
    _resp({"type": "reasoning", "summary": [], "encrypted_content": "gAAA..."}),
    # the agent's narrative -> becomes the rationale carried onto the following tool calls
    _resp({"type": "message", "role": "assistant",
           "content": [{"type": "output_text", "text": "I'll look at the repo first."}]}),
    # shell search -> SearchCode, with a result matched by call_id
    _resp({"type": "function_call", "name": "exec_command",
           "arguments": '{"cmd":"rg clamp"}', "call_id": "c1"}),
    _resp({"type": "function_call_output", "call_id": "c1", "output": "no matches"}),
    # shell read -> ReadFile
    _resp({"type": "function_call", "name": "exec_command",
           "arguments": '{"cmd":"sed -n \'1,20p\' calc.py"}', "call_id": "c2"}),
    # apply_patch adding a file -> CreateFile with the file parsed from the patch header
    _resp({"type": "custom_tool_call", "name": "apply_patch", "call_id": "c3",
           "input": "*** Begin Patch\n*** Add File: clamp.py\n+let clamp x = x\n*** End Patch"}),
    # shell tests -> RunTests
    _resp({"type": "function_call", "name": "exec_command",
           "arguments": '{"cmd":"pytest -q"}', "call_id": "c4"}),
    # web search -> SearchWeb
    _resp({"type": "web_search_call", "action": {"type": "open_page", "url": "https://example.com"}}),
    {"type": "event_msg", "payload": {"type": "task_complete"}},
]


def test_maps_codex_tools_in_order():
    parsed = codex.parse(ENTRIES)
    types = [e["type"] for e in parsed["events"] if e["t"] == "action"]
    assert types == ["SearchCode", "ReadFile", "CreateFile", "RunTests", "SearchWeb"]


def test_extracts_user_directive_skips_chrome():
    parsed = codex.parse(ENTRIES)
    dirs = [e["text"] for e in parsed["events"] if e["t"] == "directive"]
    assert dirs == ["add a clamp function and test it"]


def test_apply_patch_add_is_createfile_with_file():
    parsed = codex.parse(ENTRIES)
    create = next(e for e in parsed["events"] if e["t"] == "action" and e["type"] == "CreateFile")
    assert create["file"] == "clamp.py" and create["is_edit"] is True


def test_shell_classification():
    parsed = codex.parse(ENTRIES)
    by_cmd = {e.get("command"): e["type"] for e in parsed["events"] if e["t"] == "action" and e.get("command")}
    assert by_cmd["rg clamp"] == "SearchCode"
    assert by_cmd["sed -n '1,20p' calc.py"] == "ReadFile"
    assert by_cmd["pytest -q"] == "RunTests"


def test_result_and_rationale_are_carried():
    parsed = codex.parse(ENTRIES)
    search = next(e for e in parsed["events"] if e["t"] == "action" and e["type"] == "SearchCode")
    assert search["result"] == "no matches"                     # matched by call_id
    assert "repo first" in (search["rationale"] or "").lower()  # assistant narrative carried over


def test_model_detected():
    assert codex.parse(ENTRIES)["model"] == "gpt-5.4"


def test_build_trace_is_valid():
    trace = build_trace(codex.parse(ENTRIES))
    errors, _ = validate_trace(trace)
    assert errors == []

"""Unit tests for the Gemini CLI chat adapter."""

from ponens.adapters import gemini
from ponens.emit import build_trace
from ponens.trace import validate_trace


ENTRIES = [
    # session header line (no `type`) -> ignored
    {"sessionId": "x", "projectHash": "h", "startTime": "2026-06-17T10:59:07.378Z"},
    {"type": "user", "content": [{"text": "write some iml model for me"}]},
    {
        "type": "gemini",
        "model": "gemini-3-flash-preview",
        "content": "I'll look around first.",
        "toolCalls": [
            {"name": "glob", "args": {"pattern": "**/*.iml"}, "status": "success",
             "resultDisplay": "3 files", "displayName": "FindFiles"},
            {"name": "read_file", "args": {"absolute_path": "calc.py"}, "status": "success",
             "resultDisplay": "def calc(): ...", "displayName": "ReadFile"},
            {"name": "activate_skill", "args": {"name": "codelogician"}, "status": "success"},  # skipped
        ],
    },
    # a tool-result echo (functionResponse) as a user turn -> NOT a directive
    {"type": "user", "content": [{"functionResponse": {"id": "1", "name": "read_file",
                                                       "response": {"output": "..."}}}]},
    {
        "type": "gemini",
        "content": "Now write and check it.",
        "toolCalls": [
            {"name": "write_file", "args": {"file_path": "model.iml"}, "status": "success"},
            {"name": "run_shell_command", "args": {"command": "pytest -q"}, "status": "success"},
            {"name": "replace", "args": {"file_path": "model.iml"}, "status": "error"},
        ],
    },
]


def test_maps_gemini_tools_in_order():
    parsed = gemini.parse(ENTRIES)
    types = [e["type"] for e in parsed["events"] if e["t"] == "action"]
    assert types == ["ExploreDirectory", "ReadFile", "CreateFile", "RunTests", "EditFile"]


def test_skips_meta_tools_and_result_echoes():
    parsed = gemini.parse(ENTRIES)
    labels = [e.get("fallback_label") for e in parsed["events"] if e["t"] == "action"]
    assert "activate_skill" not in labels and "Activate Skill" not in labels
    dirs = [e["text"] for e in parsed["events"] if e["t"] == "directive"]
    assert dirs == ["write some iml model for me"]        # the functionResponse user turn is skipped


def test_file_extraction_and_error_status():
    parsed = gemini.parse(ENTRIES)
    read = next(e for e in parsed["events"] if e["t"] == "action" and e["type"] == "ReadFile")
    assert read["file"] == "calc.py"
    edit = next(e for e in parsed["events"] if e["t"] == "action" and e["type"] == "EditFile")
    assert edit["error"] is True                          # status == "error"


def test_shell_and_rationale():
    parsed = gemini.parse(ENTRIES)
    tests = next(e for e in parsed["events"] if e["t"] == "action" and e["type"] == "RunTests")
    assert tests["command"] == "pytest -q"
    glob_ev = next(e for e in parsed["events"] if e["t"] == "action" and e["type"] == "ExploreDirectory")
    assert "look around" in (glob_ev["rationale"] or "").lower()


def test_model_detected():
    assert gemini.parse(ENTRIES)["model"] == "gemini-3-flash-preview"


def test_build_trace_is_valid():
    trace = build_trace(gemini.parse(ENTRIES))
    errors, _ = validate_trace(trace)
    assert errors == []

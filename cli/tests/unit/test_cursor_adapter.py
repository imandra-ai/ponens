"""Unit tests for the Cursor IDE transcript adapter."""

import os

from ponens.adapters import cursor
from ponens.emit import build_trace
from ponens.trace import validate_trace


ENTRIES = [
    {
        "role": "user",
        "message": {
            "content": [
                {
                    "type": "text",
                    "text": (
                        "<timestamp>Thursday, Jul 23, 2026</timestamp>\n"
                        "<user_query>\nfix the None entitlements pill\n</user_query>"
                    ),
                }
            ]
        },
    },
    {
        "role": "assistant",
        "message": {
            "model": "cursor-agent",
            "content": [
                {"type": "text", "text": "I'll read the page first.\n\n[REDACTED]"},
                {
                    "type": "tool_use",
                    "id": "r1",
                    "name": "Read",
                    "input": {"path": "/repo/app/page.re"},
                },
            ],
        },
    },
    {
        "role": "assistant",
        "message": {
            "content": [
                {"type": "text", "text": "Now patch it."},
                {
                    "type": "tool_use",
                    "id": "e1",
                    "name": "StrReplace",
                    "input": {
                        "path": "/repo/app/page.re",
                        "old_string": "Universe",
                        "new_string": "None",
                    },
                },
                {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "TodoWrite",
                    "input": {
                        "todos": [
                            {
                                "id": "pill",
                                "content": "Add None pill",
                                "status": "in_progress",
                            }
                        ]
                    },
                },
            ],
        },
    },
    {
        "role": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": "s1",
                    "name": "Shell",
                    "input": {
                        "command": "git status",
                        "description": "check status",
                    },
                },
                {
                    "type": "tool_use",
                    "id": "s2",
                    "name": "Shell",
                    "input": {"command": "pytest -q"},
                },
                {
                    "type": "tool_use",
                    "id": "await1",
                    "name": "AwaitShell",
                    "input": {"shell_id": "1"},
                },
            ],
        },
    },
    {
        "role": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": "q1",
                    "name": "AskQuestion",
                    "input": {
                        "title": "Visibility",
                        "questions": [
                            {
                                "id": "v",
                                "prompt": "Who should see pending invites?",
                                "options": [{"id": "all", "label": "Everyone"}],
                            }
                        ],
                    },
                }
            ],
        },
    },
    {"type": "turn_ended", "status": "ok"},
]


def test_maps_cursor_tools():
    parsed = cursor.parse(ENTRIES)
    types = [e["type"] for e in parsed["events"] if e["t"] == "action"]
    assert types == [
        "ReadFile",
        "EditFile",
        "GitStatus",
        "RunTests",
        "ExclusiveDecision",
    ]


def test_skips_awaitshell_and_status_rows():
    parsed = cursor.parse(ENTRIES)
    labels = [
        e.get("fallback_label")
        for e in parsed["events"]
        if e["t"] == "action"
    ]
    assert "AwaitShell" not in labels


def test_extracts_user_query_directive():
    parsed = cursor.parse(ENTRIES)
    dirs = [e["text"] for e in parsed["events"] if e["t"] == "directive"]
    assert dirs == ["fix the None entitlements pill"]


def test_strips_redacted_from_rationale():
    parsed = cursor.parse(ENTRIES)
    read = next(e for e in parsed["events"] if e["t"] == "action" and e["type"] == "ReadFile")
    assert "[REDACTED]" not in (read["rationale"] or "")
    assert "read the page" in read["rationale"].lower()


def test_uses_path_not_file_path():
    parsed = cursor.parse(ENTRIES)
    edit = next(e for e in parsed["events"] if e["t"] == "action" and e["type"] == "EditFile")
    assert edit["file"] == "/repo/app/page.re"
    assert edit["is_edit"] is True


def test_todowrite_becomes_todo_events():
    parsed = cursor.parse(ENTRIES)
    kinds = [e["t"] for e in parsed["events"] if e["t"].startswith("todo_")]
    assert "todo_create" in kinds
    assert "todo_update" in kinds
    create = next(e for e in parsed["events"] if e["t"] == "todo_create")
    assert create["subject"] == "Add None pill"


def test_askquestion_is_gateway():
    parsed = cursor.parse(ENTRIES)
    q = next(
        e
        for e in parsed["events"]
        if e["t"] == "action" and e["type"] == "ExclusiveDecision"
    )
    assert q["category"] == "gateway"
    assert "pending invites" in q["decision"]["question"].lower()


def test_model_captured():
    assert cursor.parse(ENTRIES)["model"] == "cursor-agent"


def test_build_trace_is_valid():
    trace = build_trace(cursor.parse(ENTRIES))
    errors, _ = validate_trace(trace)
    assert errors == []
    assert trace["trigger"]["description"] == "fix the None entitlements pill"
    assert "/repo/app/page.re" in trace["files_modified"] or any(
        "page.re" in f for f in trace["files_modified"]
    )


def test_createplan_is_todo_create():
    entries = [
        {
            "role": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "p",
                        "name": "CreatePlan",
                        "input": {
                            "name": "Admin cleanup",
                            "overview": "Extract spinners",
                            "todos": [{"id": "a", "content": "Add Spinner.Section"}],
                        },
                    }
                ]
            },
        }
    ]
    parsed = cursor.parse(entries)
    subjects = [e["subject"] for e in parsed["events"] if e["t"] == "todo_create"]
    assert "Admin cleanup" in subjects
    assert "Add Spinner.Section" in subjects
    assert not any(e["t"] == "action" for e in parsed["events"])


def test_shell_action_helpers():
    assert cursor._shell_action("git commit -m x") == "GitCommit"
    assert cursor._shell_action("direnv exec . dune runtest") == "RunTests"
    assert cursor._shell_action("ls") == "RunCommand"


def test_project_slug():
    assert cursor._project_slug("/Users/e/github/imandra-web") == "Users-e-github-imandra-web"


def test_default_transcript_ignores_subagents(tmp_path, monkeypatch):
    root = tmp_path / "agent-transcripts"
    parent = root / "aaaa-bbbb"
    parent.mkdir(parents=True)
    parent_file = parent / "aaaa-bbbb.jsonl"
    parent_file.write_text("{}\n")
    sub = parent / "subagents"
    sub.mkdir()
    child = sub / "child.jsonl"
    child.write_text("{}\n")
    # newer subagent must not win
    os.utime(parent_file, (1_000_000, 1_000_000))
    os.utime(child, (2_000_000, 2_000_000))

    monkeypatch.setattr(cursor, "_agent_transcripts_dir", lambda slug=None: str(root))
    assert cursor.default_transcript() == str(parent_file)


def test_read_entries_roundtrip(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text('{"role":"user","message":{"content":"hi"}}\nnot-json\n')
    assert len(cursor.read_entries(p)) == 1

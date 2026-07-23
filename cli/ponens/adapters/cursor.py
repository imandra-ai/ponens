"""Cursor IDE agent transcript adapter.

Maps a Cursor agent session transcript (JSONL under
``~/.cursor/projects/<slug>/agent-transcripts/<uuid>/<uuid>.jsonl``) into the
normalized event stream that ``emit.build_trace`` consumes.

Cursor's shape is close to Claude Code's (``role`` + content blocks with
``text`` / ``tool_use``), with these differences handled here:

- Rows use ``role`` (``user`` / ``assistant``), not Claude's top-level ``type``.
- User turns wrap the prompt in ``<user_query>…</user_query>`` (plus UI chrome).
- Tool vocabulary: ``Shell``, ``StrReplace``, ``AskQuestion``, ``TodoWrite``, …
  (paths are ``path``, not ``file_path``).
- Tool results are typically **not** persisted in the JSONL (no
  ``tool_result`` blocks) — actions still emit; ``result`` is simply absent.
- Bookkeeping / IDE-only tools (``AwaitShell``, ``Task``, MCP, …) are skipped.
- Subagent transcripts live under ``…/subagents/`` and are ignored by
  ``default_transcript()``.

Exposes the adapter surface: NAME, IMPLEMENTED, default_transcript(),
read_entries(path), parse(entries) -> {events, model, assistant, last_reasoning}.
"""
from __future__ import annotations

import glob
import json
import os
import re

NAME = "cursor"
IMPLEMENTED = True

# Cursor tool name -> canonical trace action type. ``Shell`` is refined by
# ``_shell_action``. Unlisted tools fall back to RunCommand unless skipped.
TOOL_MAP = {
    "Read": "ReadFile",
    "StrReplace": "EditFile",
    "Write": "CreateFile",
    "Delete": "EditFile",
    "EditNotebook": "EditFile",
    "Grep": "SearchCode",
    "Glob": "ExploreDirectory",
    "WebSearch": "SearchWeb",
    "WebFetch": "ReadDocumentation",
    "AskQuestion": "AskUser",
    "ReadLints": "RunCommand",
}

# Meta / IDE plumbing — not part of the engineering record.
# TodoWrite / CreatePlan are handled as todo_* events (not actions).
SKIP_TOOLS = {
    "AwaitShell",
    "Await",
    "Task",
    "SwitchMode",
    "CallMcpTool",
    "GetMcpTools",
    "FetchMcpResource",
    "GenerateImage",
}

FILE_TOOLS = {"Read", "StrReplace", "Write", "Delete", "EditNotebook"}
EDIT_TOOLS = {"StrReplace", "Write", "Delete", "EditNotebook"}
SEARCH_TOOLS = {"Grep", "Glob"}

_USER_QUERY_RE = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.DOTALL)
_REDACTED_RE = re.compile(r"\[REDACTED\]")


def _shell_action(cmd):
    c = (cmd or "").lower()
    if "git commit" in c:
        return "GitCommit"
    if "git diff" in c:
        return "GitDiff"
    if "git status" in c:
        return "GitStatus"
    if any(
        t in c
        for t in (
            "pytest",
            "npm test",
            "go test",
            "cargo test",
            "unittest",
            "vitest",
            "dune runtest",
        )
    ):
        return "RunTests"
    return "RunCommand"


def _action_type(tool, inp):
    if tool == "Shell":
        return _shell_action(inp.get("command", ""))
    return TOOL_MAP.get(tool, "RunCommand")


def _file_from_input(tool, inp):
    if tool == "EditNotebook":
        return inp.get("target_notebook") or inp.get("path")
    if tool in FILE_TOOLS:
        return inp.get("path") or inp.get("file_path")
    return None


def _reasoning(content):
    """Human-facing text before the first tool_use; falls back to thinking blocks."""
    texts, thinks = [], []
    for b in content:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "tool_use":
            break
        if b.get("type") == "text" and b.get("text"):
            t = _REDACTED_RE.sub("", b["text"]).strip()
            if t:
                texts.append(t)
        elif b.get("type") == "thinking" and (b.get("thinking") or b.get("text")):
            thinks.append((b.get("thinking") or b.get("text")).strip())
    return " ".join(texts).strip() or " ".join(thinks).strip()


def _directive_text(content):
    """Extract the user's real instruction from a Cursor user turn.

    Cursor wraps prompts as ``<user_query>…</user_query>`` inside a larger UI
    payload. Prefer that; otherwise return plain text content.
    """
    if isinstance(content, str):
        raw = content
    elif isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text" and b.get("text"):
                parts.append(b["text"])
            # Ignore tool_result blocks if they ever appear on user turns.
        raw = "\n".join(parts)
    else:
        return ""

    m = _USER_QUERY_RE.search(raw)
    if m:
        return m.group(1).strip()

    # Skip chrome-only payloads (system reminders, open files, etc.) with no query.
    if "<user_info>" in raw or "<open_and_recently_viewed_files>" in raw:
        return ""
    return raw.strip()


def _project_slug(cwd=None):
    """Cursor project folder name for a workspace path: ``/a/b`` → ``a-b``."""
    cwd = os.path.abspath(cwd or os.getcwd())
    return cwd.strip("/").replace("/", "-")


def _agent_transcripts_dir(slug=None):
    """``~/.cursor/projects/<slug>/agent-transcripts`` for the given (or cwd) slug."""
    slug = slug or _project_slug()
    return os.path.join(
        os.path.expanduser("~"), ".cursor", "projects", slug, "agent-transcripts"
    )


def default_transcript():
    """Newest parent (non-subagent) Cursor transcript for the current project."""
    root = _agent_transcripts_dir()
    if not os.path.isdir(root):
        return None
    # Parent chats: <uuid>/<uuid>.jsonl — exclude …/subagents/*.jsonl
    cands = [
        p
        for p in glob.glob(os.path.join(root, "*", "*.jsonl"))
        if f"{os.sep}subagents{os.sep}" not in p
    ]
    cands.sort(key=os.path.getmtime)
    return cands[-1] if cands else None


def read_entries(path):
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def _emit_todowrite(events, inp):
    for todo in inp.get("todos") or []:
        if not isinstance(todo, dict):
            continue
        subject = todo.get("content") or todo.get("id")
        if subject:
            events.append({"t": "todo_create", "subject": subject})
        tid = todo.get("id")
        if tid is not None or todo.get("status"):
            events.append(
                {
                    "t": "todo_update",
                    "task_id": str(tid or ""),
                    "status": todo.get("status"),
                }
            )


def parse(entries):
    # 1. tool results by tool_use_id (rarely present in Cursor exports)
    results = {}
    for e in entries:
        role = e.get("role") or e.get("type")
        if role not in ("user", "tool"):
            continue
        content = (e.get("message") or {}).get("content")
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    body = b.get("content")
                    if isinstance(body, list):
                        body = " ".join(
                            x.get("text", "") for x in body if isinstance(x, dict)
                        )
                    results[b.get("tool_use_id")] = {
                        "text": body or "",
                        "error": bool(b.get("is_error")),
                    }

    # 2. walk in order → normalized events
    events, model, last_reasoning = [], "unknown", None
    for e in entries:
        role = e.get("role") or e.get("type")
        # Skip turn_ended / other status rows
        if role not in ("user", "assistant"):
            continue

        if role == "user":
            text = _directive_text((e.get("message") or {}).get("content"))
            if text:
                events.append({"t": "directive", "text": text})
            continue

        msg = e.get("message") or {}
        if model == "unknown" and msg.get("model"):
            model = msg["model"]
        content = msg.get("content") or []
        if not isinstance(content, list):
            continue

        reasoning = _reasoning(content)
        if reasoning:
            last_reasoning = reasoning

        for b in content:
            if not isinstance(b, dict) or b.get("type") != "tool_use":
                continue
            tool, inp = b.get("name"), (b.get("input") or {})
            if not tool:
                continue

            if tool == "TodoWrite":
                _emit_todowrite(events, inp)
                continue
            if tool == "CreatePlan":
                subject = inp.get("name") or inp.get("overview")
                if subject:
                    events.append({"t": "todo_create", "subject": subject})
                for todo in inp.get("todos") or []:
                    if isinstance(todo, dict) and (todo.get("content") or todo.get("id")):
                        events.append(
                            {
                                "t": "todo_create",
                                "subject": todo.get("content") or todo.get("id"),
                            }
                        )
                continue
            if tool in SKIP_TOOLS:
                continue

            res = results.get(b.get("id"))
            rationale = reasoning or last_reasoning

            if tool == "AskQuestion":
                questions = inp.get("questions") or [{}]
                q0 = questions[0] if questions else {}
                question = (
                    q0.get("prompt")
                    or q0.get("question")
                    or inp.get("title")
                    or "decision"
                )
                events.append(
                    {
                        "t": "action",
                        "type": "ExclusiveDecision",
                        "category": "gateway",
                        "rationale": rationale,
                        "decision": {"question": question},
                        "result": res["text"] if res else None,
                        "error": bool(res and res["error"]),
                    }
                )
                continue

            events.append(
                {
                    "t": "action",
                    "type": _action_type(tool, inp),
                    "category": "reasoning" if tool in SEARCH_TOOLS else "activity",
                    "rationale": rationale,
                    "description": inp.get("description"),
                    "file": _file_from_input(tool, inp),
                    "is_edit": tool in EDIT_TOOLS,
                    "command": inp.get("command") if tool == "Shell" else None,
                    "query": inp.get("pattern") or inp.get("query") or inp.get("search_term"),
                    "result": res["text"] if res else None,
                    "error": bool(res and res["error"]),
                    "fallback_label": tool,
                }
            )

    return {
        "events": events,
        "model": model,
        "assistant": "ponens",
        "last_reasoning": last_reasoning,
    }

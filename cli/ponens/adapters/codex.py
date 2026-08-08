"""Codex CLI transcript adapter.

Maps a Codex CLI **rollout** transcript (JSONL under
``~/.codex/sessions/YYYY/MM/DD/rollout-<ts>-<uuid>.jsonl``) into the normalized event
stream that ``emit.build_trace`` consumes. Each rollout line is an envelope
``{"timestamp", "type", "payload"}``; the record we care about is ``response_item`` (the
OpenAI Responses stream):

- ``{type: message, role: user|assistant|developer, content: [{type: input_text|output_text, text}]}``
  — the user's prompts (role ``user``, minus ``<environment_context>``/permissions chrome) and the
  agent's narrative (role ``assistant``); ``developer`` messages are system chrome and skipped.
- ``{type: function_call, name, arguments (JSON string), call_id}`` — a tool call (``exec_command`` /
  ``shell`` for the shell, ``read_file`` / ``write_file`` / ``apply_patch`` / …).
- ``{type: custom_tool_call, name: apply_patch, input, call_id}`` and ``{type: local_shell_call, …}``
  — the free-form / shell tool variants.
- ``{type: web_search_call, action: {url}}`` — a web search.
- ``{type: (function_call|custom_tool_call)_output, call_id, output}`` — the tool result, matched to
  its call by ``call_id``. Encrypted ``reasoning`` items are skipped.

Exposes the adapter surface: NAME, IMPLEMENTED, default_transcript(), read_entries(path),
parse(entries) -> {events, model, assistant, last_reasoning}.
"""
import glob
import json
import os
import re

NAME = "codex"
IMPLEMENTED = True

# Codex tool name -> canonical trace action type. Shell tools are refined by `_shell_action`;
# apply_patch is refined (Add File -> CreateFile) by `_patch_target`.
TOOL_MAP = {
    "read_file": "ReadFile",
    "write_file": "CreateFile",
    "list_dir": "ExploreDirectory",
    "grep": "SearchCode",
    "search": "SearchCode",
    "web_search": "SearchWeb",
    "update_plan": None,  # plan bookkeeping — not part of the engineering record
}
SHELL_TOOLS = {"exec_command", "shell", "local_shell", "container.exec", "bash"}


def _shell_action(cmd):
    """Codex drives almost everything through the shell, so classify the command into a canonical
    action — reads (`cat`/`sed -n`), searches (`rg`), directory walks (`ls`/`find`), git, tests —
    instead of collapsing the whole session to `RunCommand`."""
    c = (cmd or "").strip().lower()
    if not c:
        return "RunCommand"
    if "git commit" in c:
        return "GitCommit"
    if "git diff" in c:
        return "GitDiff"
    if "git status" in c:
        return "GitStatus"
    if any(t in c for t in ("pytest", "npm test", "go test", "cargo test", "unittest", "jest")):
        return "RunTests"
    head = re.split(r"[|&;]", c, 1)[0].strip()             # first command in a pipeline
    tok = head.split()[0] if head.split() else ""
    if tok in ("rg", "grep", "ag", "ack"):
        return "SearchCode"
    if tok in ("ls", "find", "fd", "tree", "glob"):
        return "ExploreDirectory"
    if tok == "sed":
        return "ReadFile" if "-i" not in c else "EditFile"  # `sed -n` reads; `sed -i` edits
    if tok in ("cat", "head", "tail", "less", "bat", "nl", "open"):
        return "ReadFile"
    return "RunCommand"


def _patch_target(patch):
    """(action_type, file) for an apply_patch body — CreateFile for an added file, else EditFile."""
    patch = patch or ""
    add = "*** Add File:" in patch
    file = None
    for marker in ("*** Add File:", "*** Update File:", "*** Delete File:"):
        i = patch.find(marker)
        if i != -1:
            file = patch[i + len(marker):].splitlines()[0].strip()
            break
    return ("CreateFile" if add else "EditFile"), file


def _text(content):
    """Join the text of a Responses `content` block list (input_text / output_text)."""
    return "".join(b["text"] for b in (content or [])
                   if isinstance(b, dict) and b.get("text")).strip()


def _json_args(raw):
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def default_transcript():
    """The newest Codex rollout whose recorded `cwd` is the current project, if any."""
    root = os.path.join(os.path.expanduser("~"), ".codex", "sessions")
    cwd = os.path.abspath(os.getcwd())
    rollouts = sorted(glob.glob(os.path.join(root, "**", "rollout-*.jsonl"), recursive=True),
                      key=os.path.getmtime, reverse=True)
    for path in rollouts:
        try:
            with open(path) as f:
                first = json.loads(f.readline() or "{}")
        except (OSError, json.JSONDecodeError):
            continue
        if first.get("type") == "session_meta" and (first.get("payload") or {}).get("cwd") == cwd:
            return path
    return None


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


def _tool_action(p):
    """Turn a tool-call response_item payload into a partial action dict, or None to skip. Handles
    function_call / custom_tool_call / local_shell_call / web_search_call."""
    kind = p.get("type")
    call_id = p.get("call_id")
    if kind == "web_search_call":
        return {"type": "SearchWeb", "query": (p.get("action") or {}).get("url"),
                "name": "web_search", "call_id": call_id}
    if kind == "local_shell_call":
        cmd = " ".join((p.get("action") or {}).get("command") or [])
        return {"type": _shell_action(cmd), "command": cmd, "name": "shell", "call_id": call_id}
    name = p.get("name")
    if name in SHELL_TOOLS:
        cmd = _json_args(p.get("arguments")).get("cmd") or _json_args(p.get("arguments")).get("command")
        if isinstance(cmd, list):
            cmd = " ".join(cmd)
        return {"type": _shell_action(cmd), "command": cmd, "name": name, "call_id": call_id}
    if name == "apply_patch":
        body = p.get("input") if kind == "custom_tool_call" else _json_args(p.get("arguments")).get("input", "")
        atype, file = _patch_target(body)
        return {"type": atype, "file": file, "is_edit": True, "name": name, "call_id": call_id}
    if name in TOOL_MAP:
        if TOOL_MAP[name] is None:
            return None  # update_plan etc.
        args = _json_args(p.get("arguments"))
        return {"type": TOOL_MAP[name], "file": args.get("path") or args.get("file"),
                "query": args.get("pattern") or args.get("query"), "name": name, "call_id": call_id}
    # Unknown tool: keep it as a generic command so the record stays complete.
    return {"type": "RunCommand", "name": name or "tool", "call_id": call_id}


def parse(entries):
    # 1. collect tool results by call_id (function_call_output / custom_tool_call_output)
    results = {}
    for e in entries:
        if e.get("type") != "response_item":
            continue
        p = e.get("payload") or {}
        if p.get("type") in ("function_call_output", "custom_tool_call_output"):
            out = p.get("output")
            if isinstance(out, dict):
                out = out.get("content") or out.get("output") or json.dumps(out)
            results[p.get("call_id")] = str(out or "")

    # 2. walk the response stream in order -> normalized events
    events, model, last_reasoning = [], "codex", None
    for e in entries:
        et = e.get("type")
        if et in ("session_meta", "turn_context"):
            m = (e.get("payload") or {}).get("model")
            if m:
                model = m
            continue
        if et != "response_item":
            continue
        p = e.get("payload") or {}
        pt = p.get("type")

        if pt == "message":
            role, text = p.get("role"), _text(p.get("content"))
            if not text or role == "developer":
                continue                                   # system / permissions chrome
            if role == "user":
                if not text.lstrip().startswith("<"):      # skip <environment_context> / tag chrome
                    events.append({"t": "directive", "text": text})
            elif role == "assistant":
                last_reasoning = text                       # the agent's narrative before its tools
            continue

        if pt in ("function_call", "custom_tool_call", "local_shell_call", "web_search_call"):
            act = _tool_action(p)
            if not act:
                continue
            events.append({
                "t": "action",
                "type": act["type"],
                "category": "reasoning" if act["type"] in ("SearchCode", "ExploreDirectory") else "activity",
                "rationale": last_reasoning,
                "file": act.get("file"),
                "is_edit": bool(act.get("is_edit")),
                "command": act.get("command"),
                "query": act.get("query"),
                "result": results.get(act.get("call_id")),
                "error": False,
                "fallback_label": act.get("name"),
            })

    return {"events": events, "model": model, "assistant": "ponens", "last_reasoning": last_reasoning}

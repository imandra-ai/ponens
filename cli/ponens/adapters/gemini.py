"""Gemini CLI transcript adapter.

Maps a Gemini CLI **chat** transcript (JSONL under
``~/.gemini/tmp/<project>/chats/session-<ts>-<id>.jsonl``) into the normalized event stream that
``emit.build_trace`` consumes. After a one-line session header, each line is a turn:

- ``{type: user, content: [{text}]}`` — a user prompt (a directive). A ``user`` line whose content is a
  ``functionResponse`` is a tool-result echo, not a prompt, and is skipped.
- ``{type: gemini, model, content, thoughts: [...], toolCalls: [ {name, args, result/resultDisplay,
  status, displayName}, … ]}`` — the agent's narrative (``content`` / ``thoughts``) plus its tool calls.
  Unlike Claude/Codex, Gemini stores each tool's **result inside the call item**, so no id matching is
  needed. Tool names: ``read_file`` / ``write_file`` / ``replace`` / ``run_shell_command`` /
  ``grep_search`` / ``list_directory`` / ``glob`` / ``google_web_search`` / ``web_fetch`` / …

Exposes the adapter surface: NAME, IMPLEMENTED, default_transcript(), read_entries(path),
parse(entries) -> {events, model, assistant, last_reasoning}.
"""
import glob
import json
import os
import re

NAME = "gemini"
IMPLEMENTED = True

# Gemini tool name -> canonical trace action type. run_shell_command is refined by `_shell_action`.
TOOL_MAP = {
    "read_file": "ReadFile",
    "read_many_files": "ReadFile",
    "write_file": "CreateFile",
    "replace": "EditFile",
    "edit": "EditFile",
    "grep_search": "SearchCode",
    "search_file_content": "SearchCode",
    "list_directory": "ExploreDirectory",
    "glob": "ExploreDirectory",
    "google_web_search": "SearchWeb",
    "web_search": "SearchWeb",
    "web_fetch": "ReadDocumentation",
}
# Meta / bookkeeping tools that aren't part of the engineering record.
SKIP_TOOLS = {"activate_skill", "save_memory", "set_memory", "get_memory"}


def _shell_action(cmd):
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
    tok = (re.split(r"[|&;]", c, 1)[0].strip().split() or [""])[0]
    if tok in ("rg", "grep", "ag", "ack"):
        return "SearchCode"
    if tok in ("ls", "find", "fd", "tree"):
        return "ExploreDirectory"
    if tok == "sed":
        return "ReadFile" if "-i" not in c else "EditFile"
    if tok in ("cat", "head", "tail", "less", "bat", "nl"):
        return "ReadFile"
    return "RunCommand"


def default_transcript():
    """The newest Gemini chat session whose project root is the current directory, if any."""
    tmp = os.path.join(os.path.expanduser("~"), ".gemini", "tmp")
    cwd = os.path.abspath(os.getcwd())
    best, best_mtime = None, -1.0
    for root_file in glob.glob(os.path.join(tmp, "*", ".project_root")):
        try:
            proj = open(root_file).read().strip()
        except OSError:
            continue
        if os.path.abspath(proj) != cwd:
            continue
        chats = glob.glob(os.path.join(os.path.dirname(root_file), "chats", "session-*.jsonl"))
        for c in chats:
            m = os.path.getmtime(c)
            if m > best_mtime:
                best, best_mtime = c, m
    return best


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


def _user_text(content):
    """The prompt text of a `user` turn, or None when it is a tool-result echo (functionResponse)."""
    if isinstance(content, str):
        return content.strip() or None
    if not isinstance(content, list):
        return None
    if any(isinstance(b, dict) and "functionResponse" in b for b in content):
        return None                                        # a tool result echoed back, not a prompt
    text = " ".join(b["text"] for b in content if isinstance(b, dict) and b.get("text")).strip()
    return text or None


def _thoughts(entry):
    """The agent's narrative for a gemini turn — the human-facing content, else its thought summary."""
    if isinstance(entry.get("content"), str) and entry["content"].strip():
        return entry["content"].strip()
    parts = []
    for t in entry.get("thoughts") or []:
        if isinstance(t, dict):
            parts.append((t.get("subject") or "") + (": " + t["description"] if t.get("description") else ""))
    return " ".join(p for p in parts if p).strip()


def _tool_action(tc, rationale):
    """One Gemini toolCall item -> an `action` event, or None to skip."""
    name = tc.get("name") or tc.get("content")             # older logs put the name in `content`
    if not name or name in SKIP_TOOLS:
        return None
    args = tc.get("args") if isinstance(tc.get("args"), dict) else {}
    if not args and isinstance(tc.get("args"), str):
        try:
            args = json.loads(tc["args"])
        except json.JSONDecodeError:
            args = {}
    cmd = args.get("command")
    atype = _shell_action(cmd) if name == "run_shell_command" else TOOL_MAP.get(name, "RunCommand")
    result = tc.get("resultDisplay")
    if not isinstance(result, str):
        result = json.dumps(tc.get("result")) if tc.get("result") is not None else None
    return {
        "t": "action",
        "type": atype,
        "category": "reasoning" if atype in ("SearchCode", "ExploreDirectory") else "activity",
        "rationale": rationale,
        "file": args.get("absolute_path") or args.get("file_path") or args.get("path"),
        "is_edit": atype in ("EditFile", "CreateFile"),
        "command": cmd,
        "query": args.get("pattern") or args.get("query"),
        "description": tc.get("description"),
        "result": result,
        "error": tc.get("status") not in (None, "success", "completed"),
        "fallback_label": tc.get("displayName") or name,
    }


def parse(entries):
    events, model, last_reasoning = [], "gemini", None
    for e in entries:
        et = e.get("type")
        if et == "user":
            text = _user_text(e.get("content"))
            if text:
                events.append({"t": "directive", "text": text})
            continue
        if et != "gemini":
            continue                                       # session header / other lines
        if model == "gemini" and e.get("model"):
            model = e["model"]
        narrative = _thoughts(e)
        if narrative:
            last_reasoning = narrative
        for tc in e.get("toolCalls") or []:
            act = _tool_action(tc, last_reasoning)
            if act:
                events.append(act)

    return {"events": events, "model": model, "assistant": "ponens", "last_reasoning": last_reasoning}

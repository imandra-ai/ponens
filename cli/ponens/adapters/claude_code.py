"""Claude Code transcript adapter.

Maps a Claude Code session transcript (a JSONL of messages, each with content blocks
— text / thinking / tool_use / tool_result) into the **normalized event stream** that
`emit.build_trace` consumes. Everything Claude-specific lives here: the tool-name
vocabulary, the message/content-block shape, and the todo (TaskCreate/TaskUpdate) signal.

To support another agent, add a sibling module exposing the same surface:
    NAME, IMPLEMENTED, default_transcript(), read_entries(path), parse(entries)
`parse` returns {"events": [...], "model": str, "assistant": str, "last_reasoning": str|None},
where each event is one of:
    {"t": "directive", "text": str}                         # a user instruction
    {"t": "todo_create", "subject": str|None}               # the agent's plan
    {"t": "todo_update", "task_id": str, "status": str}
    {"t": "action", "type": ..., "category": ..., "rationale": ..., "file": ...,
     "is_edit": bool, "command": ..., "query": ..., "description": ..., "result": ...,
     "error": bool, "decision": {...}|None, "fallback_label": ...}
"""
import glob
import json
import os

NAME = "claude-code"
IMPLEMENTED = True

# Claude Code tool name -> canonical trace action type
TOOL_MAP = {
    "Read": "ReadFile",
    "Edit": "EditFile",
    "MultiEdit": "EditFile",
    "Write": "CreateFile",
    "NotebookEdit": "EditFile",
    "Grep": "SearchCode",
    "Glob": "ExploreDirectory",
    "WebSearch": "SearchWeb",
    "WebFetch": "ReadDocumentation",
    "AskUserQuestion": "AskUser",
}
# Meta/bookkeeping tools that aren't part of the engineering record.
# (TaskCreate/TaskUpdate are NOT skipped — they're the agent's plan, surfaced as todo
#  events so the core can derive PlanDeclared meta-actions; never emitted as actions.)
SKIP_TOOLS = {"TaskList", "TaskGet", "TaskOutput", "TaskStop",
              "ToolSearch", "ExitPlanMode", "EnterPlanMode", "Skill"}
FILE_TOOLS = {"Read", "Edit", "MultiEdit", "Write", "NotebookEdit"}
EDIT_TOOLS = {"Edit", "MultiEdit", "Write", "NotebookEdit"}


def _bash_action(cmd):
    c = (cmd or "").lower()
    if "git commit" in c:
        return "GitCommit"
    if "git diff" in c:
        return "GitDiff"
    if "git status" in c:
        return "GitStatus"
    if any(t in c for t in ("pytest", "npm test", "go test", "cargo test", "unittest")):
        return "RunTests"
    return "RunCommand"


def _action_type(tool, inp):
    if tool == "Bash":
        return _bash_action(inp.get("command", ""))
    return TOOL_MAP.get(tool, "RunCommand")


def _reasoning(content):
    """The agent's reasoning before its tool calls — the motivation. Prefers the
    human-facing text; falls back to the model's thinking blocks."""
    texts, thinks = [], []
    for b in content:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "tool_use":
            break
        if b.get("type") == "text" and b.get("text"):
            texts.append(b["text"].strip())
        elif b.get("type") == "thinking" and (b.get("thinking") or b.get("text")):
            thinks.append((b.get("thinking") or b.get("text")).strip())
    return " ".join(texts).strip() or " ".join(thinks).strip()


def default_transcript():
    """The newest Claude Code session transcript for the current project, if any."""
    proj = "-" + os.path.abspath(os.getcwd()).strip("/").replace("/", "-")
    d = os.path.join(os.path.expanduser("~"), ".claude", "projects", proj)
    js = sorted(glob.glob(os.path.join(d, "*.jsonl")), key=os.path.getmtime)
    return js[-1] if js else None


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


def parse(entries):
    # 1. collect tool results by tool_use_id
    results = {}
    for e in entries:
        if e.get("type") != "user":
            continue
        content = (e.get("message") or {}).get("content")
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    body = b.get("content")
                    if isinstance(body, list):
                        body = " ".join(x.get("text", "") for x in body if isinstance(x, dict))
                    results[b.get("tool_use_id")] = {"text": body or "", "error": bool(b.get("is_error"))}

    # 2. walk in order -> normalized events
    events, model, last_reasoning = [], "unknown", None
    for e in entries:
        et = e.get("type")
        if et == "user":
            c = (e.get("message") or {}).get("content")
            if isinstance(c, str) and c.strip():
                events.append({"t": "directive", "text": c.strip()})
            continue
        if et != "assistant":
            continue
        msg = e.get("message") or {}
        if model == "unknown":
            model = msg.get("model", "unknown")
        content = msg.get("content") or []
        reasoning = _reasoning(content)
        if reasoning:
            last_reasoning = reasoning
        for b in content:
            if not isinstance(b, dict) or b.get("type") != "tool_use":
                continue
            tool, inp = b.get("name"), (b.get("input") or {})
            if tool == "TaskCreate":
                events.append({"t": "todo_create", "subject": inp.get("subject") or inp.get("description")})
                continue
            if tool == "TaskUpdate":
                events.append({"t": "todo_update", "task_id": str(inp.get("taskId") or ""),
                               "status": inp.get("status")})
                continue
            if tool in SKIP_TOOLS:
                continue
            res = results.get(b.get("id"))
            rationale = reasoning or last_reasoning      # carryover; the core truncates
            if tool == "AskUserQuestion":
                q = (inp.get("questions") or [{}])[0]
                events.append({
                    "t": "action", "type": "ExclusiveDecision", "category": "gateway",
                    "rationale": rationale,
                    "decision": {"question": q.get("question") or q.get("header") or "decision"},
                    "result": res["text"] if res else None, "error": bool(res and res["error"])})
                continue
            events.append({
                "t": "action",
                "type": _action_type(tool, inp),
                "category": "reasoning" if tool in ("Grep", "Glob") else "activity",
                "rationale": rationale,
                "description": inp.get("description"),
                "file": inp.get("file_path") if tool in FILE_TOOLS else None,
                "is_edit": tool in EDIT_TOOLS,
                "command": inp.get("command") if tool == "Bash" else None,
                "query": inp.get("pattern") or inp.get("query"),
                "result": res["text"] if res else None,
                "error": bool(res and res["error"]),
                "fallback_label": tool,
            })

    return {"events": events, "model": model, "assistant": "ponens",
            "last_reasoning": last_reasoning}

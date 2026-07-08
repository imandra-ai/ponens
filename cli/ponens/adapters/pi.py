"""pi (CodeLogician) transcript adapter.

Maps a pi session transcript (a JSONL under `<project>/.pi/sessions/`, one row per event
— `session` / `model_change` / `thinking_level_change` / `message`) into the normalized
event stream that `emit.build_trace` consumes. Everything pi-specific lives here: the row
envelope (`{type:"message", message:{...}}`), the content-block shape (`text` / `thinking`
/ `toolCall`), the separate `toolResult` messages, and pi's tool vocabulary — including the
CodeLogician formal-reasoning tools (`codelogician`, `formal_verify`, `check_fidelity`, …),
which map to the canonical `Verify` action so they surface as verification evidence.

Exposes the adapter surface: NAME, IMPLEMENTED, default_transcript(), read_entries(path),
parse(entries) -> {"events", "model", "assistant", "last_reasoning"}.
"""
import glob
import json
import os

NAME = "pi"
IMPLEMENTED = True

# pi tool name -> canonical trace action type. Unlisted tools fall back to RunCommand;
# `bash` is refined by _bash_action.
TOOL_MAP = {
    "read": "ReadFile",
    "write": "CreateFile",
    "edit": "EditFile",
    "ls": "ExploreDirectory",
    "find": "ExploreDirectory",
    "grep": "SearchCode",
    # CodeLogician / ImandraX formal-reasoning tools -> Verify (formal-methods evidence)
    "codelogician": "Verify",
    "formal_verify": "Verify",
    "formal_comprehend": "Verify",
    "formal_testgen": "Verify",
    "check_fidelity": "Verify",
    "deterministic_translate": "Verify",
    # auxiliary formal tools
    "formal_lookup": "ReadFile",
    "formal_runs": "RunCommand",
    "visualize_regions": "RunCommand",
}
FILE_TOOLS = {"read", "write", "edit", "formal_lookup"}
EDIT_TOOLS = {"write", "edit"}
SEARCH_TOOLS = {"grep", "find"}


def _bash_action(cmd):
    c = (cmd or "").lower()
    if "git commit" in c:
        return "GitCommit"
    if "git diff" in c:
        return "GitDiff"
    if "git status" in c:
        return "GitStatus"
    if any(t in c for t in ("pytest", "npm test", "go test", "cargo test", "unittest", "vitest")):
        return "RunTests"
    return "RunCommand"


def _action_type(tool, inp):
    if tool == "bash":
        return _bash_action(inp.get("command", ""))
    return TOOL_MAP.get(tool, "RunCommand")


def _block_text(b):
    """Text carried by a content block (pi uses `text` for both text and thinking blocks)."""
    if not isinstance(b, dict):
        return ""
    return (b.get("text") or b.get("thinking") or "").strip()


def _reasoning(content):
    """The agent's reasoning before its tool calls — prefers the human-facing text, falls
    back to the thinking blocks. Stops at the first tool call."""
    texts, thinks = [], []
    for b in content:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "toolCall":
            break
        if b.get("type") == "text" and _block_text(b):
            texts.append(_block_text(b))
        elif b.get("type") == "thinking" and _block_text(b):
            thinks.append(_block_text(b))
    return " ".join(texts).strip() or " ".join(thinks).strip()


def default_transcript():
    """The newest MAIN pi session transcript for the current project. pi stores sessions in
    two places: a project-local `<cwd>/.pi/sessions/` (when the project sets sessionDir) and
    the global `~/.pi/agent/sessions/<slug>/` (where <slug> is the cwd path with '/'→'-',
    wrapped in '--'). We search both and take the newest. Child formal-reasoning subagent
    sessions (`*_imandra-fr-*`) are skipped in favor of the parent."""
    cwd = os.path.abspath(os.getcwd())
    slug = "--" + cwd.strip("/").replace("/", "-") + "--"
    dirs = [
        os.path.join(cwd, ".pi", "sessions"),
        os.path.join(os.path.expanduser("~"), ".pi", "agent", "sessions", slug),
    ]
    cands = [p for d in dirs for p in glob.glob(os.path.join(d, "*.jsonl"))]
    main = [p for p in cands if "imandra-fr" not in os.path.basename(p)]
    cands = main or cands
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


def _user_text(content):
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return " ".join(_block_text(b) for b in content
                        if isinstance(b, dict) and b.get("type") == "text").strip()
    return ""


def parse(entries):
    # Unwrap `message` rows into inner messages; capture the model.
    inner, model = [], "unknown"
    for e in entries:
        et = e.get("type")
        if et == "model_change" and model == "unknown":
            model = e.get("modelId") or model
        elif et == "message" and isinstance(e.get("message"), dict):
            inner.append(e["message"])

    # 1. collect tool results by toolCallId (pi emits these as role="toolResult" messages)
    results = {}
    for m in inner:
        if m.get("role") == "toolResult":
            body = m.get("content")
            if isinstance(body, list):
                body = " ".join(x.get("text", "") for x in body if isinstance(x, dict))
            results[m.get("toolCallId")] = {"text": body or "", "error": bool(m.get("isError"))}

    # 2. walk in order -> normalized events
    events, last_reasoning = [], None
    for m in inner:
        role = m.get("role")
        if role == "user":
            text = _user_text(m.get("content"))
            if text:
                events.append({"t": "directive", "text": text})
            continue
        if role != "assistant":
            continue
        if model == "unknown":
            model = m.get("model", "unknown")
        content = m.get("content") or []
        reasoning = _reasoning(content)
        if reasoning:
            last_reasoning = reasoning
        for b in content:
            if not isinstance(b, dict) or b.get("type") != "toolCall":
                continue
            tool, inp = b.get("name"), (b.get("arguments") or {})
            res = results.get(b.get("id"))
            events.append({
                "t": "action",
                "type": _action_type(tool, inp),
                "category": "reasoning" if tool in SEARCH_TOOLS else "activity",
                "rationale": reasoning or last_reasoning,      # carryover; core truncates
                "description": (inp.get("description") or inp.get("task")
                                or inp.get("operation") or inp.get("instruction")),
                "file": inp.get("path") or inp.get("file") or inp.get("iml_file"),
                "is_edit": tool in EDIT_TOOLS,
                "command": inp.get("command") if tool == "bash" else None,
                "query": inp.get("pattern") or inp.get("query"),
                "result": res["text"] if res else None,
                "error": bool(res and res["error"]),
                "fallback_label": tool,
            })

    return {"events": events, "model": model, "assistant": "ponens",
            "last_reasoning": last_reasoning}

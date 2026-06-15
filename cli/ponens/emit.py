"""Auto-emit a reasoning trace from an agent session transcript.

This is the *frictionless emission* path: instead of hand-building a trace, derive it
from what the agent already did. A per-agent **adapter** (see `ponens.adapters`) maps the
agent's native transcript into a normalized event stream; this module's agent-agnostic
core turns that stream into a trace — actions, meta-actions (§8.4), and a synthesized
lineage DAG (§7).

What is derived mechanically: actions, file targets, command results, decisions, the
trigger, files_modified, the meta-action grouping, and the artifact lineage. What is NOT
derivable and must be self-reported by the agent: the residual surface (declared gaps)
and formal proofs.
"""

import json
import os
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone

from .adapters import adapter_names, claude_code, get_adapter
from .formatting import green, gray, cyan


def _short(s, n=200):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[:n] + "…"


def _rel(p):
    """Relativize an absolute path for display — repo-relative when under the cwd,
    else home-relative (~/…) — so labels read 'spec/foo.md', not a leaked home dir."""
    if not p or not p.startswith("/"):
        return p
    try:
        rel = os.path.relpath(p, os.getcwd())
        if not rel.startswith(".."):
            return rel
    except ValueError:
        pass
    home = os.path.expanduser("~")
    if p == home or p.startswith(home + "/"):
        return "~" + p[len(home):]
    return p


# precedence for a reasoning step's headline type (most significant wins)
_TYPE_RANK = {"EditFile": 5, "CreateFile": 5, "RunTests": 4, "GitCommit": 4, "Verify": 4,
              "AskUser": 3, "RunCommand": 2, "GitDiff": 2, "GitStatus": 2,
              "SearchCode": 1, "ExploreDirectory": 1, "ReadFile": 1,
              "ReadDocumentation": 1, "SearchWeb": 1}

# Activity classes whose *consecutive runs* collapse into one reasoning step.
# Types not listed here (RunTests, GitCommit, Verify, AskUser, …) stay standalone —
# they're discrete meaningful events.
_GROUP = {
    "ReadFile": "research", "SearchCode": "research", "ExploreDirectory": "research",
    "ReadDocumentation": "research", "SearchWeb": "research",
    "EditFile": "edit", "CreateFile": "edit",
    "RunCommand": "shell",
}


def _summarize_group(grp, new_id):
    """Collapse one turn's tool calls into a single reasoning step (lossy view —
    preserves the dominant action, the file evidence, and the most informative result).
    A single action passes through verbatim so its enrichment (category, decisions,
    reproducibility) is never lost — only multi-action runs are collapsed."""
    if len(grp) == 1:
        a = dict(grp[0])
        a["id"] = new_id
        return a
    dom = max(grp, key=lambda a: _TYPE_RANK.get(a["type"], 0))["type"]
    counts = Counter(a["type"] for a in grp)
    files = list(dict.fromkeys(
        e["ref"] for a in grp for e in a.get("evidence", []) if e.get("type") == "FileRef"))

    rationale = next((a["rationale"] for a in grp
                      if a.get("rationale") and not a["rationale"].startswith("(")), None)
    if not rationale:
        rationale = "Worked on " + (", ".join(os.path.basename(f) for f in files[:3]) if files else dom)

    detail = "; ".join(f"{n}× {t}" for t, n in counts.items())
    if files:
        names = [os.path.basename(f) for f in files[:6]]
        detail += " · " + ", ".join(names) + ("…" if len(files) > 6 else "")

    result = next((a["result_summary"] for a in grp
                   if a["type"] in ("RunTests", "RunCommand") and a.get("result_summary")), None)
    if not result:
        result = next((a["result_summary"] for a in reversed(grp) if a.get("result_summary")), None)

    cats = {a.get("category") for a in grp if a.get("category")}
    category = cats.pop() if len(cats) == 1 else "activity"
    action = {
        "id": new_id, "type": dom, "category": category,
        # carry the grouping tags from the run's first action so meta-action
        # assignment survives summarization
        "_dir": grp[0].get("_dir"), "_task": grp[0].get("_task"),
        "label": _short(rationale, 80), "rationale": _short(rationale, 280),
        "detail": detail, "inputs": [], "outputs": [],
        "evidence": [{"type": "FileRef", "ref": f} for f in files],
    }
    if result:
        action["result_summary"] = result
    return action


def _groupable(a):
    """Collapsible noise vs. a discrete event worth keeping standalone. Decisions
    (gateways) and anything carrying reproducibility are kept whole."""
    return (_GROUP.get(a["type"]) is not None
            and not a.get("reproducibility")
            and a.get("category") not in ("gateway", "reasoning"))


def summarize_actions(actions):
    """Collapse consecutive runs of the same activity class (research / edit) into
    one reasoning step; keep discrete events (tests, commits, decisions, reproducible
    commands) standalone so their enrichment survives."""
    groups = []
    for i, a in enumerate(actions):
        gk = _GROUP.get(a["type"]) if _groupable(a) else None
        if gk and groups and groups[-1]["key"] == gk:
            groups[-1]["items"].append(a)
        else:
            groups.append({"key": gk or f"solo{i}", "items": [a]})
    return [_summarize_group(g["items"], idx) for idx, g in enumerate(groups, 1)]


# Acknowledgement-only directives ("yes", "ok") make poor meta-action titles —
# fall back to what the agent then did.
_TRIVIAL_DIRECTIVE = {"yes", "ok", "okay", "yep", "sure", "go", "do it", "go ahead",
                      "continue", "proceed", "let's do it", "lets do it", "let's go",
                      "do this", "do that", "sounds good", "perfect", "great", "nice", "yes please"}


def _meta_title(directive, first_action):
    d = (directive or "").strip()
    if d and d.lower().rstrip(".!") not in _TRIVIAL_DIRECTIVE and len(d) >= 12:
        return _short(d, 80)
    return _short(first_action.get("rationale") or first_action.get("label") or "Step", 80)


def _meta_actions(actions, directives, task_status):
    """Group atomic actions into meta-actions by the fidelity ladder (§8.4): an
    active todo (PlanDeclared) where one is in progress, else the user directive
    that the action followed (TurnSegmented). Consecutive same-key actions merge."""
    groups = []
    for a in actions:
        key = ("task", a["_task"]) if a.get("_task") else ("dir", a.get("_dir", -1))
        if groups and groups[-1]["key"] == key:
            groups[-1]["ids"].append(a["id"])
        else:
            groups.append({"key": key, "ids": [a["id"]], "first": a})

    metas = []
    for i, g in enumerate(groups, 1):
        kind, val = g["key"]
        if kind == "task":
            m = {"id": f"m{i}", "title": _short(val, 80), "intent": val,
                 "action_ids": g["ids"], "source": "plan_declared",
                 "status": "completed" if task_status.get(val) == "completed" else "partial"}
        else:
            d = directives[val] if 0 <= val < len(directives) else None
            m = {"id": f"m{i}", "title": _meta_title(d, g["first"]),
                 "action_ids": g["ids"], "source": "turn_segmented"}
            if d:
                m["intent"] = _short(d, 200)
        metas.append(m)
    return metas


def _synthesize_artifacts(actions):
    """Derive a lineage DAG from the actions so the data flow is visible without the
    agent hand-declaring it: each edit produces a versioned SourceCode artifact (chained
    via derived_from), test runs and commits *consume* the working set (the files edited
    since the last commit) and produce a TestResult / Commit. Wires action inputs/outputs
    so every consumed artifact has a strictly-earlier producer (data_flow_integrity holds)."""
    artifacts = []
    file_art = {}     # file path -> latest artifact id (its current version)
    working = {}       # file path -> artifact id, edited since the last commit
    n = 0

    def _new(atype, name, producer, derived=None, summary=None):
        nonlocal n
        n += 1
        art = {"artifact_id": f"art{n}", "artifact_type": atype, "name": name,
               "producer_action_id": producer}
        if derived:
            art["derived_from"] = list(dict.fromkeys(derived))
        if summary:
            art["summary"] = summary
        artifacts.append(art)
        return art["artifact_id"]

    for a in actions:
        t = a.get("type")
        files = [e["ref"] for e in a.get("evidence", []) if e.get("type") == "FileRef"]
        if t in ("EditFile", "CreateFile"):
            outs = []
            for f in files:
                prev = file_art.get(f)
                aid = _new("SourceCode", os.path.basename(f), a["id"], [prev] if prev else None)
                file_art[f] = aid
                working[f] = aid
                outs.append(aid)
            if outs:
                a["outputs"] = list(dict.fromkeys(a.get("outputs", []) + outs))
        elif t == "RunTests":
            ins = list(working.values())
            aid = _new("TestResult", _short(a.get("label", "tests"), 50), a["id"], ins or None,
                       _short(a.get("result_summary"), 200) if a.get("result_summary") else None)
            if ins:
                a["inputs"] = list(dict.fromkeys(a.get("inputs", []) + ins))
            a["outputs"] = list(dict.fromkeys(a.get("outputs", []) + [aid]))
        elif t == "GitCommit":
            ins = list(working.values())
            aid = _new("Commit", _short(a.get("label", "commit"), 50), a["id"], ins or None)
            if ins:
                a["inputs"] = list(dict.fromkeys(a.get("inputs", []) + ins))
            a["outputs"] = list(dict.fromkeys(a.get("outputs", []) + [aid]))
            working.clear()
    return artifacts


def _build_action(ev, aid, cur_dir, active_task):
    """Assemble one trace action from a normalized `action` event (adapter output)."""
    result = ev.get("result")
    result_summary = (("ERROR: " if ev.get("error") else "") + _short(result, 160)) if result is not None else None
    rationale = _short(ev.get("rationale"), 400) or f"({ev.get('type')})"

    if ev.get("decision"):
        q = (ev["decision"] or {}).get("question", "")
        return {
            "id": aid, "type": ev.get("type", "ExclusiveDecision"), "category": "gateway",
            "label": _short(q or "decision", 80), "rationale": rationale,
            "detail": "Decision: " + _short(q, 120)
                      + (" → " + _short(result_summary, 160) if result_summary else ""),
            "inputs": [], "outputs": [], "evidence": [],
            "_dir": cur_dir, "_task": active_task,
        }

    rel_file = _rel(ev.get("file")) if ev.get("file") else None
    label = _short(ev.get("description") or rel_file or ev.get("command")
                   or ev.get("query") or ev.get("fallback_label") or ev.get("type"), 80)
    action = {
        "id": aid, "type": ev.get("type"), "category": ev.get("category", "activity"),
        "label": label, "rationale": rationale,
        "inputs": [], "outputs": [], "evidence": [],
        "_dir": cur_dir, "_task": active_task,
    }
    if rel_file:
        action["evidence"].append({"type": "FileRef", "ref": rel_file})
    cmd = ev.get("command")
    if cmd:
        action["detail"] = _short(cmd, 200)
        # commands are re-runnable — capture the reproduction procedure + expected output
        action["execution"] = {"tool": "shell", "determinism": "deterministic"}
        action["reproducibility"] = {
            "status": "reproducible", "reproduction_kind": "tool_reexecution",
            "procedure": {"kind": "command", "command": cmd},
        }
        if result_summary:
            action["reproducibility"]["expected_output"] = {"result_summary": result_summary}
    if result_summary:
        action["result_summary"] = result_summary
    return action


def build_trace(parsed, title=None, summarize=False):
    """The agent-agnostic core: a normalized event stream -> a trace. `parsed` is an
    adapter's output: {"events", "model", "assistant", "last_reasoning"}."""
    events = parsed.get("events", [])
    model = parsed.get("model", "unknown")
    assistant = parsed.get("assistant", "ponens")
    last_text = parsed.get("last_reasoning")

    actions, files_modified, aid = [], [], 0
    directives, cur_dir = [], -1
    created, task_status, active_task = [], {}, None

    for ev in events:
        t = ev.get("t")
        if t == "directive":
            directives.append(_short(ev.get("text"), 200))
            cur_dir += 1
        elif t == "todo_create":
            created.append(ev.get("subject") or f"task {len(created) + 1}")
        elif t == "todo_update":
            tid, st = str(ev.get("task_id") or ""), ev.get("status")
            subj = created[int(tid) - 1] if tid.isdigit() and 0 < int(tid) <= len(created) else None
            if st == "in_progress":
                active_task = subj
            elif st in ("completed", "cancelled"):
                if subj:
                    task_status[subj] = st
                if subj == active_task:
                    active_task = None
        elif t == "action":
            aid += 1
            action = _build_action(ev, aid, cur_dir, active_task)
            if ev.get("is_edit") and action["evidence"]:
                files_modified.append(action["evidence"][0]["ref"])
            actions.append(action)

    if summarize:
        actions = summarize_actions(actions)

    # group into meta-actions, stamp each action with its meta-action, drop internal tags
    meta_actions = _meta_actions(actions, directives, task_status)
    of_action = {aidx: m["id"] for m in meta_actions for aidx in m["action_ids"]}
    for a in actions:
        if a["id"] in of_action:
            a["meta_action_id"] = of_action[a["id"]]
        for k in ("_dir", "_task"):
            a.pop(k, None)

    # derive the lineage DAG, and attribute each produced artifact to its meta-action
    artifacts = _synthesize_artifacts(actions)
    a_by_id = {a["id"]: a for a in actions}
    m_by_id = {m["id"]: m for m in meta_actions}
    for art in artifacts:
        mid = a_by_id.get(art["producer_action_id"], {}).get("meta_action_id")
        if mid and mid in m_by_id:
            m_by_id[mid].setdefault("produced_artifact_ids", []).append(art["artifact_id"])

    trigger_desc = directives[0] if directives else None
    return {
        "trace_id": f"trace-{uuid.uuid4().hex[:12]}",
        "spec_version": "1.6",
        "assistant": assistant,
        "model": model,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "title": title or (f"Session: {_short(trigger_desc, 60)}" if trigger_desc else "Agent session"),
        "trigger": {"type": "TaskReceived", "description": trigger_desc or "(no prompt found)"},
        "actions": actions,
        "meta_actions": meta_actions,
        "outcome": {"type": "ProcessCompleted", "summary": _short(last_text, 200) or "Session completed"},
        "artifacts": artifacts,
        "policies": [],
        "policy_evaluations": [],
        "residuals": [],
        "files_modified": sorted(set(files_modified)),
        "reproducibility": {
            "status": "partially_reproducible",
            "notes": "Commands/tests are tool-reexecutable (see action.reproducibility); file "
                     "edits are reproducible from the bound commit; agent decisions are non-deterministic.",
        },
        "metrics": {"total_actions": len(actions), "meta_action_count": len(meta_actions)},
    }


def transcript_to_trace(entries, title=None, summarize=False):
    """Convenience for the Claude Code format: parse raw entries, then build the trace."""
    return build_trace(claude_code.parse(entries), title=title, summarize=summarize)


def cmd_emit(args):
    try:
        adapter = get_adapter(args.source)
    except KeyError:
        print(f"Error: unknown --from '{args.source}' (choices: {', '.join(adapter_names())})",
              file=sys.stderr)
        sys.exit(1)
    if not getattr(adapter, "IMPLEMENTED", True):
        print(f"Error: the '{adapter.NAME}' adapter is not implemented yet — only "
              "'claude-code' is supported today. Contributions welcome.", file=sys.stderr)
        sys.exit(1)

    path = args.transcript or adapter.default_transcript()
    if not path:
        print(f"Error: no transcript given and none found for --from {adapter.NAME}. "
              "Pass one explicitly.", file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(path):
        print(f"Error: transcript not found: {path}", file=sys.stderr)
        sys.exit(1)

    trace = build_trace(adapter.parse(adapter.read_entries(path)),
                        title=args.title, summarize=getattr(args, "summarize", False))
    out = json.dumps(trace, indent=2, ensure_ascii=False) + "\n"

    if args.output:
        with open(args.output, "w") as f:
            f.write(out)
        print(f"{green('Emitted')} {cyan(trace['trace_id'])} → {args.output}")
        metas = trace.get("meta_actions", [])
        declared = sum(1 for m in metas if m.get("source") == "plan_declared")
        print(gray(f"  {trace['metrics']['total_actions']} actions in {len(metas)} meta-actions "
                   f"({declared} from the agent's plan) · {len(trace['artifacts'])} artifacts · "
                   f"{len(trace['files_modified'])} files · from {os.path.basename(path)}"))
        print(gray("  next: curate the narrative, declare the gaps, grade, govern — "
                   "run `ponens agent` for the full workflow."))
        if not trace.get("artifacts"):
            print(gray("  no artifacts → lineage is empty (not visualizable). Have the agent declare "
                       "what it produced/consumed and wire inputs/outputs to show the data flow."))
    else:
        sys.stdout.write(out)
    return 0


def register(subparsers):
    p = subparsers.add_parser("emit", help="Derive a trace from an agent session transcript")
    p.add_argument("transcript", nargs="?",
                   help="Path to the session transcript (default: newest for this project)")
    p.add_argument("--from", dest="source", default="claude-code", choices=adapter_names(),
                   help="Agent transcript format (only claude-code is implemented today)")
    p.add_argument("-o", "--output", help="Write the trace here (default: stdout)")
    p.add_argument("--title", help="Trace title")
    p.add_argument("--summarize", action="store_true",
                   help="Group tool calls into reasoning steps (fewer, higher-level actions)")
    p.set_defaults(func=cmd_emit)

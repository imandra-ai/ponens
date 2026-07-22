"""Langfuse → ponens.  `ponens langfuse import <trace.json>`

Ingests a Langfuse trace export (a trace with nested *observations*) and emits a ponens trace,
mapping Langfuse's model onto the trace model:

    observation (leaf)          -> action     (name→type/label, input→rationale, level→result)
    observation (has children)  -> meta_action (the phase grouping its actions)
    parentObservationId tree    -> meta nesting (parent_id) + action.meta_action_id
    startTime / endTime         -> action.timestamp (+ duration in the label)
    type GENERATION/SPAN/EVENT  -> action type (a GENERATION is an LLM call → Compute; +model in label)
    level=ERROR / statusMessage -> result_summary; metadata `ponens.inputs/outputs` -> artifact lineage

Accepts a single trace `{"id","name","observations":[...]}`, an API list `{"data":[...]}`, a bare
observation list, or one observation.
"""

import datetime
import json
import sys

from .otel import _TYPE_KEYWORDS, _csv


def _norm_ts(v):
    """A Langfuse ISO-8601 timestamp string → (sortable float, normalized ISO string)."""
    if not v:
        return (0.0, None)
    try:
        dt = datetime.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return (dt.timestamp(), dt.isoformat(timespec="milliseconds").replace("+00:00", "Z"))
    except (ValueError, TypeError):
        return (0.0, str(v))


def _summ(v, n=200):
    if v is None:
        return None
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def observations(doc):
    """Return (trace_meta, observations) from any of the accepted Langfuse shapes."""
    if isinstance(doc, list):
        return {}, [dict(o) for o in doc]
    if isinstance(doc, dict) and "observations" in doc:
        return doc, [dict(o) for o in doc["observations"]]
    if isinstance(doc, dict) and isinstance(doc.get("data"), list):
        data = doc["data"]
        if data and isinstance(data[0], dict) and "observations" in data[0]:
            return data[0], [dict(o) for o in data[0]["observations"]]
        return {}, [dict(o) for o in data]          # bare observation list under "data"
    if isinstance(doc, dict) and doc.get("type"):
        return {}, [dict(doc)]                        # a single observation
    raise ValueError("no observations found (expected a Langfuse trace with `observations`, or a list)")


def _obs_type(o):
    md = o.get("metadata") or {}
    if md.get("ponens.tool") or md.get("tool.name"):
        return "ToolCall"
    otype = (o.get("type") or "").upper()
    if otype == "GENERATION":
        return "Compute"          # an LLM call — don't name-guess it
    name = (o.get("name") or "").lower()
    for kw, t in _TYPE_KEYWORDS:
        if kw in name:
            return t
    if otype == "EVENT":
        return "ReportProgress"   # a point-in-time marker
    return "Compute"


def to_trace(doc, title=None):
    tmeta, obs = observations(doc)
    if not obs:
        raise ValueError("no observations to convert")
    for o in obs:
        o["_sort"], o["_ts"] = _norm_ts(o.get("startTime") or o.get("start_time"))
    obs.sort(key=lambda o: o["_sort"])

    by_id = {o.get("id"): o for o in obs}
    children = {}
    for o in obs:
        pid = o.get("parentObservationId") or o.get("parent_observation_id")
        if pid and pid in by_id:
            children.setdefault(pid, []).append(o)
    is_internal = {oid: bool(children.get(oid)) for oid in by_id}

    action_id, meta_id, next_a, next_m = {}, {}, 1, 1
    for o in obs:
        oid = o.get("id")
        if is_internal[oid]:
            meta_id[oid] = f"m{next_m}"; next_m += 1
        else:
            action_id[oid] = next_a; next_a += 1

    def nearest_meta(oid):
        pid = by_id[oid].get("parentObservationId") or by_id[oid].get("parent_observation_id")
        while pid and pid in by_id:
            if pid in meta_id:
                return meta_id[pid]
            pid = by_id[pid].get("parentObservationId") or by_id[pid].get("parent_observation_id")
        return None

    meta_members = {}
    for oid, aid in action_id.items():
        m = nearest_meta(oid)
        if m:
            meta_members.setdefault(m, []).append(aid)
    for m in meta_members:
        meta_members[m].sort()

    def _is_error(o):
        return str(o.get("level", "")).upper() == "ERROR"

    errored = {action_id[oid] for oid in action_id if _is_error(by_id[oid])}

    actions, meta_actions, artifacts = [], [], []
    root_name = None
    for o in obs:
        oid = o.get("id")
        md = o.get("metadata") or {}
        name = o.get("name") or o.get("type") or "observation"
        if root_name is None and not (o.get("parentObservationId") or o.get("parent_observation_id")):
            root_name = name
        if is_internal[oid]:
            aids = meta_members.get(meta_id[oid], [])
            meta_actions.append({k: v for k, v in {
                "id": meta_id[oid], "title": name,
                "intent": md.get("ponens.intent") or _summ(o.get("input")) or f"Langfuse observation: {name}",
                "action_ids": aids,
                "status": ("abandoned" if _is_error(o) else
                           "partial" if any(a in errored for a in aids) else "completed"),
                "source": "intent_inferred", "parent_id": nearest_meta(oid),
            }.items() if v not in (None, [])})
            continue

        model = o.get("model")
        _, end_iso = _norm_ts(o.get("endTime") or o.get("end_time"))
        dur = ""
        try:
            dur = f" ({round(_norm_ts(o.get('endTime'))[0] - o['_sort'], 3) * 1000:.0f}ms)"
        except Exception:
            dur = ""
        result_summary = None
        if _is_error(o):
            result_summary = "ERROR: " + (o.get("statusMessage") or "observation reported error")
        elif o.get("output") is not None:
            result_summary = _summ(o.get("output"), 160)

        typ = _obs_type(o)
        inputs, outputs = _csv(md.get("ponens.inputs")), _csv(md.get("ponens.outputs"))
        act = {k: v for k, v in {
            "id": action_id[oid],
            "type": typ,
            "category": "gateway" if typ in ("Decision", "UserApproval") else "activity",
            "label": name + (f" · {model}" if model else "") + dur,
            "rationale": md.get("ponens.rationale") or _summ(o.get("input")) or f"{name} — Langfuse {o.get('type', 'observation')} {oid}",
            "timestamp": o.get("_ts"),
            "agent": md.get("ponens.agent") or tmeta.get("userId"),
            "inputs": inputs, "outputs": outputs,
            "evidence": [{"type": "LangfuseObservation", "ref": oid}],
            "result_summary": result_summary,
            "meta_action_id": nearest_meta(oid),
        }.items() if v not in (None, [])}
        act.setdefault("inputs", [])
        act.setdefault("outputs", [])
        actions.append(act)
        for out in outputs:
            artifacts.append({"artifact_id": out, "artifact_type": "AnalysisNote", "name": out,
                              "producer_action_id": action_id[oid],
                              **({"derived_from": inputs} if inputs else {})})

    _, trace_ts = _norm_ts(tmeta.get("timestamp") or (obs[0].get("_ts")))
    trace_id = tmeta.get("id") or obs[0].get("traceId") or "langfuse-import"
    return {
        "trace_id": str(trace_id)[:60] or "langfuse-import",
        "spec_version": "1.6",
        "assistant": "langfuse",
        "timestamp": trace_ts,
        "trigger": {"type": "LangfuseTrace", "description": title or tmeta.get("name") or root_name or "Langfuse trace"},
        "outcome": {"type": "ProcessCompleted",
                    "summary": _summ(tmeta.get("output")) or f"{len(actions)} actions from {len(obs)} observations"},
        "policies": [], "policy_evaluations": [],
        "meta_actions": meta_actions, "artifacts": artifacts, "actions": actions,
    }


def cmd_langfuse_import(args):
    try:
        with open(args.file) as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"could not read Langfuse export: {e}", file=sys.stderr)
        return 1
    try:
        trace = to_trace(doc, title=getattr(args, "title", None))
    except ValueError as e:
        print(f"langfuse import: {e}", file=sys.stderr)
        return 1
    text = json.dumps(trace, indent=2, ensure_ascii=False)
    if getattr(args, "output", None):
        with open(args.output, "w") as f:
            f.write(text + "\n")
        print(f"wrote {args.output} — {len(trace['actions'])} actions, {len(trace['meta_actions'])} meta-actions")
    else:
        print(text)
    return 0


def register(subparsers):
    lf = subparsers.add_parser("langfuse", help="Bridge a Langfuse trace export into a ponens trace")
    sub = lf.add_subparsers(dest="langfuse_command", required=True)
    p = sub.add_parser("import", help="Convert a Langfuse trace (nested observations) to a ponens trace")
    p.add_argument("file", help="Langfuse trace JSON (trace with `observations`, or an observation list)")
    p.add_argument("-o", "--output", help="Write the trace here (default: stdout)")
    p.add_argument("--title", help="Trace title / trigger description")
    p.set_defaults(func=cmd_langfuse_import)

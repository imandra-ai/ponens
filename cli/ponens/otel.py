"""OpenTelemetry → ponens.  `ponens otel import <otlp.json>`

Ingests an OTLP-JSON span export and emits a ponens trace, mapping the OTel model onto the trace
model directly (the transcript-adapter stream in `ponens.emit` is linear + agent-shaped; OTel's span
*tree* and *timing* are constructed here):

    span (leaf)          -> action        (name→type/label, attributes→rationale/agent, status→result)
    span (has children)  -> meta_action   (the curated phase grouping its descendant actions)
    span start / end     -> action.timestamp  (+ duration in detail)
    span parent tree     -> meta_action nesting (parent_id) + action.meta_action_id
    span links / attrs   -> inputs/outputs + artifact lineage (via the `ponens.inputs/outputs` convention)

Accepts full OTLP/JSON (`{"resourceSpans":[...]}`), a `{"spans":[...]}` object, or a bare span list.
"""

import datetime
import json
import sys

# OTel status codes: 0 UNSET, 1 OK, 2 ERROR.
_STATUS_ERROR = 2

# Span-name / attribute keywords → a ponens action type (best-effort; falls back to "Compute").
_TYPE_KEYWORDS = [
    ("retriev", "Retrieve"), ("search", "Retrieve"), ("fetch", "Retrieve"), ("query", "Retrieve"),
    ("tool", "ToolCall"), ("rpc", "ToolCall"), ("http", "ToolCall"), ("call", "ToolCall"),
    ("approv", "UserApproval"), ("decis", "Decision"), ("gate", "Decision"),
    ("releas", "Release"), ("execut", "Release"), ("dispatch", "Release"), ("deploy", "Deploy"),
    ("commit", "GitCommit"), ("draft", "Draft"), ("comput", "Compute"), ("chat", "Compute"),
    ("generat", "Compute"), ("reason", "Compute"),
]


def _iso(nano):
    if not nano:
        return None
    try:
        return datetime.datetime.utcfromtimestamp(int(nano) / 1e9).isoformat(timespec="milliseconds") + "Z"
    except (ValueError, TypeError):
        return None


def _unwrap(v):
    """An OTLP AnyValue -> a plain Python value."""
    if not isinstance(v, dict):
        return v
    for k in ("stringValue", "boolValue"):
        if k in v:
            return v[k]
    for k in ("intValue", "doubleValue"):
        if k in v:
            try:
                return int(v[k]) if k == "intValue" else float(v[k])
            except (ValueError, TypeError):
                return v[k]
    if "arrayValue" in v:
        return [_unwrap(x) for x in (v["arrayValue"].get("values") or [])]
    if "kvlistValue" in v:
        return _attrs(v["kvlistValue"].get("values") or [])
    return v.get("value", v)


def _attrs(attr_list):
    """OTLP attribute list -> {key: value}."""
    out = {}
    for a in attr_list or []:
        if isinstance(a, dict) and "key" in a:
            out[a["key"]] = _unwrap(a.get("value"))
    return out


def flatten_spans(doc):
    """Return a flat list of spans, each annotated with its resource attributes under `_resource`."""
    if isinstance(doc, list):
        return [dict(s) for s in doc]
    if "spans" in doc and "resourceSpans" not in doc:
        return [dict(s) for s in doc["spans"]]
    spans = []
    for rs in doc.get("resourceSpans", []):
        res = _attrs((rs.get("resource") or {}).get("attributes"))
        for ss in rs.get("scopeSpans", rs.get("instrumentationLibrarySpans", [])):
            for s in ss.get("spans", []):
                s = dict(s)
                s["_resource"] = res
                spans.append(s)
    return spans


def _action_type(name, attrs):
    if attrs.get("gen_ai.tool.name") or attrs.get("rpc.method"):
        return "ToolCall"
    low = (name or "").lower()
    for kw, t in _TYPE_KEYWORDS:
        if kw in low:
            return t
    return "Compute"


def _csv(v):
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str):
        return [x.strip() for x in v.split(",") if x.strip()]
    return []


def to_trace(doc, title=None):
    spans = flatten_spans(doc)
    if not spans:
        raise ValueError("no spans found (expected OTLP resourceSpans / spans / a span list)")
    for s in spans:
        s.setdefault("startTimeUnixNano", s.get("start_time_unix_nano"))
    spans.sort(key=lambda s: int(s.get("startTimeUnixNano") or 0))

    by_id = {s.get("spanId") or s.get("span_id"): s for s in spans}
    children = {}
    for s in spans:
        pid = s.get("parentSpanId") or s.get("parent_span_id")
        if pid and pid in by_id:
            children.setdefault(pid, []).append(s)
    is_internal = {sid: bool(children.get(sid)) for sid in by_id}

    # Leaf spans → actions (sequential ids); internal spans → meta-actions.
    actions, meta_actions, artifacts = [], [], []
    action_id = {}   # spanId -> action id
    meta_id = {}     # spanId -> meta id
    next_a, next_m = 1, 1
    for s in spans:
        sid = s.get("spanId") or s.get("span_id")
        if is_internal[sid]:
            meta_id[sid] = f"m{next_m}"; next_m += 1
        else:
            action_id[sid] = next_a; next_a += 1

    def nearest_meta(sid):
        s = by_id[sid]
        pid = s.get("parentSpanId") or s.get("parent_span_id")
        while pid and pid in by_id:
            if pid in meta_id:
                return meta_id[pid]
            pid = by_id[pid].get("parentSpanId") or by_id[pid].get("parent_span_id")
        return None

    # Each leaf action belongs to its NEAREST internal ancestor (one meta each); deeper nesting is
    # carried by meta_action.parent_id — so an action is never listed under two meta-actions.
    meta_members = {}
    for sid_a, aid in action_id.items():
        m = nearest_meta(sid_a)
        if m:
            meta_members.setdefault(m, []).append(aid)
    for m in meta_members:
        meta_members[m].sort()

    def _is_error(s):
        st = s.get("status") or {}
        return st.get("code") == _STATUS_ERROR or str(st.get("code")).endswith("ERROR")

    errored_actions = {action_id[sid] for sid in action_id if _is_error(by_id[sid])}

    root_name = None
    for s in spans:
        sid = s.get("spanId") or s.get("span_id")
        attrs = _attrs(s.get("attributes"))
        res = s.get("_resource", {})
        name = s.get("name", "span")
        if root_name is None and not (s.get("parentSpanId") or s.get("parent_span_id")):
            root_name = name
        agent = attrs.get("gen_ai.agent.name") or res.get("service.name")
        start = _iso(s.get("startTimeUnixNano"))
        dur_ms = None
        try:
            dur_ms = round((int(s.get("endTimeUnixNano")) - int(s.get("startTimeUnixNano"))) / 1e6, 1)
        except (ValueError, TypeError):
            pass
        status = s.get("status") or {}
        err = status.get("code") == _STATUS_ERROR or str(status.get("code")).endswith("ERROR")
        result_summary = None
        if err:
            result_summary = "ERROR: " + (status.get("message") or "span reported error")
        elif attrs.get("ponens.result"):
            result_summary = str(attrs["ponens.result"])

        if is_internal[sid]:
            meta_actions.append({k: v for k, v in {
                "id": meta_id[sid], "title": name,
                "intent": attrs.get("ponens.intent") or f"OpenTelemetry span: {name}",
                "action_ids": meta_members.get(meta_id[sid], []),
                "status": ("abandoned" if err else
                           "partial" if any(a in errored_actions for a in meta_members.get(meta_id[sid], []))
                           else "completed"),
                "source": "intent_inferred", "parent_id": nearest_meta(sid),
            }.items() if v not in (None, [])})
            continue

        inputs, outputs = _csv(attrs.get("ponens.inputs")), _csv(attrs.get("ponens.outputs"))
        act = {k: v for k, v in {
            "id": action_id[sid],
            "type": _action_type(name, attrs),
            "category": "gateway" if _action_type(name, attrs) in ("Decision", "UserApproval") else "activity",
            "label": (f"{name} ({dur_ms}ms)" if dur_ms is not None else name),
            "rationale": attrs.get("ponens.rationale") or f"{name} — OpenTelemetry span {sid}",
            "timestamp": start,
            "agent": agent,
            "inputs": inputs, "outputs": outputs,
            "evidence": [{"type": "OtelSpan", "ref": sid}],
            "result_summary": result_summary,
            "meta_action_id": nearest_meta(sid),
        }.items() if v not in (None, [])}
        act.setdefault("inputs", [])
        act.setdefault("outputs", [])
        actions.append(act)
        for o in outputs:
            artifacts.append({"artifact_id": o, "artifact_type": "AnalysisNote", "name": o,
                              "producer_action_id": action_id[sid],
                              **({"derived_from": inputs} if inputs else {})})

    trace_id = (spans[0].get("traceId") or spans[0].get("trace_id") or "otel-import")
    return {
        "trace_id": str(trace_id)[:40] or "otel-import",
        "spec_version": "1.6",
        "assistant": "opentelemetry",
        "timestamp": _iso(spans[0].get("startTimeUnixNano")),
        "trigger": {"type": "OtelExport", "description": title or root_name or "OpenTelemetry trace"},
        "outcome": {"type": "ProcessCompleted", "summary": f"{len(actions)} actions from {len(spans)} spans"},
        "policies": [], "policy_evaluations": [],
        "meta_actions": meta_actions, "artifacts": artifacts, "actions": actions,
    }


def cmd_otel_import(args):
    try:
        with open(args.file) as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"could not read OTLP-JSON: {e}", file=sys.stderr)
        return 1
    try:
        trace = to_trace(doc, title=getattr(args, "title", None))
    except ValueError as e:
        print(f"otel import: {e}", file=sys.stderr)
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
    otel = subparsers.add_parser("otel", help="Bridge OpenTelemetry (OTLP-JSON) spans into a ponens trace")
    sub = otel.add_subparsers(dest="otel_command", required=True)
    p = sub.add_parser("import", help="Convert an OTLP-JSON span export to a ponens trace")
    p.add_argument("file", help="OTLP-JSON file (resourceSpans / spans / a span list)")
    p.add_argument("-o", "--output", help="Write the trace here (default: stdout)")
    p.add_argument("--title", help="Trace title / trigger description")
    p.set_defaults(func=cmd_otel_import)

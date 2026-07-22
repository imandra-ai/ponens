"""Tests for the OpenTelemetry → ponens bridge (`ponens otel import`)."""

import pytest

from ponens import otel

_B = 1784721600_000000000  # 2026-07-22T12:00:00Z in unix nanos


def _t(ms):
    return str(_B + ms * 1_000_000)


def _span(sid, parent, name, s, e, attrs=None, err=False):
    d = {"traceId": "trace-1", "spanId": sid, "name": name,
         "startTimeUnixNano": _t(s), "endTimeUnixNano": _t(e),
         "attributes": [{"key": k, "value": {"stringValue": v}} for k, v in (attrs or {}).items()]}
    if parent:
        d["parentSpanId"] = parent
    if err:
        d["status"] = {"code": 2, "message": "boom"}
    return d


def _otlp(spans):
    return {"resourceSpans": [{
        "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "agt"}}]},
        "scopeSpans": [{"spans": spans}]}]}


def _nested():
    return _otlp([
        _span("r", "", "root workflow", 0, 100),
        _span("a", "r", "retrieve NBBO", 0, 10, {"ponens.outputs": "snap"}),
        _span("rg", "r", "risk gate", 20, 60),
        _span("c", "rg", "risk decision", 25, 40, {"ponens.inputs": "snap", "ponens.outputs": "ok"}),
        _span("b", "r", "release order", 70, 80, {"ponens.inputs": "ok", "ponens.outputs": "ord"}),
    ])


def test_leaf_spans_become_actions_with_types_and_timestamps():
    tr = otel.to_trace(_nested())
    acts = {a["id"]: a for a in tr["actions"]}
    assert len(acts) == 3                                   # 3 leaves (r, rg are internal)
    assert acts[1]["type"] == "Retrieve" and acts[1]["timestamp"].startswith("2026-07-22T12:00:00")
    assert acts[2]["type"] == "Decision"                   # "risk decision"
    assert acts[3]["type"] == "Release"
    assert acts[1]["agent"] == "agt"                       # resource service.name → actor
    assert acts[1]["evidence"][0] == {"type": "OtelSpan", "ref": "a"}


def test_parent_spans_become_nested_meta_actions_each_action_owned_once():
    tr = otel.to_trace(_nested())
    metas = {m["id"]: m for m in tr["meta_actions"]}
    assert len(metas) == 2
    root = next(m for m in metas.values() if m["title"] == "root workflow")
    rg = next(m for m in metas.values() if m["title"] == "risk gate")
    assert rg["parent_id"] == root["id"]                   # nesting
    assert rg["action_ids"] == [2]                         # the risk decision only
    assert sorted(root["action_ids"]) == [1, 3]            # NOT 2 — it belongs to the nested meta
    # every action is in exactly one meta's action_ids
    owned = [aid for m in metas.values() for aid in m["action_ids"]]
    assert sorted(owned) == [1, 2, 3]


def test_lineage_from_ponens_io_convention():
    arts = {a["artifact_id"]: a for a in otel.to_trace(_nested())["artifacts"]}
    assert arts["ord"]["derived_from"] == ["ok"]           # release consumed "ok", produced "ord"


def test_error_status_marks_result_and_abandons_meta():
    tr = otel.to_trace(_otlp([_span("r", "", "flow", 0, 50),
                              _span("x", "r", "release order", 0, 20, {}, err=True)]))
    assert tr["actions"][0]["result_summary"].startswith("ERROR:")
    assert tr["meta_actions"][0]["status"] == "partial"    # a phase with a failed child → partial


def test_accepts_bare_span_list_and_rejects_empty():
    tr = otel.to_trace([_span("a", "", "retrieve x", 0, 10)])
    assert len(tr["actions"]) == 1 and tr["actions"][0]["type"] == "Retrieve"
    with pytest.raises(ValueError):
        otel.to_trace([])

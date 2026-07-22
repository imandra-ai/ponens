"""Tests for the Langfuse → ponens bridge (`ponens langfuse import`)."""

import pytest

from ponens import langfuse


def _obs(oid, parent, otype, name, s, e, md=None, model=None, level=None, output=None):
    d = {"id": oid, "traceId": "t", "type": otype, "name": name,
         "startTime": f"2026-07-22T12:00:00.{s:03d}Z", "endTime": f"2026-07-22T12:00:00.{e:03d}Z"}
    if parent:
        d["parentObservationId"] = parent
    if md:
        d["metadata"] = md
    if model:
        d["model"] = model
    if level:
        d["level"] = level
    if output is not None:
        d["output"] = output
    return d


def _trace():
    return {"id": "lf1", "name": "flow", "userId": "agt", "observations": [
        _obs("root", None, "SPAN", "root", 0, 300),
        _obs("o1", "root", "SPAN", "retrieve NBBO", 0, 40, {"ponens.outputs": "snap"}),
        _obs("rg", "root", "SPAN", "risk gate", 50, 120),
        _obs("o3", "rg", "EVENT", "risk decision", 60, 60, {"ponens.inputs": "snap", "ponens.outputs": "ok"}),
        _obs("o2", "root", "GENERATION", "size order", 130, 200,
             {"ponens.inputs": "ok", "ponens.outputs": "ord"}, model="gpt-4o"),
    ]}


def _by_label(tr):
    return {a["label"].split(" (")[0].split(" · ")[0]: a for a in tr["actions"]}


def test_generation_maps_to_compute_not_greedy_order_keyword():
    size = [a for a in langfuse.to_trace(_trace())["actions"] if a["label"].startswith("size order")][0]
    assert size["type"] == "Compute"          # a GENERATION LLM call, NOT "Release" from the word 'order'
    assert "gpt-4o" in size["label"]


def test_observation_types_timestamps_and_actor():
    a = _by_label(langfuse.to_trace(_trace()))
    assert a["retrieve NBBO"]["type"] == "Retrieve"
    assert a["risk decision"]["type"] == "Decision"       # EVENT named "risk decision"
    assert a["retrieve NBBO"]["timestamp"] == "2026-07-22T12:00:00.000Z"
    assert a["retrieve NBBO"]["agent"] == "agt"           # trace.userId → actor


def test_nested_meta_and_single_ownership():
    tr = langfuse.to_trace(_trace())
    metas = {m["title"]: m for m in tr["meta_actions"]}
    assert metas["risk gate"]["parent_id"] == metas["root"]["id"]
    owned = [aid for m in tr["meta_actions"] for aid in m["action_ids"]]
    assert sorted(owned) == [1, 2, 3]                     # each action owned by exactly one meta


def test_lineage_from_ponens_io_convention():
    arts = {a["artifact_id"]: a for a in langfuse.to_trace(_trace())["artifacts"]}
    assert arts["ord"]["derived_from"] == ["ok"]


def test_accepts_bare_list_and_error_level():
    tr = langfuse.to_trace([_obs("x", None, "SPAN", "release order", 0, 10, {}, level="ERROR")])
    assert tr["actions"][0]["type"] == "Release"
    assert tr["actions"][0]["result_summary"].startswith("ERROR")
    with pytest.raises(ValueError):
        langfuse.to_trace([])

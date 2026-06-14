"""Unit tests for meta-action curation (scrub the narrative; evidence stays faithful)."""

import json
import types

from ponens.trace import (cmd_meta_set, cmd_meta_merge, cmd_meta_drop, cmd_retitle,
                          load_trace, validate_trace)


def _trace(tmp_path):
    t = {"trace_id": "t",
         "actions": [{"id": i, "type": "EditFile", "rationale": "r" * 40, "meta_action_id": f"m{i}"}
                     for i in (1, 2, 3)],
         "trigger": {"type": "T"}, "outcome": {"type": "P", "summary": "old"},
         "meta_actions": [{"id": f"m{i}", "title": f"yes {i}", "action_ids": [i], "source": "turn_segmented"}
                          for i in (1, 2, 3)]}
    f = tmp_path / "t.json"
    f.write_text(json.dumps(t))
    return f


def _ns(f, **kw):
    return types.SimpleNamespace(trace_file=str(f), **kw)


def test_set_rewrites_and_marks_curated(tmp_path):
    f = _trace(tmp_path)
    assert cmd_meta_set(_ns(f, meta_id="m1", title="Build the viewer zoom",
                            intent="read at the step level", outcome="shipped", status=None)) == 0
    m = next(m for m in load_trace(str(f))["meta_actions"] if m["id"] == "m1")
    assert m["title"] == "Build the viewer zoom" and m["intent"] == "read at the step level"
    assert m["outcome"] == "shipped" and m["source"] == "curated"


def test_set_rejects_bad_status(tmp_path):
    f = _trace(tmp_path)
    assert cmd_meta_set(_ns(f, meta_id="m1", title=None, intent=None, outcome=None, status="done")) == 1


def test_merge_folds_dead_ends(tmp_path):
    f = _trace(tmp_path)
    assert cmd_meta_merge(_ns(f, into="m1", meta_ids=["m2", "m3"])) == 0
    t = load_trace(str(f))
    assert len(t["meta_actions"]) == 1
    keep = t["meta_actions"][0]
    assert keep["id"] == "m1" and keep["action_ids"] == [1, 2, 3] and keep["source"] == "curated"
    assert all(a["meta_action_id"] == "m1" for a in t["actions"])   # reassigned
    assert validate_trace(t)[0] == []                                # still well-formed


def test_drop_keeps_actions_ungrouped(tmp_path):
    f = _trace(tmp_path)
    assert cmd_meta_drop(_ns(f, meta_id="m2")) == 0
    t = load_trace(str(f))
    assert {m["id"] for m in t["meta_actions"]} == {"m1", "m3"}
    a2 = next(a for a in t["actions"] if a["id"] == 2)
    assert "meta_action_id" not in a2                                # ungrouped, not orphaned
    assert validate_trace(t)[0] == []


def test_retitle_sets_trace_headline(tmp_path):
    f = _trace(tmp_path)
    cmd_retitle(_ns(f, title="A clean title", outcome="A clean outcome"))
    t = load_trace(str(f))
    assert t["title"] == "A clean title" and t["outcome"]["summary"] == "A clean outcome"

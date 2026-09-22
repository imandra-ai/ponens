"""Attaching, listing and removing a policy on a LOCAL trace, without a hub.

`policies add --into` already existed. Its counterparts did not: a rule picked up by mistake could
only be taken out by hand-editing the record, and nothing said what rules a given record was being
judged against - which matters because no policies attached and every policy passing produce the
same silence in every downstream summary, and only one of them means anything was checked.
"""
import json
import types

import pytest

from ponens.registry import cmd_policies_add, cmd_policies_attached, cmd_policies_remove

POLICY = {
    "id": "no_refund_above_capture",
    "name": "A refund never exceeds what was captured",
    "severity": "error",
    "description": "The total refunded must never exceed the amount captured.",
    "formula": "G(action)",
    "version": "1.0.0",
}


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / ".ponens" / "policies").mkdir(parents=True)
    (tmp_path / ".ponens" / "policies" / "no_refund_above_capture.json").write_text(json.dumps(POLICY))
    (tmp_path / ".ponens" / "sources.toml").write_text(
        '[[source]]\nname = "house"\ntype = "local"\npath = ".ponens/policies"\n')
    trace = tmp_path / "t.json"
    trace.write_text(json.dumps({"trace_id": "demo", "actions": [], "artifacts": []}))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))   # keep the user-global source file out
    return trace


def _add(trace, pid="no_refund_above_capture"):
    return cmd_policies_add(types.SimpleNamespace(policy_id=pid, into=str(trace), refresh=False))


def test_a_house_policy_attaches_from_a_local_source(project):
    _add(project)
    attached = json.loads(project.read_text())["policies"]
    assert [p["policy_id"] for p in attached] == ["no_refund_above_capture"]
    assert attached[0]["source"]["source"] == "house"      # provenance, so a reviewer sees the origin


def test_attached_lists_what_the_record_is_judged_against(project, capsys):
    _add(project)
    capsys.readouterr()
    assert cmd_policies_attached(types.SimpleNamespace(trace_file=str(project))) == 0
    out = capsys.readouterr().out
    assert "no_refund_above_capture" in out and "house" in out and "error" in out


def test_attached_says_plainly_when_nothing_is_attached(project, capsys):
    assert cmd_policies_attached(types.SimpleNamespace(trace_file=str(project))) == 0
    out = capsys.readouterr().out
    assert "No policies are attached" in out
    assert "nothing to evaluate" in out
    assert "policies add" in out                           # and how to fix it


def test_remove_is_the_counterpart_of_add(project):
    _add(project)
    rc = cmd_policies_remove(types.SimpleNamespace(
        policy_id=["no_refund_above_capture"], from_=str(project)))
    assert rc == 0
    assert json.loads(project.read_text())["policies"] == []


def test_removing_something_that_is_not_there_is_an_error(project, capsys):
    _add(project)
    rc = cmd_policies_remove(types.SimpleNamespace(
        policy_id=["no_refund_above_capture", "nosuch"], from_=str(project)))
    assert rc == 1
    assert "not attached: nosuch" in capsys.readouterr().err
    assert json.loads(project.read_text())["policies"] == []   # the real one still went


def test_a_missing_trace_file_is_refused(tmp_path):
    with pytest.raises(SystemExit):
        cmd_policies_attached(types.SimpleNamespace(trace_file=str(tmp_path / "nope.json")))

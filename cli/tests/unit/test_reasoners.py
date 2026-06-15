"""Unit tests for `ponens reasoners` (the reasoner registry CLI)."""

import json
import os
import types

import ponens.reasoners as R

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
GALLERY = os.path.join(REPO, "gallery", "reasoners")


def _use_local(monkeypatch):
    monkeypatch.setenv("PONENS_REASONER_URL", GALLERY)


def test_load_catalog(monkeypatch):
    _use_local(monkeypatch)
    ids = {r["id"] for r in R.load_catalog()["reasoners"]}
    assert {"codelogician", "imandrax"} <= ids


def test_search_filters_by_kind(monkeypatch, capsys):
    _use_local(monkeypatch)
    R.cmd_reasoners_search(types.SimpleNamespace(query="", kind="smt", status=None, refresh=False, json=True))
    rows = json.loads(capsys.readouterr().out)
    assert [r["id"] for r in rows] == ["z3"]


def test_search_query_matches_tags(monkeypatch, capsys):
    _use_local(monkeypatch)
    R.cmd_reasoners_search(types.SimpleNamespace(query="tla", kind=None, status=None, refresh=False, json=True))
    rows = json.loads(capsys.readouterr().out)
    assert "tlc" in [r["id"] for r in rows]


def test_show_full_definition(monkeypatch, capsys):
    _use_local(monkeypatch)
    R.cmd_reasoners_show(types.SimpleNamespace(reasoner_id="codelogician", json=True))
    r = json.loads(capsys.readouterr().out)
    assert r["name"] == "Imandra CodeLogician"
    assert "VerificationResult" in r["produces"] and r["status"] == "available"

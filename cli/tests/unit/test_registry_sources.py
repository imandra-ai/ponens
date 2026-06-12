"""Unit tests for multi-source config, local sources, and qualified resolution."""

import json
import os
import types

import pytest

from ponens import registry as reg


@pytest.fixture
def env(tmp_path, monkeypatch):
    (tmp_path / "home").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PONENS_REGISTRY_CACHE", str(tmp_path / "cache"))
    monkeypatch.delenv("PONENS_REGISTRY_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _write_sources(root, text):
    d = root / ".ponens"
    d.mkdir(exist_ok=True)
    (d / "sources.toml").write_text(text)


def _local_policy(d, pid, **kw):
    pol = {
        "id": pid, "name": pid, "category": "workflow", "severity": "warning",
        "description": "d", "formula": "G(action -> rationale != EMPTY)",
        "domain": "general", "tags": [], "language_level": "pure_temporal",
        "examples": {"passes": "x", "fails": "y"},
    }
    pol.update(kw)
    (d / f"{pid}.json").write_text(json.dumps(pol))


# --- config -----------------------------------------------------------------

def test_default_when_no_config(env):
    srcs = reg.load_sources()
    assert [s["name"] for s in srcs] == ["community"]


def test_load_sources_from_config(env):
    (env / "p").mkdir()
    _write_sources(env, '[[source]]\nname = "team"\ntype = "local"\npath = "p"\n')
    srcs = reg.load_sources()
    assert [s["name"] for s in srcs] == ["team"]
    assert srcs[0]["type"] == "local"


def test_project_extends_and_orders(env):
    (env / "p").mkdir()
    _write_sources(env,
        '[[source]]\nname = "community"\ntype = "gallery"\nurl = "https://x/"\n\n'
        '[[source]]\nname = "team"\ntype = "local"\npath = "p"\n')
    srcs = reg.load_sources()
    assert [s["name"] for s in srcs] == ["community", "team"]
    assert srcs[0]["url"] == "https://x"  # trailing slash stripped


# --- local source -----------------------------------------------------------

def test_local_source_catalog(env):
    d = env / "p"; d.mkdir(); _local_policy(d, "r1"); _local_policy(d, "r2")
    _write_sources(env, '[[source]]\nname = "team"\ntype = "local"\npath = "p"\n')
    cat = reg.source_catalog(reg.get_source("team"))
    ids = {e["id"] for e in cat["policies"]}
    assert {"r1", "r2"} <= ids


def test_fetch_policy_from_local(env):
    d = env / "p"; d.mkdir(); _local_policy(d, "r1", description="local rule")
    _write_sources(env, '[[source]]\nname = "team"\ntype = "local"\npath = "p"\n')
    p = reg.fetch_policy_from(reg.get_source("team"), "r1")
    assert p["description"] == "local rule"


# --- qualified / unqualified resolution -------------------------------------

def test_qualified_resolve(env):
    d = env / "p"; d.mkdir(); _local_policy(d, "r1")
    _write_sources(env, '[[source]]\nname = "team"\ntype = "local"\npath = "p"\n')
    src, entry = reg.resolve("team/r1")
    assert src["name"] == "team" and entry["id"] == "r1"


def test_unqualified_resolve_single(env):
    d = env / "p"; d.mkdir(); _local_policy(d, "only")
    _write_sources(env, '[[source]]\nname = "team"\ntype = "local"\npath = "p"\n')
    src, entry = reg.resolve("only")
    assert src["name"] == "team"


def test_unqualified_ambiguous_errors(env):
    a = env / "a"; a.mkdir(); _local_policy(a, "dup")
    b = env / "b"; b.mkdir(); _local_policy(b, "dup")
    _write_sources(env,
        '[[source]]\nname = "a"\ntype = "local"\npath = "a"\n\n'
        '[[source]]\nname = "b"\ntype = "local"\npath = "b"\n')
    with pytest.raises(SystemExit):
        reg.resolve("dup")


def test_unknown_qualified_source_errors(env):
    _write_sources(env, '[[source]]\nname = "team"\ntype = "local"\npath = "p"\n')
    (env / "p").mkdir()
    with pytest.raises(SystemExit):
        reg.resolve("nope/r1")


# --- provenance through add -------------------------------------------------

def test_add_stamps_source_provenance(env):
    d = env / "a"; d.mkdir(); _local_policy(d, "r1")
    _write_sources(env, '[[source]]\nname = "acme"\ntype = "local"\npath = "a"\n')
    tf = env / "t.json"; tf.write_text(json.dumps({"trace_id": "t", "actions": []}))
    reg.cmd_policies_add(types.SimpleNamespace(policy_id="acme/r1", into=str(tf)))
    pol = json.loads(tf.read_text())["policies"][0]
    assert pol["source"]["source"] == "acme" and pol["source"]["id"] == "r1"

"""Unit tests for the registry I/O path (registry.py) against a file:// gallery.

Uses the real in-repo gallery as the default `community` source, with an isolated
HOME (no real ~/.ponens config) and a temp cache. No network, no hub.
"""

import json
import os
import types

import pytest

from ponens import registry as reg

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
GALLERY = os.path.join(REPO, "gallery", "policies")


@pytest.fixture
def reg_env(tmp_path, monkeypatch):
    (tmp_path / "home").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PONENS_REGISTRY_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("PONENS_REGISTRY_URL", f"file://{GALLERY}")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _update(source=None):
    reg.cmd_registry_update(types.SimpleNamespace(source=source))


# --- sources / config -------------------------------------------------------

def test_default_source_from_env(reg_env):
    srcs = reg.load_sources()
    assert [s["name"] for s in srcs] == ["community"]
    assert srcs[0]["type"] == "gallery" and srcs[0]["url"].startswith("file://")


def test_source_catalog_uncached_raises(reg_env):
    with pytest.raises(FileNotFoundError):
        reg.source_catalog(reg.default_source())


def test_registry_update_then_catalog(reg_env):
    _update()
    cat = reg.source_catalog(reg.default_source())
    assert cat["policy_count"] > 0


def test_fetch_policy_from_caches(reg_env):
    p = reg.fetch_policy_from(reg.default_source(), "tests_before_commit")
    assert p["id"] == "tests_before_commit"
    assert os.path.exists(os.path.join(reg._gallery_cache_dir("community"),
                                       "policies", "tests_before_commit.json"))


# --- search filter ----------------------------------------------------------

def _args(query="", category=None, severity=None, domain=None, tag=None):
    return types.SimpleNamespace(query=query, category=category, severity=severity,
                                 domain=domain, tag=tag)


def test_matches_by_query():
    entry = {"id": "tests_before_commit", "name": "Tests Before Commit",
             "description": "run tests first", "domain": "general", "tags": ["ci"]}
    assert reg._matches(entry, "tests", _args()) is True
    assert reg._matches(entry, "nonsense", _args()) is False


def test_matches_by_severity_and_domain():
    entry = {"id": "x", "name": "X", "description": "", "domain": "payments",
             "severity": "error", "tags": ["pci"]}
    assert reg._matches(entry, "", _args(severity="error")) is True
    assert reg._matches(entry, "", _args(severity="warning")) is False
    assert reg._matches(entry, "", _args(domain="react")) is False


def test_matches_by_tag():
    entry = {"id": "x", "name": "X", "description": "", "domain": "general", "tags": ["ci", "git"]}
    assert reg._matches(entry, "", _args(tag="git")) is True
    assert reg._matches(entry, "", _args(tag="nope")) is False


# --- policies add -----------------------------------------------------------

def test_policies_add_materializes_into_trace(reg_env):
    _update()
    tf = reg_env / "trace.json"
    tf.write_text(json.dumps({"trace_id": "t", "actions": [], "artifacts": []}))
    reg.cmd_policies_add(types.SimpleNamespace(policy_id="tests_before_commit", into=str(tf)))
    added = json.loads(tf.read_text())["policies"][0]
    assert added["policy_id"] == "tests_before_commit"
    assert added["name"] == "tests_before_commit"      # snake id → name for the checker
    assert added["source"]["source"] == "community"     # provenance


def test_policies_add_dedupes(reg_env):
    _update()
    tf = reg_env / "trace.json"
    tf.write_text(json.dumps({"trace_id": "t", "actions": [], "artifacts": []}))
    args = types.SimpleNamespace(policy_id="tests_before_commit", into=str(tf))
    reg.cmd_policies_add(args)
    reg.cmd_policies_add(args)
    pols = json.loads(tf.read_text())["policies"]
    assert sum(1 for p in pols if p["policy_id"] == "tests_before_commit") == 1

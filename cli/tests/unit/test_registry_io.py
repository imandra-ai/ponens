"""Unit tests for the registry I/O path (registry.py) against a file:// fixture.

Uses the real in-repo gallery served over file:// and a temp cache dir — no
network and no hub server.
"""

import json
import os
import types

import pytest

from ponens import registry as reg

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
GALLERY = os.path.join(REPO, "gallery", "policies")


@pytest.fixture
def local_registry(tmp_path, monkeypatch):
    """Point the registry at the in-repo gallery (file://) and a temp cache."""
    monkeypatch.setenv("PONENS_REGISTRY_URL", f"file://{GALLERY}")
    monkeypatch.setenv("PONENS_REGISTRY_CACHE", str(tmp_path / "cache"))
    return tmp_path


# ---------------------------------------------------------------------------
# config / env
# ---------------------------------------------------------------------------

def test_registry_url_env_strips_trailing_slash(monkeypatch):
    monkeypatch.setenv("PONENS_REGISTRY_URL", "https://example.test/gallery/")
    assert reg.registry_url() == "https://example.test/gallery"


def test_cache_dir_env_and_creates_policies_subdir(tmp_path, monkeypatch):
    monkeypatch.setenv("PONENS_REGISTRY_CACHE", str(tmp_path / "c"))
    base = reg.cache_dir()
    assert base == str(tmp_path / "c")
    assert os.path.isdir(os.path.join(base, "policies"))


# ---------------------------------------------------------------------------
# update / load / fetch
# ---------------------------------------------------------------------------

def test_registry_update_writes_catalog(local_registry, capsys):
    reg.cmd_registry_update(types.SimpleNamespace())
    cat = json.load(open(reg.catalog_path()))
    assert cat["policy_count"] > 0


def test_load_catalog_after_update(local_registry):
    reg.cmd_registry_update(types.SimpleNamespace())
    cat = reg.load_catalog()
    assert isinstance(cat["policies"], list) and cat["policies"]


def test_load_catalog_without_update_exits(local_registry):
    with pytest.raises(SystemExit):
        reg.load_catalog()


def test_fetch_policy_returns_and_caches(local_registry):
    reg.cmd_registry_update(types.SimpleNamespace())
    p = reg.fetch_policy("tests_before_commit")
    assert p["id"] == "tests_before_commit"
    assert os.path.exists(os.path.join(reg.cache_dir(), "policies", "tests_before_commit.json"))


# ---------------------------------------------------------------------------
# search filter
# ---------------------------------------------------------------------------

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
    assert reg._matches(entry, "", _args(domain="payments")) is True
    assert reg._matches(entry, "", _args(domain="react")) is False


def test_matches_by_tag():
    entry = {"id": "x", "name": "X", "description": "", "domain": "general", "tags": ["ci", "git"]}
    assert reg._matches(entry, "", _args(tag="git")) is True
    assert reg._matches(entry, "", _args(tag="nope")) is False


# ---------------------------------------------------------------------------
# policies add (materialize into a trace)
# ---------------------------------------------------------------------------

def test_policies_add_materializes_into_trace(local_registry, tmp_path):
    reg.cmd_registry_update(types.SimpleNamespace())
    trace_file = tmp_path / "trace.json"
    trace_file.write_text(json.dumps({"trace_id": "t", "actions": [], "artifacts": []}))
    reg.cmd_policies_add(types.SimpleNamespace(policy_id="tests_before_commit", into=str(trace_file)))
    trace = json.loads(trace_file.read_text())
    ids = [p["policy_id"] for p in trace["policies"]]
    assert "tests_before_commit" in ids
    # adapter maps the snake id to `name` so the checker can match it
    added = next(p for p in trace["policies"] if p["policy_id"] == "tests_before_commit")
    assert added["name"] == "tests_before_commit"
    assert added["source"]["id"] == "tests_before_commit"


def test_policies_add_dedupes(local_registry, tmp_path, capsys):
    reg.cmd_registry_update(types.SimpleNamespace())
    trace_file = tmp_path / "trace.json"
    trace_file.write_text(json.dumps({"trace_id": "t", "actions": [], "artifacts": []}))
    args = types.SimpleNamespace(policy_id="tests_before_commit", into=str(trace_file))
    reg.cmd_policies_add(args)
    reg.cmd_policies_add(args)  # second add should be a no-op
    trace = json.loads(trace_file.read_text())
    assert sum(1 for p in trace["policies"] if p["policy_id"] == "tests_before_commit") == 1

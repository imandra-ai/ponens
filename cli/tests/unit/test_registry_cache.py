"""Unit tests for the hash-checked, self-healing per-source policy cache (registry.py)."""

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


def _real(policy_id):
    return json.load(open(os.path.join(GALLERY, f"{policy_id}.json")))


def _seed_cache(content, policy_id="tests_before_commit"):
    p = os.path.join(reg._gallery_cache_dir("community"), "policies", f"{policy_id}.json")
    with open(p, "w") as f:
        json.dump(content, f)
    return p


def test_policy_hash_matches_catalog(reg_env):
    reg.cmd_registry_update(types.SimpleNamespace(source=None))
    cat = reg.source_catalog(reg.default_source())
    entry = next(e for e in cat["policies"] if e["id"] == "tests_before_commit")
    assert reg._policy_hash(_real("tests_before_commit")) == entry["hash"]


def test_matching_hash_returns_cache_without_fetch(reg_env, monkeypatch):
    real = _real("tests_before_commit")
    _seed_cache(real)
    monkeypatch.setenv("PONENS_REGISTRY_URL", "file:///nonexistent")  # a fetch would raise
    got = reg.fetch_policy_from(reg.default_source(), "tests_before_commit", reg._policy_hash(real))
    assert got["id"] == "tests_before_commit"


def test_hash_mismatch_refetches_and_heals(reg_env):
    _seed_cache({"id": "tests_before_commit", "stale": True})
    real = _real("tests_before_commit")
    got = reg.fetch_policy_from(reg.default_source(), "tests_before_commit", reg._policy_hash(real))
    assert "stale" not in got and got.get("formula")
    cached = json.load(open(os.path.join(reg._gallery_cache_dir("community"),
                                         "policies", "tests_before_commit.json")))
    assert "stale" not in cached


def test_refresh_bypasses_cache(reg_env, monkeypatch):
    real = _real("tests_before_commit")
    _seed_cache(real)
    monkeypatch.setenv("PONENS_REGISTRY_URL", "file:///nonexistent")
    with pytest.raises(RuntimeError):
        reg.fetch_policy_from(reg.default_source(), "tests_before_commit",
                              reg._policy_hash(real), refresh=True)


def test_no_expected_hash_trusts_cache(reg_env, monkeypatch):
    _seed_cache({"id": "tests_before_commit", "cached": True})
    monkeypatch.setenv("PONENS_REGISTRY_URL", "file:///nonexistent")
    got = reg.fetch_policy_from(reg.default_source(), "tests_before_commit")
    assert got["cached"] is True

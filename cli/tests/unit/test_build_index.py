"""Unit tests for the gallery catalog builder (scripts/build_index.py).

build_index.py is a repo-level script (not part of the cli package); we load it
by path. Pure functions are tested directly; staleness/--check behavior is driven
in-process against a temporary gallery via monkeypatched module globals.
"""

import importlib.util
import json
import os
import sys

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
BUILD_INDEX_PATH = os.path.join(REPO, "scripts", "build_index.py")


def _load_build_index():
    spec = importlib.util.spec_from_file_location("build_index", BUILD_INDEX_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bi = _load_build_index()


def _policy(**overrides):
    p = {
        "id": "demo_policy",
        "name": "Demo",
        "category": "workflow",
        "severity": "error",
        "description": "a demo policy",
        "formula": "G(GitCommit → P(RunTests ∧ completed))",
        "domain": "general",
        "rationale": "because",
        "tags": ["t"],
        "language_level": "pure_temporal",
        "examples": {"passes": "x", "fails": "y"},
    }
    p.update(overrides)
    return p


# ---------------------------------------------------------------------------
# hashing
# ---------------------------------------------------------------------------

def test_policy_hash_is_prefixed_and_deterministic():
    p = _policy()
    h1 = bi.policy_hash(p)
    h2 = bi.policy_hash(dict(p))
    assert h1.startswith("sha256:")
    assert h1 == h2


def test_policy_hash_ignores_downloads():
    a = bi.policy_hash(_policy(downloads=1))
    b = bi.policy_hash(_policy(downloads=9999))
    assert a == b


def test_policy_hash_changes_with_content():
    a = bi.policy_hash(_policy(description="one"))
    b = bi.policy_hash(_policy(description="two"))
    assert a != b


# ---------------------------------------------------------------------------
# formula lint
# ---------------------------------------------------------------------------

def test_lint_balanced_formula_ok():
    assert bi._lint_formula("G(a -> b)") == []


def test_lint_unbalanced_formula_errors():
    assert bi._lint_formula("G((a")
    assert bi._lint_formula("a)")


def test_lint_empty_formula_errors():
    assert bi._lint_formula("   ")


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

def test_validate_ok():
    assert bi.validate_policy(_policy(), "demo_policy.json", {"general"}) == []


def test_validate_missing_severity():
    errs = bi.validate_policy(_policy(severity=""), "demo_policy.json", {"general"})
    assert any("severity" in e for e in errs)


def test_validate_id_filename_mismatch():
    errs = bi.validate_policy(_policy(), "other_name.json", {"general"})
    assert any("filename" in e for e in errs)


def test_validate_bad_category():
    errs = bi.validate_policy(_policy(category="nonsense"), "demo_policy.json", {"general"})
    assert any("category" in e for e in errs)


def test_validate_unknown_domain():
    errs = bi.validate_policy(_policy(domain="mars"), "demo_policy.json", {"general"})
    assert any("domain" in e for e in errs)


def test_validate_missing_examples():
    errs = bi.validate_policy(_policy(examples={"passes": "x"}), "demo_policy.json", {"general"})
    assert any("examples" in e for e in errs)


# ---------------------------------------------------------------------------
# catalog construction
# ---------------------------------------------------------------------------

def test_build_catalog_shape():
    policies = [("p.json", _policy())]
    index = {"domains": {"general": {"label": "General"}}}
    cat = bi.build_catalog(policies, index)
    assert cat["policy_count"] == 1
    entry = cat["policies"][0]
    assert entry["id"] == "demo_policy"
    assert entry["hash"].startswith("sha256:")
    assert entry["reference_compiler"] in ("ok", "unsupported", "unknown")
    assert cat["categories"] == ["workflow"]
    assert cat["domains"] == {"general": {"label": "General"}}


# ---------------------------------------------------------------------------
# compiler compatibility status
# ---------------------------------------------------------------------------

def test_compiler_status_ok_for_valid_formula():
    status, _ = bi.compiler_status(_policy())
    assert status in ("ok", "unknown")  # ok when ponens importable (it is, in CI)


def test_compiler_status_unsupported_for_garbage_formula():
    status, _ = bi.compiler_status(_policy(formula="G(((("))
    assert status in ("unsupported", "unknown")


# ---------------------------------------------------------------------------
# --check staleness, driven in-process against a temp gallery
# ---------------------------------------------------------------------------

def _setup_temp_gallery(tmp_path, monkeypatch, policy):
    gdir = tmp_path / "gallery" / "policies"
    gdir.mkdir(parents=True)
    (gdir / f"{policy['id']}.json").write_text(json.dumps(policy))
    index = {"policies": [policy["id"]], "domains": {policy["domain"]: {}},
             "categories": [], "tags": []}
    (gdir / "_index.json").write_text(json.dumps(index))
    monkeypatch.setattr(bi, "POLICY_DIR", str(gdir))
    monkeypatch.setattr(bi, "INDEX_PATH", str(gdir / "_index.json"))
    monkeypatch.setattr(bi, "CATALOG_PATH", str(gdir / "_catalog.json"))
    return gdir


def test_generate_then_check_passes(tmp_path, monkeypatch):
    gdir = _setup_temp_gallery(tmp_path, monkeypatch, _policy())
    monkeypatch.setattr(sys, "argv", ["build_index.py"])
    assert bi.main() == 0
    assert (gdir / "_catalog.json").exists()
    monkeypatch.setattr(sys, "argv", ["build_index.py", "--check"])
    assert bi.main() == 0


def test_check_fails_when_catalog_stale(tmp_path, monkeypatch):
    gdir = _setup_temp_gallery(tmp_path, monkeypatch, _policy())
    monkeypatch.setattr(sys, "argv", ["build_index.py"])
    assert bi.main() == 0
    # tamper the committed catalog
    catalog = json.loads((gdir / "_catalog.json").read_text())
    catalog["policy_count"] = 999
    (gdir / "_catalog.json").write_text(json.dumps(catalog, indent=2) + "\n")
    monkeypatch.setattr(sys, "argv", ["build_index.py", "--check"])
    assert bi.main() == 1


def test_check_fails_when_id_missing_from_index(tmp_path, monkeypatch):
    gdir = _setup_temp_gallery(tmp_path, monkeypatch, _policy())
    # add a second policy file but do NOT register it in _index.json
    (gdir / "extra.json").write_text(json.dumps(_policy(id="extra")))
    monkeypatch.setattr(sys, "argv", ["build_index.py", "--check"])
    assert bi.main() == 1

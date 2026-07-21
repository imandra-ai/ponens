"""Tests for `ponens demos` — the bundled sample traces (list / get / resolve)."""

import argparse
import json

from ponens import demos


def test_manifest_loads_with_samples():
    _d, samples = demos._load_manifest()
    assert samples, "expected bundled (or dev examples/) demo samples"
    assert all("file" in s and s["file"].endswith(".json") for s in samples)


def test_resolve_by_file_stem_and_name():
    _d, samples = demos._load_manifest()
    s0 = samples[0]
    assert demos._resolve(samples, s0["file"]) is s0                 # exact file
    assert demos._resolve(samples, s0["file"][:-5]) is s0            # without .json
    assert demos._resolve(samples, s0["name"].lower()) is s0         # by display name
    assert demos._resolve(samples, "does-not-exist") is None


def test_get_writes_a_valid_trace(tmp_path):
    _d, samples = demos._load_manifest()
    out = tmp_path / "t.json"
    rc = demos.cmd_demos_get(argparse.Namespace(name=samples[0]["file"], output=str(out)))
    assert rc == 0 and out.exists()
    assert "actions" in json.loads(out.read_text())                  # a real trace


def test_get_unknown_demo_errors():
    assert demos.cmd_demos_get(argparse.Namespace(name="nope", output=None)) == 1


def test_list_json_emits_the_manifest(capsys):
    rc = demos.cmd_demos_list(argparse.Namespace(json=True))
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert isinstance(out, list) and out

"""Unit tests for YAML trace support (load, fmt, hash-equivalence)."""

import json
import sys
import types

import pytest

from ponens.trace import load_trace, cmd_fmt, _dump_yaml
from ponens.sync import content_hash

# YAML support is an optional extra (`pip install ponens[yaml]`). Skip the whole
# module when PyYAML isn't installed, rather than failing the stdlib-only run.
pytest.importorskip("yaml")


TRACE = {
    "trace_id": "trace-yaml",
    "spec_version": "1.5",
    "actions": [{"id": 1, "type": "Formalize", "rationale": "model it",
                 "detail": "line one\nline two\nline three"}],
    "artifacts": [],
}


def test_load_yaml_trace(tmp_path):
    f = tmp_path / "t.yaml"
    f.write_text(_dump_yaml(TRACE))
    assert load_trace(str(f)) == TRACE


def test_fmt_json_to_yaml_roundtrip(tmp_path):
    j = tmp_path / "t.json"
    j.write_text(json.dumps(TRACE))
    y = tmp_path / "t.yaml"
    cmd_fmt(types.SimpleNamespace(trace_file=str(j), to="yaml", output=str(y)))
    # YAML loads back to the identical content
    assert load_trace(str(y)) == TRACE


def test_yaml_uses_block_scalar_for_multiline(tmp_path):
    out = _dump_yaml(TRACE)
    assert "|-" in out or "|\n" in out or "|+" in out  # literal block style, not escaped \n
    assert "\\n" not in out                              # not an escaped one-liner


def test_hash_is_format_agnostic(tmp_path):
    j = tmp_path / "t.json"
    j.write_text(json.dumps(TRACE))
    y = tmp_path / "t.yaml"
    y.write_text(_dump_yaml(TRACE))
    assert content_hash(load_trace(str(j))) == content_hash(load_trace(str(y)))


def test_invalid_yaml_errors(tmp_path):
    f = tmp_path / "t.yaml"
    f.write_text("trace_id: [unclosed\n  bad: : :")
    with pytest.raises(SystemExit):
        load_trace(str(f))


def test_missing_pyyaml_gives_clean_error(tmp_path, monkeypatch):
    # simulate PyYAML not installed: None in sys.modules makes `import yaml` raise ImportError
    monkeypatch.setitem(sys.modules, "yaml", None)
    f = tmp_path / "t.yaml"
    f.write_text("trace_id: t\n")
    with pytest.raises(SystemExit):
        load_trace(str(f))

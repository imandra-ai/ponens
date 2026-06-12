"""Unit tests for the browser-view helpers in trace.py (#5/--web slice)."""

import json
import os
import sys

from ponens import trace as tr


# --- visualizer discovery + injection --------------------------------------

def test_find_visualizer_exists():
    p = tr._find_visualizer()
    assert p is not None
    assert p.endswith("visualizer.html")
    assert os.path.exists(p)


def test_render_viewer_html_injects_trace():
    html = tr._render_viewer_html({"trace_id": "trace-xyz", "actions": []})
    assert html is not None
    assert "loadTrace(_cliTrace)" in html
    assert "trace-xyz" in html
    assert "</body>" in html


# --- headless / browser detection ------------------------------------------

def test_can_open_browser_env_override(monkeypatch):
    monkeypatch.setenv("PONENS_NO_BROWSER", "1")
    assert tr._can_open_browser() is False


def test_can_open_browser_darwin(monkeypatch):
    monkeypatch.delenv("PONENS_NO_BROWSER", raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    assert tr._can_open_browser() is True


def test_can_open_browser_headless_linux(monkeypatch):
    monkeypatch.delenv("PONENS_NO_BROWSER", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert tr._can_open_browser() is False


def test_can_open_browser_linux_with_display(monkeypatch):
    monkeypatch.delenv("PONENS_NO_BROWSER", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("DISPLAY", ":0")
    assert tr._can_open_browser() is True


# --- launch_viewer ----------------------------------------------------------

def test_launch_viewer_headless_writes_file(monkeypatch, capsys):
    monkeypatch.setenv("PONENS_NO_BROWSER", "1")
    rc = tr.launch_viewer({"trace_id": "trace-h", "actions": []})
    out = capsys.readouterr().out
    assert rc == 0
    assert "written to" in out
    path = out.split("written to", 1)[1].split("\n")[0].strip()
    assert os.path.exists(path)
    assert "trace-h" in open(path).read()
    os.remove(path)


def test_launch_viewer_hub_target(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PONENS_NO_BROWSER", "1")
    tf = tmp_path / "t.json"
    tf.write_text(json.dumps({"trace_id": "t", "actions": []}))
    (tmp_path / "t.json.sync").write_text(
        json.dumps({"hub_trace_id": "tr_42", "content_hash": "h", "commit_sha": "c"}))
    rc = tr.launch_viewer({"trace_id": "t"}, trace_file=str(tf))
    out = capsys.readouterr().out
    assert rc == 0
    assert "Hub view:" in out and "tr_42" in out

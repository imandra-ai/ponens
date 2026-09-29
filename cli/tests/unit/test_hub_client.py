"""The hub client signs in, and `ponens push` understands a hub that already holds the work.

A hub that requires sign-in (Imandra Warrant, outside development) refused every push: nothing sent a
token. And a hub that keeps a re-push as a pointer to the record already holding the work said so,
while push printed the pointer as if it were a new record and remembered its id.
"""

import io
import json
import shutil
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from ponens import client, sync

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "stripe-demo-trace.json"


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def sent(monkeypatch):
    """Every request the client makes, answered with {}."""
    reqs = []

    def fake(req, *a, **k):
        reqs.append(req)
        return _Resp(b"{}")
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    for k in ("PONENS_HUB_URL", "PONENS_HUB_TOKEN", "WARRANT_URL", "WARRANT_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    return reqs


def test_the_token_is_sent_as_a_bearer(sent, monkeypatch):
    monkeypatch.setenv("PONENS_HUB_URL", "https://hub.example.com/")
    monkeypatch.setenv("PONENS_HUB_TOKEN", "th_secret")
    client.api("GET", "/traces")
    assert sent[0].full_url == "https://hub.example.com/api/traces"
    assert sent[0].get_header("Authorization") == "Bearer th_secret"


def test_warrant_settings_are_read_too_and_no_token_means_no_header(sent, monkeypatch):
    client.api("GET", "/traces")
    assert sent[0].get_header("Authorization") is None
    monkeypatch.setenv("WARRANT_URL", "https://warrant.example.com")
    monkeypatch.setenv("WARRANT_TOKEN", "th_w")
    client.api("GET", "/traces")
    assert sent[1].full_url == "https://warrant.example.com/api/traces"
    assert sent[1].get_header("Authorization") == "Bearer th_w"
    # PONENS_* wins when both are set.
    monkeypatch.setenv("PONENS_HUB_TOKEN", "th_p")
    client.api("GET", "/traces")
    assert sent[2].get_header("Authorization") == "Bearer th_p"


def test_a_refusal_says_which_setting_to_fix_and_never_prints_the_token(monkeypatch):
    def refuse(req, *a, **k):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"error":"Sign in"}'))
    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.delenv("PONENS_HUB_TOKEN", raising=False)
    monkeypatch.delenv("WARRANT_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="set PONENS_HUB_TOKEN"):
        client.api("GET", "/traces")
    monkeypatch.setenv("PONENS_HUB_TOKEN", "th_secret")
    with pytest.raises(RuntimeError) as e:
        client.api("GET", "/traces")
    assert "refused the token" in str(e.value) and "th_secret" not in str(e.value)


def _bound_trace(tmp_path):
    f = tmp_path / "work.json"
    shutil.copy(FIXTURE, f)
    t = json.loads(f.read_text())
    t.update({"repo": "imandra-ai/demo", "branch": "main", "commit_sha": "a" * 40})
    f.write_text(json.dumps(t))
    return f


def test_a_push_the_hub_already_holds_remembers_the_record_that_holds_it(tmp_path, monkeypatch, capsys):
    f = _bound_trace(tmp_path)
    calls = []

    def hub(method, path, body=None):
        calls.append((method, path))
        if path == "/traces":
            return {"trace_id": "tr_new", "status": "draft"}
        return {"ok": True, "duplicate_of": "tr_held", "note": "The same content is already here - this push was kept as a pointer to it."}
    monkeypatch.setattr(sync, "api", hub)
    sync.cmd_push(type("A", (), {"file": str(f), "visibility": None})())
    out = capsys.readouterr().out
    assert "Already on the hub" in out and "tr_held" in out and "tr_new" not in out
    assert sync.load_sidecar(str(f))["hub_trace_id"] == "tr_held"
    # Nothing is linked to the pointer: it is not a record of its own.
    assert not any(p.endswith("/links") for _, p in calls)


def test_a_push_the_hub_stores_is_reported_as_before(tmp_path, monkeypatch, capsys):
    f = _bound_trace(tmp_path)
    monkeypatch.setattr(sync, "api", lambda m, p, b=None: {"trace_id": "tr_new", "status": "draft"} if p == "/traces" else {"ok": True})
    sync.cmd_push(type("A", (), {"file": str(f), "visibility": None})())
    assert "Pushed" in capsys.readouterr().out
    assert sync.load_sidecar(str(f))["hub_trace_id"] == "tr_new"

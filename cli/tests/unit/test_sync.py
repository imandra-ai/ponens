"""Unit tests for the git/hub sync verbs (cli/ponens/sync.py).

bind/status/content-hash/discovery are tested against a real temporary git repo;
push/pull guard paths are tested without a hub (they exit before any network call).
"""

import json
import subprocess
import types

import pytest

from ponens import sync


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    _git("init", cwd=tmp_path)
    _git("config", "user.email", "t@t.co", cwd=tmp_path)
    _git("config", "user.name", "T", cwd=tmp_path)
    _git("remote", "add", "origin", "git@github.com:imandra-ai/demo.git", cwd=tmp_path)
    (tmp_path / "f.txt").write_text("hi")
    _git("add", ".", cwd=tmp_path)
    _git("commit", "-qm", "init", cwd=tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def args(**kw):
    return types.SimpleNamespace(**kw)


# ---------------------------------------------------------------------------
# content_hash
# ---------------------------------------------------------------------------

def test_content_hash_deterministic():
    t = {"actions": [{"id": 1}], "timestamp": "x"}
    assert sync.content_hash(t) == sync.content_hash(dict(t))


def test_content_hash_excludes_binding_and_timestamp():
    a = {"actions": [{"id": 1}], "timestamp": "t1"}
    b = {"actions": [{"id": 1}], "timestamp": "t2", "repo": "x/y",
         "branch": "main", "commit_sha": "abc", "content_hash": "sha256:old"}
    assert sync.content_hash(a) == sync.content_hash(b)


def test_content_hash_changes_with_content():
    assert sync.content_hash({"actions": [{"id": 1}]}) != sync.content_hash({"actions": [{"id": 2}]})


# ---------------------------------------------------------------------------
# _local_state
# ---------------------------------------------------------------------------

def test_local_state_unbound():
    assert sync._local_state({}, "h", "head")[0] == "unbound"


def test_local_state_dirty():
    t = {"commit_sha": "abc", "content_hash": "sha256:old"}
    assert sync._local_state(t, "sha256:new", "abc")[0] == "dirty"


def test_local_state_stale():
    t = {"commit_sha": "abc", "content_hash": "h"}
    assert sync._local_state(t, "h", "def")[0] == "stale"


def test_local_state_bound():
    t = {"commit_sha": "abc", "content_hash": "h"}
    assert sync._local_state(t, "h", "abc")[0] == "bound"


# ---------------------------------------------------------------------------
# find_trace_file / sidecar
# ---------------------------------------------------------------------------

def test_find_trace_file_explicit(tmp_path):
    f = tmp_path / "x.json"
    f.write_text("{}")
    assert sync.find_trace_file(args(file=str(f))) == str(f)


def test_find_trace_file_discovers_single(git_repo):
    d = git_repo / ".ponens"
    d.mkdir()
    (d / "t.json").write_text("{}")
    assert sync.find_trace_file(args(file=None)).endswith("t.json")


def test_find_trace_file_none_exits(git_repo):
    (git_repo / ".ponens").mkdir()
    with pytest.raises(SystemExit):
        sync.find_trace_file(args(file=None))


def test_find_trace_file_multiple_exits(git_repo):
    d = git_repo / ".ponens"
    d.mkdir()
    (d / "a.json").write_text("{}")
    (d / "b.json").write_text("{}")
    with pytest.raises(SystemExit):
        sync.find_trace_file(args(file=None))


def test_sidecar_roundtrip(tmp_path):
    f = str(tmp_path / "t.json")
    assert sync.load_sidecar(f) is None
    sync.save_sidecar(f, {"hub_trace_id": "tr_1", "content_hash": "h", "commit_sha": "c"})
    assert sync.load_sidecar(f)["hub_trace_id"] == "tr_1"


# ---------------------------------------------------------------------------
# bind (real git)
# ---------------------------------------------------------------------------

def test_bind_stamps_trace(git_repo):
    d = git_repo / ".ponens"
    d.mkdir()
    tf = d / "t.json"
    tf.write_text(json.dumps({"trace_id": "trace-abc", "actions": [], "artifacts": []}))
    sync.cmd_bind(args(file=str(tf), no_note=True))
    t = json.loads(tf.read_text())
    assert t["repo"] == "imandra-ai/demo"
    assert t["branch"] in ("main", "master")
    assert len(t["commit_sha"]) == 40
    assert t["content_hash"].startswith("sha256:")


def test_bind_writes_git_note(git_repo):
    d = git_repo / ".ponens"
    d.mkdir()
    tf = d / "t.json"
    tf.write_text(json.dumps({"trace_id": "trace-xyz", "actions": []}))
    sync.cmd_bind(args(file=str(tf), no_note=False))
    note = subprocess.run(["git", "notes", "--ref=ponens", "show", "HEAD"],
                          cwd=git_repo, capture_output=True, text=True)
    assert "Trace-Id: trace-xyz" in note.stdout


def test_bind_is_idempotent_on_same_commit(git_repo):
    d = git_repo / ".ponens"
    d.mkdir()
    tf = d / "t.json"
    tf.write_text(json.dumps({"trace_id": "trace-i", "actions": [{"id": 1}]}))
    sync.cmd_bind(args(file=str(tf), no_note=True))
    h1 = json.loads(tf.read_text())["content_hash"]
    sync.cmd_bind(args(file=str(tf), no_note=True))
    h2 = json.loads(tf.read_text())["content_hash"]
    assert h1 == h2


# ---------------------------------------------------------------------------
# push/pull guards (no hub touched)
# ---------------------------------------------------------------------------

def test_push_unbound_exits(tmp_path):
    f = tmp_path / "t.json"
    f.write_text(json.dumps({"trace_id": "t", "actions": []}))
    with pytest.raises(SystemExit):
        sync.cmd_push(args(file=str(f), visibility=None))


def test_pull_unpushed_exits(tmp_path):
    f = tmp_path / "t.json"
    f.write_text(json.dumps({"trace_id": "t", "actions": []}))
    with pytest.raises(SystemExit):
        sync.cmd_pull(args(file=str(f)))

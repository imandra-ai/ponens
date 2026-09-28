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


def test_bind_externalize_moves_inline_blobs_to_the_store(git_repo):
    from ponens import objects as ob
    d = git_repo / ".ponens"
    d.mkdir()
    objdir = git_repo / ".ponens" / "objects"
    tf = d / "t.json"
    tf.write_text(json.dumps({"trace_id": "trace-ext", "actions": [], "artifacts": [
        {"artifact_id": "m1", "artifact_type": "IMLModel",
         "payload": {"iml_code": "let f x = x", "symbols": ["f"]}},
    ]}))
    sync.cmd_bind(args(file=str(tf), no_note=True, externalize=True, objects_dir=str(objdir)))
    t = json.loads(tf.read_text())
    payload = t["artifacts"][0]["payload"]
    assert "iml_code" not in payload                          # inline moved out
    assert ob.is_ref(payload["iml_code_ref"])                 # → content ref
    assert ob.get_text(payload["iml_code_ref"], str(objdir)) == "let f x = x"  # resolvable from store
    assert t["content_hash"].startswith("sha256:")            # hash computed over the externalized form


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


# ---------------------------------------------------------------------------
# push actually uploads the trace
# ---------------------------------------------------------------------------

def _record_api(monkeypatch):
    """Capture every hub call `cmd_push` makes, so a missing one is a failing test."""
    calls = []

    def fake(method, path, body=None):
        calls.append((method, path, body))
        if method == "POST" and path == "/traces":
            return {"trace_id": "tr_hub_1"}
        return {"ok": True}

    monkeypatch.setattr(sync, "api", fake)
    return calls


def test_push_uploads_the_trace_body(git_repo, monkeypatch):
    """A push must send the RECORD, not just a row about it.

    `POST /traces/{id}/content` was served by the hub from the beginning and nothing ever called
    it, so a pushed trace arrived as a title, a commit and a content hash with nothing behind them
    - the viewer, the goal and gap summary and any policy run over the artifacts all had no
    content to read. Metadata-only is the failure this test exists to catch, and it is invisible
    from the CLI side: `push` reported success either way.
    """
    trace = {"trace_id": "t", "actions": [{"id": 1}], "artifacts": [],
             "commit_sha": "a" * 40, "repo": "imandra-ai/demo", "branch": "main"}
    f = git_repo / "t.json"
    f.write_text(json.dumps(trace))
    calls = _record_api(monkeypatch)

    sync.cmd_push(args(file=str(f), visibility=None))

    content = [c for c in calls if c[0] == "POST" and c[1].endswith("/content")]
    assert content, f"push never uploaded the trace body; calls were {[(c[0], c[1]) for c in calls]}"
    assert content[0][1] == "/traces/tr_hub_1/content"
    # and the whole record, not a summary of it
    assert content[0][2]["actions"] == [{"id": 1}]


def test_push_creates_the_row_before_uploading_content(git_repo, monkeypatch):
    """Order matters: the content endpoint is addressed by the id the create call returns."""
    trace = {"trace_id": "t", "actions": [], "commit_sha": "b" * 40}
    f = git_repo / "t.json"
    f.write_text(json.dumps(trace))
    calls = _record_api(monkeypatch)

    sync.cmd_push(args(file=str(f), visibility=None))

    paths = [c[1] for c in calls if c[0] == "POST"]
    assert paths.index("/traces") < paths.index("/traces/tr_hub_1/content")

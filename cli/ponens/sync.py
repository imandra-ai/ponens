"""Git/hub sync verbs — bind, push, pull, status (see spec/CLI_SYNC_MODEL).

A trace is bound 1:1 to a git commit: `bind` stamps the trace with the repo /
branch / commit and writes a `Trace-Id` git note back onto the commit; `push`
publishes it to a hub backend; `pull` fetches collaboration state read-only;
`status` reports divergence across local file / HEAD / hub.

The local gate (`trace check`) is offline; these verbs are the network layer.
"""

import glob
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

from .client import api, hub_url
from .trace import load_trace, save_trace
from .formatting import bold, gray, red, green, yellow, cyan, magenta, underline, color_status

# Fields excluded from content_hash: transport/binding metadata, not reasoning content.
HASH_EXCLUDE = {"timestamp", "content_hash", "repo", "branch", "commit_sha"}


def _err(msg):
    print(red(f"Error: {msg}"), file=sys.stderr)
    sys.exit(1)


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ----------------------------------------------------------------------------
# Git
# ----------------------------------------------------------------------------

def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True)


def git_root():
    r = _git("rev-parse", "--show-toplevel")
    return r.stdout.strip() if r.returncode == 0 else None


def git_head():
    r = _git("rev-parse", "HEAD")
    return r.stdout.strip() if r.returncode == 0 else None


def git_branch():
    r = _git("rev-parse", "--abbrev-ref", "HEAD")
    return r.stdout.strip() if r.returncode == 0 else None


def git_remote_slug():
    r = _git("remote", "get-url", "origin")
    if r.returncode != 0:
        return ""
    m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?/?$", r.stdout.strip())
    return m.group(1) if m else ""


def write_trace_note(trace_id, sha):
    """Write a `Trace-Id` note on the commit (refs/notes/ponens), non-mutating."""
    return _git("notes", "--ref=ponens", "add", "-f", "-m", f"Trace-Id: {trace_id}", sha).returncode == 0


# ----------------------------------------------------------------------------
# Content hash & trace discovery
# ----------------------------------------------------------------------------

def content_hash(trace):
    stable = {k: v for k, v in trace.items() if k not in HASH_EXCLUDE}
    canon = json.dumps(stable, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()


def ponens_dir():
    return os.path.join(git_root() or os.getcwd(), ".ponens")


def find_trace_file(args):
    if getattr(args, "file", None):
        if not os.path.exists(args.file):
            _err(f"trace file not found: {args.file}")
        return args.file
    d = ponens_dir()
    cands = []
    for ext in ("*.json", "*.yaml", "*.yml"):
        cands += [p for p in glob.glob(os.path.join(d, ext)) if not p.endswith(".sync")]
    if len(cands) == 1:
        return cands[0]
    if not cands:
        _err(f"no trace found in {d} — pass --file or create .ponens/<trace>.json")
    _err(f"multiple traces in {d} — pass --file to choose one of: "
         + ", ".join(os.path.basename(c) for c in cands))


def _sidecar_path(trace_file):
    return trace_file + ".sync"


def load_sidecar(trace_file):
    p = _sidecar_path(trace_file)
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return None


def save_sidecar(trace_file, data):
    with open(_sidecar_path(trace_file), "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


# ----------------------------------------------------------------------------
# bind
# ----------------------------------------------------------------------------

def cmd_bind(args):
    tf = find_trace_file(args)
    trace = load_trace(tf)
    if not git_root():
        _err("not inside a git repository")
    sha, branch, slug = git_head(), git_branch(), git_remote_slug()
    if not sha:
        _err("git HEAD not found (no commits yet?)")

    trace["repo"] = slug
    trace["branch"] = branch
    trace["commit_sha"] = sha
    trace["content_hash"] = content_hash(trace)
    save_trace(tf, trace)

    tid = trace.get("trace_id", "")
    noted = False if getattr(args, "no_note", False) else write_trace_note(tid, sha)

    print(f"{green('Bound')} {cyan(tid)} → {magenta(sha[:12])}")
    print(f"  repo:   {slug or gray('(no remote)')}")
    print(f"  branch: {branch}")
    print(f"  hash:   {gray(trace['content_hash'])}")
    if noted:
        print(f"  note:   {gray('refs/notes/ponens  (Trace-Id: ' + tid + ')')}")
    print(gray("  next: ponens push"))


# ----------------------------------------------------------------------------
# status
# ----------------------------------------------------------------------------

def _local_state(trace, cur_hash, head):
    commit = trace.get("commit_sha")
    if not commit:
        return "unbound", "ponens bind"
    if trace.get("content_hash") and cur_hash != trace["content_hash"]:
        return "dirty", "content changed since bind — commit it (→ successor) or re-bind"
    if head and commit != head:
        return "stale", "HEAD moved past the bound commit — re-bind, then push a successor"
    return "bound", None


def cmd_status(args):
    tf = find_trace_file(args)
    trace = load_trace(tf)
    cur_hash = content_hash(trace)
    head = git_head()
    state, advice = _local_state(trace, cur_hash, head)

    print(f"{bold('trace')}   {cyan(trace.get('trace_id', '?'))}  ({os.path.relpath(tf)})")
    if trace.get("commit_sha"):
        marker = "" if trace["commit_sha"] == head else yellow("  ← HEAD has moved")
        print(f"commit  {magenta(trace['commit_sha'][:12])}{marker}")

    side = load_sidecar(tf)
    if state == "bound":
        if not side:
            state, advice = "bound, unpushed", "ponens push"
        elif side.get("content_hash") == cur_hash and side.get("commit_sha") == trace.get("commit_sha"):
            state = "synced"
        else:
            state, advice = "dirty", "local content differs from last push — commit (→ successor) and push"

    # hub collaboration state (best-effort; degrade gracefully if unreachable)
    hub_line = None
    if side and side.get("hub_trace_id"):
        try:
            t = api("GET", f"/traces/{side['hub_trace_id']}")
            ris = api("GET", f"/traces/{side['hub_trace_id']}/review-items")
            blocking = [r for r in (ris if isinstance(ris, list) else [])
                        if r.get("blocking") and r.get("status") != "resolved"]
            hub_line = f"hub:    {color_status(t.get('status', '?'))}"
            if blocking:
                hub_line += yellow(f"  · {len(blocking)} open blocking review item(s)")
                if state == "synced":
                    state = "behind"
                    advice = "ponens pull  (open blocking items on the hub)"
        except RuntimeError:
            hub_line = gray(f"hub:    unreachable ({hub_url()})")

    print(f"state   {bold(state)}")
    if hub_line:
        print(hub_line)
    if advice:
        print(gray(f"  → {advice}"))


# ----------------------------------------------------------------------------
# push
# ----------------------------------------------------------------------------

def cmd_push(args):
    tf = find_trace_file(args)
    trace = load_trace(tf)
    commit = trace.get("commit_sha")
    if not commit:
        _err("trace is not bound to a commit — run: ponens bind")
    cur = content_hash(trace)
    side = load_sidecar(tf)

    if side and side.get("content_hash") == cur and side.get("commit_sha") == commit:
        print(f"{gray('Already synced')} — {cyan(side['hub_trace_id'])} at {magenta(commit[:12])}")
        return

    body = {
        "title": trace.get("title") or os.path.splitext(os.path.basename(tf))[0],
        "repo": trace.get("repo", ""),
        "branch": trace.get("branch", ""),
        "commit_sha": commit,
        "task_ref": trace.get("task_ref", ""),
        "visibility": getattr(args, "visibility", None) or "org",
        "content_hash": cur,
        "active_policy_pack_ids": [],
        "summary": trace.get("summary"),
    }
    t = api("POST", "/traces", body)
    hub_id = t["trace_id"]

    # 1 trace : 1 commit — if content changed from a prior push, link the successor
    superseded = None
    if side and side.get("hub_trace_id") and side.get("content_hash") != cur:
        api("POST", f"/traces/{hub_id}/links", {
            "to_trace_id": side["hub_trace_id"],
            "relationship": "supersedes",
            "note": "Successor pushed via ponens",
        })
        superseded = side["hub_trace_id"]

    save_sidecar(tf, {"hub_trace_id": hub_id, "content_hash": cur,
                      "commit_sha": commit, "pushed_at": _now()})

    print(f"{green('Pushed')} {cyan(hub_id)}  ({color_status(t.get('status', 'shared'))})")
    if superseded:
        print(f"  supersedes {cyan(superseded)}")
    print(f"  viewer: {underline(hub_url() + '/traces/' + hub_id)}")


# ----------------------------------------------------------------------------
# pull
# ----------------------------------------------------------------------------

def cmd_pull(args):
    tf = find_trace_file(args)
    side = load_sidecar(tf)
    if not side or not side.get("hub_trace_id"):
        _err("trace has not been pushed yet — run: ponens push")
    hid = side["hub_trace_id"]

    t = api("GET", f"/traces/{hid}")
    comments = api("GET", f"/traces/{hid}/comments")
    ris = api("GET", f"/traces/{hid}/review-items")
    comments = comments if isinstance(comments, list) else []
    ris = ris if isinstance(ris, list) else []

    print(f"{bold('hub trace')}  {cyan(hid)}  ({color_status(t.get('status', '?'))})")
    print(f"comments     {len(comments)}")
    open_ris = [r for r in ris if r.get("status") != "resolved"]
    blocking = [r for r in open_ris if r.get("blocking")]
    print(f"review items {len(open_ris)} open" + (yellow(f"  · {len(blocking)} blocking") if blocking else ""))
    for r in open_ris:
        flag = red("[blocking] ") if r.get("blocking") else ""
        print(f"  {gray(r.get('review_item_id', '?'))}  {flag}{r.get('title', '')}")
    print(gray("  (read-only — pull never edits your working tree)"))


# ----------------------------------------------------------------------------
# registration
# ----------------------------------------------------------------------------

def register(subparsers):
    specs = [
        ("bind", cmd_bind, "Stamp the trace with the current git commit and write a Trace-Id note"),
        ("push", cmd_push, "Publish the bound trace to a hub backend"),
        ("pull", cmd_pull, "Fetch hub collaboration state for the trace (read-only)"),
        ("status", cmd_status, "Show divergence across local file / HEAD / hub"),
    ]
    for name, fn, help_text in specs:
        p = subparsers.add_parser(name, help=help_text)
        p.add_argument("--file", help="Path to the trace JSON (default: .ponens/<trace>.json)")
        if name == "bind":
            p.add_argument("--no-note", action="store_true",
                           help="Do not write the Trace-Id git note")
        if name == "push":
            p.add_argument("--visibility", choices=["private", "org", "shared_link"],
                           help="Trace visibility on the hub (default: org)")
        p.set_defaults(func=fn)

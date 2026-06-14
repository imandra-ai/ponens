"""ponens CLI — author, share, review, govern, and validate reasoning traces."""

import argparse
import json
import os
import platform
import subprocess
import sys

from .client import api, hub_url
from .formatting import (
    bold, gray, red, green, yellow, blue, magenta, cyan, white, underline,
    color_status, time_ago, table, heading,
)
from . import trace as trace_mod
from . import registry as registry_mod
from . import sync as sync_mod
from . import emit as emit_mod


# ── Helpers ─────────────────────────────────────────────────────


def _ensure_list(data):
    """Normalize API response to a list."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("items", [])
    return []


def _open_browser(url: str):
    plat = platform.system()
    if plat == "Darwin":
        subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif plat == "Windows":
        subprocess.Popen(["start", url], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ================================================================
# auth
# ================================================================

def cmd_auth_whoami(_args):
    data = api("GET", "/auth/current-user")
    u = data["user"]
    o = data["organization"]
    print()
    uid = u["user_id"]
    oid = o["organization_id"]
    print(f"  User:  {bold(u['name'])} {gray(f'({uid})')}")
    print(f"  Email: {u['email']}")
    print(f"  Role:  {cyan(u['role'])}")
    print(f"  Org:   {bold(o['name'])} {gray(f'({oid})')}")
    print()


def cmd_auth_switch(args):
    data = api("POST", "/auth/current-user", {"user_id": args.user_id})
    u = data["user"]
    o = data["organization"]
    print(f"Switched to {bold(u['name'])} ({u['role']}) @ {o['name']}")


def cmd_auth_users(_args):
    data = api("GET", "/auth/current-user")
    heading("Available Users")
    table(data["all_users"], [
        {"label": "ID", "get": lambda u: u["user_id"]},
        {"label": "Name", "get": lambda u: u["name"]},
        {"label": "Email", "get": lambda u: u["email"]},
        {"label": "Role", "get": lambda u: u["role"], "color": cyan},
        {"label": "Org", "get": lambda u: u["organization_id"]},
    ])
    print()
    print(gray(f"  Current: {data['user']['user_id']}  |  Switch: ponens auth switch <user_id>"))
    print()


# ================================================================
# traces
# ================================================================

def cmd_traces_list(args):
    data = _ensure_list(api("GET", "/traces"))
    if args.status:
        data = [t for t in data if t["status"] == args.status]
    if args.json:
        print(json.dumps(data, indent=2))
        return
    heading("Traces")
    table(data, [
        {"label": "ID", "get": lambda t: t["trace_id"], "color": cyan},
        {"label": "Title", "get": lambda t: t["title"][:45]},
        {"label": "Status", "get": lambda t: color_status(t["status"])},
        {"label": "Cex", "get": lambda t: t["summary"]["counterexamples"],
         "color": lambda v: red(v) if int(v) > 0 else green(v)},
        {"label": "Proofs", "get": lambda t: t["summary"]["proofs"]},
        {"label": "Tests", "get": lambda t: f"{t['summary']['tests_passed']}/{t['summary']['tests_total']}"},
        {"label": "Policy", "get": lambda t: color_status(t["summary"]["policy_status"])},
        {"label": "Updated", "get": lambda t: time_ago(t["updated_at"]), "color": gray},
    ])
    print()


def cmd_traces_show(args):
    t = api("GET", f"/traces/{args.trace_id}")
    if args.json:
        print(json.dumps(t, indent=2))
        return
    s = t["summary"]
    heading(f"Trace {t['trace_id']}")
    print(f"  Title:       {bold(t['title'])}")
    print(f"  Status:      {color_status(t['status'])}")
    print(f"  Repo:        {cyan(t['repo'])}  Branch: {t['branch']}")
    print(f"  Commit:      {gray(t['commit_sha'])}")
    print(f"  Task:        {t['task_ref']}")
    print(f"  Source:      {t['source_type']}")
    print(f"  Uploaded by: {t['uploaded_by_user_id']}")
    print(f"  Visibility:  {t['visibility']}")
    print(f"  Created:     {time_ago(t['created_at'])}  Updated: {time_ago(t['updated_at'])}")
    print()
    print(bold(white("  Summary")))
    print(f"  Policy:        {color_status(s['policy_status'])}")
    print(f"  Conformance:   {color_status(s['conformance_status'])}")
    cex = s["counterexamples"]
    print(f"  Counterex:     {red(str(cex)) if cex > 0 else green(str(cex))}")
    print(f"  Proofs:        {green(str(s['proofs']))}")
    print(f"  Regions:       {s['regions']}")
    tp, tt = s["tests_passed"], s["tests_total"]
    print(f"  Tests:         {green(f'{tp}/{tt}') if tp == tt else red(f'{tp}/{tt}')}")
    if t["active_policy_pack_ids"]:
        print()
        print(bold(white("  Policy Packs")))
        for pid in t["active_policy_pack_ids"]:
            print(f"    - {pid}")
    if t.get("latest_snapshot_id"):
        print()
        print(f"  Latest snapshot: {cyan(t['latest_snapshot_id'])}")
    print()
    print(gray(f"  View: {hub_url()}/traces/{t['trace_id']}"))
    print()


def cmd_traces_upload(args):
    file_path = os.path.abspath(args.file)
    if not os.path.exists(file_path):
        print(red(f"File not found: {file_path}"), file=sys.stderr)
        sys.exit(1)
    with open(file_path) as f:
        try:
            trace_json = json.load(f)
        except json.JSONDecodeError:
            print(red("Invalid JSON in trace file"), file=sys.stderr)
            sys.exit(1)

    body = {
        "title": args.title or os.path.splitext(os.path.basename(args.file))[0],
        "repo": args.repo or "",
        "branch": args.branch or "",
        "commit_sha": args.commit or "",
        "task_ref": args.task or "",
        "visibility": args.visibility,
        "active_policy_pack_ids": args.policy_pack or [],
        "summary": trace_json.get("summary"),
    }
    t = api("POST", "/traces", body)
    print()
    print(f"  {green('Uploaded')} trace: {bold(cyan(t['trace_id']))}")
    print(f"  Title:      {t['title']}")
    print(f"  Status:     {color_status(t['status'])}")
    viewer_url = f"{hub_url()}/traces/{t['trace_id']}"
    print(f"  Viewer URL: {underline(viewer_url)}")

    if args.policy_pack:
        for pack_id in args.policy_pack:
            api("POST", f"/traces/{t['trace_id']}/policy-packs/{pack_id}")
        print(f"  Packs:      {', '.join(args.policy_pack)}")
        runs = api("POST", f"/traces/{t['trace_id']}/policy-runs", {"policy_pack_ids": args.policy_pack})
        if isinstance(runs, list):
            print(f"  Policy runs: {', '.join(r['policy_run_id'] for r in runs)}")

    if args.related_trace and args.relation:
        api("POST", f"/traces/{t['trace_id']}/links", {
            "to_trace_id": args.related_trace,
            "relationship": args.relation,
            "note": "Created via CLI upload",
        })
        print(f"  Linked:     {t['trace_id']} {gray(args.relation)} -> {args.related_trace}")
    print()


def cmd_traces_status(args):
    t = api("PATCH", f"/traces/{args.trace_id}", {"status": args.new_status})
    print(f"{cyan(args.trace_id)} status -> {color_status(t['status'])}")


# ================================================================
# comments
# ================================================================

def cmd_comments_list(args):
    data = _ensure_list(api("GET", f"/traces/{args.trace_id}/comments"))
    if args.json:
        print(json.dumps(data, indent=2))
        return
    heading(f"Comments on {args.trace_id}")
    if not data:
        print(gray("  No comments."))
    else:
        for c in data:
            target_str = f"{c['target']['target_type']}:{c['target']['target_id']}" if c["target"]["target_id"] else c["target"]["target_type"]
            print(f"  {cyan(c['comment_id'])} {color_status(c['status'])}  {gray(c['author_user_id'])}  on {target_str}  {gray(time_ago(c['created_at']))}")
            print(f"    {c['body']}")
            if c["tags"]:
                tag_str = ", ".join(c["tags"])
                print(f"    {gray(f'tags: {tag_str}')}")
            print()


def cmd_comments_add(args):
    comment = api("POST", f"/traces/{args.trace_id}/comments", {
        "body": args.body,
        "target": {"target_type": args.target_type, "target_id": args.target_id or None},
        "tags": args.tag or [],
    })
    print(f"{green('Created')} comment {cyan(comment['comment_id'])} on {args.trace_id}")


def cmd_comments_resolve(args):
    api("PATCH", f"/traces/{args.trace_id}/comments/{args.comment_id}", {"status": "resolved"})
    print(f"{green('Resolved')} comment {cyan(args.comment_id)}")


# ================================================================
# review-items
# ================================================================

def cmd_ri_list(args):
    data = _ensure_list(api("GET", f"/traces/{args.trace_id}/review-items"))
    if args.json:
        print(json.dumps(data, indent=2))
        return
    heading(f"Review Items on {args.trace_id}")
    table(data, [
        {"label": "ID", "get": lambda r: r["review_item_id"], "color": cyan},
        {"label": "Title", "get": lambda r: r["title"][:40]},
        {"label": "Status", "get": lambda r: color_status(r["status"])},
        {"label": "Blocking", "get": lambda r: red("yes") if r["blocking"] else gray("no")},
        {"label": "Assignee", "get": lambda r: r["assignee_user_id"]},
        {"label": "Created", "get": lambda r: time_ago(r["created_at"]), "color": gray},
    ])
    print()


def cmd_ri_add(args):
    item = api("POST", f"/traces/{args.trace_id}/review-items", {
        "title": args.title,
        "body": args.body or "",
        "assignee_user_id": args.assignee or "",
        "blocking": args.blocking,
        "tags": args.tag or [],
    })
    print(f"{green('Created')} review item {cyan(item['review_item_id'])} on {args.trace_id}")
    if args.blocking:
        print(red("  This item is blocking."))


def cmd_ri_ack(args):
    api("POST", f"/traces/{args.trace_id}/review-items/{args.review_item_id}/acknowledge")
    print(f"{cyan('Acknowledged')} review item {args.review_item_id}")


def cmd_ri_resolve(args):
    api("POST", f"/traces/{args.trace_id}/review-items/{args.review_item_id}/resolve", {
        "resolution_note": args.note or "",
    })
    print(f"{green('Resolved')} review item {args.review_item_id}")


# ================================================================
# links
# ================================================================

def cmd_links_list(args):
    data = api("GET", f"/traces/{args.trace_id}/links")
    if args.json:
        print(json.dumps(data, indent=2))
        return
    heading(f"Links for {args.trace_id}")
    all_links = [
        {**l, "_dir": "out"} for l in (data.get("outgoing") or [])
    ] + [
        {**l, "_dir": "in"} for l in (data.get("incoming") or [])
    ]
    if not all_links:
        print(gray("  No links."))
    else:
        table(all_links, [
            {"label": "Dir", "get": lambda l: "->" if l["_dir"] == "out" else "<-"},
            {"label": "Relationship", "get": lambda l: l["relationship"], "color": magenta},
            {"label": "From", "get": lambda l: l["from_trace_id"], "color": cyan},
            {"label": "To", "get": lambda l: l["to_trace_id"], "color": cyan},
            {"label": "Note", "get": lambda l: (l.get("note") or "")[:50]},
            {"label": "Created", "get": lambda l: time_ago(l["created_at"]), "color": gray},
        ])
    print()


def cmd_links_add(args):
    api("POST", f"/traces/{args.from_trace_id}/links", {
        "to_trace_id": args.to_trace_id,
        "relationship": args.relationship,
        "note": args.note or "",
    })
    print(f"{green('Created')} link: {cyan(args.from_trace_id)} {magenta(args.relationship)} -> {cyan(args.to_trace_id)}")


def cmd_links_timeline(args):
    data = api("GET", f"/traces/{args.trace_id}/timeline")
    if args.json:
        print(json.dumps(data, indent=2))
        return
    heading(f"Timeline for {args.trace_id}")
    print(gray(f"  Chain traces: {', '.join(data['chain_trace_ids'])}"))
    print()
    type_colors = {
        "trace_created": blue,
        "comment": cyan,
        "review_item": magenta,
        "snapshot": yellow,
        "policy_run": green,
        "link": gray,
    }
    for entry in data["timeline"]:
        color_fn = type_colors.get(entry["type"], white)
        marker = bold("*") if entry["trace_id"] == args.trace_id else gray("o")
        print(f"  {marker} {color_fn(entry['type'].ljust(15))} {gray(time_ago(entry['timestamp']).ljust(8))}  {entry['summary']}")
    print()


# ================================================================
# packs
# ================================================================

def cmd_packs_list(args):
    query = f"?scope={args.scope}" if args.scope else ""
    data = _ensure_list(api("GET", f"/policy-packs{query}"))
    if args.json:
        print(json.dumps(data, indent=2))
        return
    heading("Policy Packs")
    table(data, [
        {"label": "ID", "get": lambda p: p["policy_pack_id"], "color": cyan},
        {"label": "Name", "get": lambda p: p["name"]},
        {"label": "Scope", "get": lambda p: p["scope"]},
        {"label": "Version", "get": lambda p: f"v{p['version']}"},
        {"label": "Status", "get": lambda p: color_status(p["status"])},
        {"label": "Policies", "get": lambda p: len(p["policy_ids"])},
        {"label": "Description", "get": lambda p: p["description"][:40]},
    ])
    print()


def cmd_packs_attach(args):
    api("POST", f"/traces/{args.trace_id}/policy-packs/{args.pack_id}")
    print(f"{green('Attached')} {cyan(args.pack_id)} to {cyan(args.trace_id)}")


def cmd_packs_detach(args):
    api("DELETE", f"/traces/{args.trace_id}/policy-packs/{args.pack_id}")
    print(f"{yellow('Detached')} {cyan(args.pack_id)} from {cyan(args.trace_id)}")


def cmd_packs_run(args):
    body = {"policy_pack_ids": args.pack} if args.pack else {}
    data = api("POST", f"/traces/{args.trace_id}/policy-runs", body)
    if isinstance(data, list):
        print(f"{green('Policy runs started')}:")
        for run in data:
            print(f"  {cyan(run['policy_run_id'])} pack={run['policy_pack_id']} -> {color_status(run['status'])}")
    else:
        print(f"{green('Policy run started')}: {json.dumps(data)}")


# ================================================================
# snapshots
# ================================================================

def cmd_snapshots_list(args):
    data = _ensure_list(api("GET", f"/traces/{args.trace_id}/snapshots"))
    if args.json:
        print(json.dumps(data, indent=2))
        return
    heading(f"Snapshots for {args.trace_id}")
    table(data, [
        {"label": "ID", "get": lambda s: s["snapshot_id"], "color": cyan},
        {"label": "Status", "get": lambda s: color_status(s["status"])},
        {"label": "Signoff", "get": lambda s: color_status(s["signoff_state"])},
        {"label": "Hash", "get": lambda s: s["trace_content_hash"]},
        {"label": "Packs", "get": lambda s: len(s["policy_pack_ids"])},
        {"label": "Created", "get": lambda s: time_ago(s["created_at"]), "color": gray},
    ])
    print()


def cmd_snapshots_create(args):
    snap = api("POST", f"/traces/{args.trace_id}/snapshots")
    print(f"{green('Created')} snapshot {cyan(snap['snapshot_id'])}")
    print(f"  Trace:   {args.trace_id}")
    print(f"  Hash:    {gray(snap['trace_content_hash'])}")
    print(f"  Signoff: {color_status(snap['signoff_state'])}")
    print(f"  Packs:   {', '.join(snap['policy_pack_ids']) or '(none)'}")


def cmd_snapshots_approve(args):
    api("POST", f"/snapshots/{args.snapshot_id}/approve", {"note": args.note})
    print(f"{green('Approved')} snapshot {cyan(args.snapshot_id)}")


# ================================================================
# activity
# ================================================================

def cmd_activity(args):
    data = _ensure_list(api("GET", "/activity"))
    if args.json:
        print(json.dumps(data, indent=2))
        return
    heading("Activity Feed")
    type_colors = {
        "trace_uploaded": blue,
        "trace_approved": green,
        "review_item_created": magenta,
        "comment_added": cyan,
        "policy_failed": red,
    }
    for item in data:
        color_fn = type_colors.get(item["type"], white)
        print(f"  {gray(time_ago(item['created_at']).ljust(8))} {color_fn(item['type'].ljust(22))} {item['summary']}")
    print()


# ================================================================
# open
# ================================================================

def cmd_open(args):
    url = f"{hub_url()}/traces/{args.trace_id}" if args.trace_id else hub_url()
    _open_browser(url)
    print(f"Opening {underline(url)}")


# ================================================================
# CLI setup
# ================================================================

def main():
    parser = argparse.ArgumentParser(
        prog="ponens",
        description="Author, share, review, govern, and validate reasoning traces",
    )
    parser.add_argument("--version", action="version", version="ponens 1.0.0")
    subparsers = parser.add_subparsers(dest="command")

    # ── auth ────────────────────────────────────────────────────
    auth = subparsers.add_parser("auth", help="Authentication and user management")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)

    auth_sub.add_parser("whoami", help="Show current user").set_defaults(func=cmd_auth_whoami)

    p = auth_sub.add_parser("switch", help="Switch to a different user")
    p.add_argument("user_id")
    p.set_defaults(func=cmd_auth_switch)

    auth_sub.add_parser("users", help="List all available users").set_defaults(func=cmd_auth_users)

    # ── traces ──────────────────────────────────────────────────
    traces = subparsers.add_parser("traces", help="Manage reasoning traces on the hub")
    traces_sub = traces.add_subparsers(dest="traces_command", required=True)

    p = traces_sub.add_parser("list", aliases=["ls"], help="List traces for current org")
    p.add_argument("-s", "--status", help="Filter by status")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.set_defaults(func=cmd_traces_list)

    p = traces_sub.add_parser("show", aliases=["get"], help="Show trace details")
    p.add_argument("trace_id")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.set_defaults(func=cmd_traces_show)

    p = traces_sub.add_parser("upload", help="Upload a new trace from a JSON file")
    p.add_argument("file", help="Path to trace JSON file")
    p.add_argument("-t", "--title", help="Trace title")
    p.add_argument("--repo", help="Repository (e.g. payments/stripe)")
    p.add_argument("--branch", help="Git branch")
    p.add_argument("--commit", help="Commit SHA")
    p.add_argument("--task", help="Task reference (e.g. TASK-381)")
    p.add_argument("--visibility", default="org", help="Visibility: private, org, shared_link")
    p.add_argument("-p", "--policy-pack", action="append", help="Attach policy pack (repeatable)")
    p.add_argument("--related-trace", help="Related trace ID")
    p.add_argument("--relation", help="Relationship type: supersedes, related_to, derived_from, same_task")
    p.set_defaults(func=cmd_traces_upload)

    p = traces_sub.add_parser("status", help="Update trace status")
    p.add_argument("trace_id")
    p.add_argument("new_status", choices=["draft", "shared", "under_review", "approved", "needs_attention", "archived"])
    p.set_defaults(func=cmd_traces_status)

    # ── comments ────────────────────────────────────────────────
    comments = subparsers.add_parser("comments", help="Manage trace comments")
    comments_sub = comments.add_subparsers(dest="comments_command", required=True)

    p = comments_sub.add_parser("list", aliases=["ls"], help="List comments on a trace")
    p.add_argument("trace_id")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.set_defaults(func=cmd_comments_list)

    p = comments_sub.add_parser("add", help="Add a comment to a trace")
    p.add_argument("trace_id")
    p.add_argument("body")
    p.add_argument("--target-type", default="trace", help="Target type: trace, action, artifact, policy")
    p.add_argument("--target-id", help="Target ID")
    p.add_argument("--tag", action="append", help="Add tag (repeatable)")
    p.set_defaults(func=cmd_comments_add)

    p = comments_sub.add_parser("resolve", help="Resolve a comment")
    p.add_argument("trace_id")
    p.add_argument("comment_id")
    p.set_defaults(func=cmd_comments_resolve)

    # ── review-items ────────────────────────────────────────────
    ri = subparsers.add_parser("review-items", aliases=["ri"], help="Manage review items")
    ri_sub = ri.add_subparsers(dest="ri_command", required=True)

    p = ri_sub.add_parser("list", aliases=["ls"], help="List review items on a trace")
    p.add_argument("trace_id")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.set_defaults(func=cmd_ri_list)

    p = ri_sub.add_parser("add", help="Create a review item")
    p.add_argument("trace_id")
    p.add_argument("title")
    p.add_argument("-b", "--body", help="Description")
    p.add_argument("-a", "--assignee", help="Assignee user ID")
    p.add_argument("--blocking", action="store_true", help="Mark as blocking")
    p.add_argument("--tag", action="append", help="Add tag (repeatable)")
    p.set_defaults(func=cmd_ri_add)

    p = ri_sub.add_parser("acknowledge", aliases=["ack"], help="Acknowledge a review item")
    p.add_argument("trace_id")
    p.add_argument("review_item_id")
    p.set_defaults(func=cmd_ri_ack)

    p = ri_sub.add_parser("resolve", help="Resolve a review item")
    p.add_argument("trace_id")
    p.add_argument("review_item_id")
    p.add_argument("-n", "--note", help="Resolution note")
    p.set_defaults(func=cmd_ri_resolve)

    # ── links ───────────────────────────────────────────────────
    links = subparsers.add_parser("links", help="Manage trace links and chains")
    links_sub = links.add_subparsers(dest="links_command", required=True)

    p = links_sub.add_parser("list", aliases=["ls"], help="List links for a trace")
    p.add_argument("trace_id")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.set_defaults(func=cmd_links_list)

    p = links_sub.add_parser("add", help="Create a trace link")
    p.add_argument("from_trace_id")
    p.add_argument("to_trace_id")
    p.add_argument("-r", "--relationship", required=True, help="Relationship: supersedes, related_to, derived_from, same_task")
    p.add_argument("-n", "--note", help="Note")
    p.set_defaults(func=cmd_links_add)

    p = links_sub.add_parser("timeline", help="Show computed chain timeline")
    p.add_argument("trace_id")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.set_defaults(func=cmd_links_timeline)

    # ── packs ───────────────────────────────────────────────────
    packs = subparsers.add_parser("packs", help="Manage policy packs")
    packs_sub = packs.add_subparsers(dest="packs_command", required=True)

    p = packs_sub.add_parser("list", aliases=["ls"], help="List policy packs")
    p.add_argument("-s", "--scope", help="Filter by scope: public, organization, user")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.set_defaults(func=cmd_packs_list)

    p = packs_sub.add_parser("attach", help="Attach a policy pack to a trace")
    p.add_argument("trace_id")
    p.add_argument("pack_id")
    p.set_defaults(func=cmd_packs_attach)

    p = packs_sub.add_parser("detach", help="Detach a policy pack from a trace")
    p.add_argument("trace_id")
    p.add_argument("pack_id")
    p.set_defaults(func=cmd_packs_detach)

    p = packs_sub.add_parser("run", help="Re-run policy evaluations on a trace")
    p.add_argument("trace_id")
    p.add_argument("-p", "--pack", action="append", help="Specific pack to run (repeatable)")
    p.set_defaults(func=cmd_packs_run)

    # ── snapshots ───────────────────────────────────────────────
    snaps = subparsers.add_parser("snapshots", aliases=["snap"], help="Manage trace snapshots")
    snaps_sub = snaps.add_subparsers(dest="snapshots_command", required=True)

    p = snaps_sub.add_parser("list", aliases=["ls"], help="List snapshots for a trace")
    p.add_argument("trace_id")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.set_defaults(func=cmd_snapshots_list)

    p = snaps_sub.add_parser("create", help="Create a snapshot of a trace")
    p.add_argument("trace_id")
    p.set_defaults(func=cmd_snapshots_create)

    p = snaps_sub.add_parser("approve", help="Approve a snapshot")
    p.add_argument("snapshot_id")
    p.add_argument("-n", "--note", default="Approved via CLI", help="Approval note")
    p.set_defaults(func=cmd_snapshots_approve)

    # ── activity ─────────────────────────────────────────────────
    p = subparsers.add_parser("activity", help="Show activity feed")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.set_defaults(func=cmd_activity)

    # ── open ─────────────────────────────────────────────────────
    p = subparsers.add_parser("open", help="Open the Hub or a trace in the browser")
    p.add_argument("trace_id", nargs="?", default=None)
    p.set_defaults(func=cmd_open)

    # ── trace (local) ────────────────────────────────────────────
    trace_mod.register(subparsers)

    # ── registry & policies (community policy gallery) ───────────
    registry_mod.register(subparsers)

    # ── git/hub sync (bind, push, pull, status) ──────────────────
    sync_mod.register(subparsers)

    # ── emit (derive a trace from an agent session transcript) ───
    emit_mod.register(subparsers)

    # ── Parse and dispatch ───────────────────────────────────────
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    try:
        result = args.func(args)
        if isinstance(result, int) and result != 0:
            sys.exit(result)
    except RuntimeError as e:
        print(red(f"Error: {e}"), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

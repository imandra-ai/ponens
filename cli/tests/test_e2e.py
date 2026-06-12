"""End-to-end tests exercising the ponens CLI against a live hub server.

These tests run in order (within each class) and build on state created
by earlier tests. The hub uses an in-memory store seeded with demo data.
"""

import json
import os
import subprocess
import tempfile

import pytest

from ponens.client import api


# ── Helpers ─────────────────────────────────────────────────────


def cli(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a ponens CLI command and return the result."""
    result = subprocess.run(
        ["ponens", *args],
        capture_output=True,
        text=True,
        env={**os.environ},
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"ponens {' '.join(args)} failed (rc={result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


def cli_json(*args: str) -> dict | list:
    """Run a CLI command with --json and parse the output."""
    r = cli(*args, "--json")
    return json.loads(r.stdout)


# ================================================================
# Auth
# ================================================================


class TestAuth:
    def test_whoami(self):
        r = cli("auth", "whoami")
        assert "Denis Ignatovich" in r.stdout
        assert "usr_denis" in r.stdout

    def test_users(self):
        r = cli("auth", "users")
        assert "Sarah Chen" in r.stdout
        assert "Mike Johnson" in r.stdout

    def test_switch_and_back(self):
        r = cli("auth", "switch", "usr_reviewer")
        assert "Sarah Chen" in r.stdout

        # Verify switched
        r = cli("auth", "whoami")
        assert "Sarah Chen" in r.stdout

        # Switch back
        cli("auth", "switch", "usr_denis")
        r = cli("auth", "whoami")
        assert "Denis Ignatovich" in r.stdout


# ================================================================
# Traces — CRUD
# ================================================================


class TestTraces:
    trace_id = None  # set by test_upload

    def test_list_seed_data(self):
        data = cli_json("traces", "list")
        assert isinstance(data, list)
        assert len(data) >= 5  # seed has 5 acme traces
        ids = [t["trace_id"] for t in data]
        assert "tr_1042" in ids

    def test_list_status_filter(self):
        data = cli_json("traces", "list", "-s", "approved")
        assert all(t["status"] == "approved" for t in data)

    def test_show_seed_trace(self):
        r = cli("traces", "show", "tr_1042")
        assert "Stripe payment flow" in r.stdout
        assert "under_review" in r.stdout

    def test_show_json(self):
        data = cli_json("traces", "show", "tr_1042")
        assert data["trace_id"] == "tr_1042"
        assert data["summary"]["proofs"] == 14

    def test_upload(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "summary": {
                    "counterexamples": 0,
                    "proofs": 3,
                    "regions": 10,
                    "tests_total": 10,
                    "tests_passed": 10,
                    "policy_status": "passed",
                    "conformance_status": "passed",
                },
            }, f)
            f.flush()
            trace_file = f.name

        try:
            r = cli(
                "traces", "upload", trace_file,
                "--title", "E2E Test Trace",
                "--repo", "test/repo",
                "--branch", "main",
                "--commit", "deadbeef",
                "--task", "TEST-1",
            )
            assert "Uploaded" in r.stdout

            # Extract trace ID from output
            for word in r.stdout.split():
                if word.startswith("tr_"):
                    TestTraces.trace_id = word.strip()
                    break
            assert TestTraces.trace_id is not None, "Could not extract trace_id from upload output"
        finally:
            os.unlink(trace_file)

    def test_uploaded_trace_appears_in_list(self):
        assert TestTraces.trace_id is not None
        data = cli_json("traces", "list")
        ids = [t["trace_id"] for t in data]
        assert TestTraces.trace_id in ids

    def test_uploaded_trace_is_draft(self):
        data = cli_json("traces", "show", TestTraces.trace_id)
        assert data["status"] == "draft"
        assert data["title"] == "E2E Test Trace"
        assert data["repo"] == "test/repo"

    def test_status_update(self):
        r = cli("traces", "status", TestTraces.trace_id, "under_review")
        assert "under_review" in r.stdout

        data = cli_json("traces", "show", TestTraces.trace_id)
        assert data["status"] == "under_review"

    def test_status_approve(self):
        cli("traces", "status", TestTraces.trace_id, "approved")
        data = cli_json("traces", "show", TestTraces.trace_id)
        assert data["status"] == "approved"


# ================================================================
# Comments
# ================================================================


class TestComments:
    comment_id = None

    def test_list_seed_comments(self):
        data = cli_json("comments", "list", "tr_1042")
        assert isinstance(data, list)
        assert len(data) >= 2  # seed has 2 comments on tr_1042

    def test_add_comment(self):
        r = cli("comments", "add", TestTraces.trace_id, "E2E test comment")
        assert "Created" in r.stdout

        data = cli_json("comments", "list", TestTraces.trace_id)
        assert len(data) >= 1
        c = next(c for c in data if c["body"] == "E2E test comment")
        TestComments.comment_id = c["comment_id"]

    def test_add_comment_with_tags(self):
        r = cli(
            "comments", "add", TestTraces.trace_id, "Tagged comment",
            "--tag", "e2e", "--tag", "test",
        )
        assert "Created" in r.stdout

        data = cli_json("comments", "list", TestTraces.trace_id)
        c = next(c for c in data if c["body"] == "Tagged comment")
        assert "e2e" in c["tags"]
        assert "test" in c["tags"]

    def test_resolve_comment(self):
        assert TestComments.comment_id is not None
        r = cli("comments", "resolve", TestTraces.trace_id, TestComments.comment_id)
        assert "Resolved" in r.stdout


# ================================================================
# Review Items
# ================================================================


class TestReviewItems:
    ri_id = None

    def test_list_seed_review_items(self):
        data = cli_json("review-items", "list", "tr_1042")
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_add_review_item(self):
        r = cli(
            "review-items", "add", TestTraces.trace_id, "E2E blocking item",
            "--body", "Must fix before merge",
            "--blocking",
        )
        assert "Created" in r.stdout
        assert "blocking" in r.stdout

        data = cli_json("review-items", "list", TestTraces.trace_id)
        ri = next(ri for ri in data if ri["title"] == "E2E blocking item")
        TestReviewItems.ri_id = ri["review_item_id"]
        assert ri["blocking"] is True
        assert ri["status"] == "open"

    def test_acknowledge_review_item(self):
        assert TestReviewItems.ri_id is not None
        r = cli("review-items", "acknowledge", TestTraces.trace_id, TestReviewItems.ri_id)
        assert "Acknowledged" in r.stdout

    def test_resolve_review_item(self):
        r = cli(
            "review-items", "resolve", TestTraces.trace_id, TestReviewItems.ri_id,
            "--note", "Fixed in latest commit",
        )
        assert "Resolved" in r.stdout

    def test_double_resolve_fails(self):
        r = cli(
            "review-items", "resolve", TestTraces.trace_id, TestReviewItems.ri_id,
            check=False,
        )
        assert r.returncode != 0


# ================================================================
# Links
# ================================================================


class TestLinks:
    def test_list_seed_links(self):
        data = cli_json("links", "list", "tr_1042")
        assert "outgoing" in data
        assert len(data["outgoing"]) >= 1  # seed link: tr_1042 supersedes tr_1039

    def test_add_link(self):
        r = cli(
            "links", "add", TestTraces.trace_id, "tr_1042",
            "--relationship", "derived_from",
            "--note", "E2E test link",
        )
        assert "Created" in r.stdout
        assert "derived_from" in r.stdout

    def test_link_appears_in_both_directions(self):
        # Outgoing from new trace
        data = cli_json("links", "list", TestTraces.trace_id)
        out = data["outgoing"]
        assert any(l["to_trace_id"] == "tr_1042" for l in out)

        # Incoming to tr_1042
        data = cli_json("links", "list", "tr_1042")
        inc = data["incoming"]
        assert any(l["from_trace_id"] == TestTraces.trace_id for l in inc)

    def test_timeline(self):
        data = cli_json("links", "timeline", "tr_1042")
        assert "chain_trace_ids" in data
        assert "timeline" in data
        assert len(data["timeline"]) > 0
        types = {e["type"] for e in data["timeline"]}
        assert "trace_created" in types


# ================================================================
# Policy Packs
# ================================================================


class TestPacks:
    def test_list_packs(self):
        data = cli_json("packs", "list")
        assert isinstance(data, list)
        assert len(data) >= 4  # seed has 4 packs
        names = [p["name"] for p in data]
        assert "payments-v3" in names

    def test_list_packs_by_scope(self):
        data = cli_json("packs", "list", "--scope", "public")
        assert all(p["scope"] == "public" for p in data)
        assert len(data) >= 1

    def test_attach_pack(self):
        r = cli("packs", "attach", TestTraces.trace_id, "pack_org_payments_v3")
        assert "Attached" in r.stdout

        data = cli_json("traces", "show", TestTraces.trace_id)
        assert "pack_org_payments_v3" in data["active_policy_pack_ids"]

    def test_run_policies(self):
        r = cli("packs", "run", TestTraces.trace_id)
        assert "Policy run" in r.stdout
        assert "passed" in r.stdout

    def test_detach_pack(self):
        r = cli("packs", "detach", TestTraces.trace_id, "pack_org_payments_v3")
        assert "Detached" in r.stdout

        data = cli_json("traces", "show", TestTraces.trace_id)
        assert "pack_org_payments_v3" not in data["active_policy_pack_ids"]


# ================================================================
# Snapshots
# ================================================================


class TestSnapshots:
    snapshot_id = None

    def test_list_seed_snapshots(self):
        data = cli_json("snapshots", "list", "tr_1041")
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["snapshot_id"] == "snap_8811"

    def test_create_snapshot(self):
        # Re-attach a pack so we have something to snapshot
        cli("packs", "attach", TestTraces.trace_id, "pack_org_auth_v2")

        r = cli("snapshots", "create", TestTraces.trace_id)
        assert "Created" in r.stdout
        assert "pending" in r.stdout

        data = cli_json("snapshots", "list", TestTraces.trace_id)
        assert len(data) >= 1
        TestSnapshots.snapshot_id = data[-1]["snapshot_id"]

    def test_approve_snapshot(self):
        assert TestSnapshots.snapshot_id is not None
        r = cli("snapshots", "approve", TestSnapshots.snapshot_id)
        assert "Approved" in r.stdout

    def test_double_approve_fails(self):
        r = cli("snapshots", "approve", TestSnapshots.snapshot_id, check=False)
        assert r.returncode != 0


# ================================================================
# Activity
# ================================================================


class TestActivity:
    def test_activity_feed(self):
        data = cli_json("activity")
        assert isinstance(data, list)
        assert len(data) > 0
        # Should include our upload activity
        types = {a["type"] for a in data}
        assert "trace_uploaded" in types

    def test_activity_includes_new_events(self):
        """Verify that our E2E actions generated activity entries."""
        data = cli_json("activity")
        summaries = [a["summary"] for a in data]
        # Our upload should appear
        assert any("E2E Test Trace" in s for s in summaries)


# ================================================================
# Open (just verifies no crash, doesn't open browser)
# ================================================================


class TestOpen:
    def test_open_no_crash(self):
        # We can't actually open a browser in CI, but verify the command
        # at least runs and prints the URL
        r = cli("open", "tr_1042")
        assert "Opening" in r.stdout
        assert "tr_1042" in r.stdout


# ================================================================
# Org isolation
# ================================================================


class TestOrgIsolation:
    def test_globex_user_sees_only_globex_traces(self):
        cli("auth", "switch", "usr_globex_dev")
        try:
            data = cli_json("traces", "list")
            org_ids = {t["organization_id"] for t in data}
            assert org_ids == {"org_globex"}
            assert any(t["trace_id"] == "tr_2001" for t in data)
        finally:
            cli("auth", "switch", "usr_denis")

    def test_globex_activity_is_isolated(self):
        cli("auth", "switch", "usr_globex_dev")
        try:
            data = cli_json("activity")
            org_ids = {a["organization_id"] for a in data}
            assert org_ids <= {"org_globex"}
        finally:
            cli("auth", "switch", "usr_denis")


# ================================================================
# Local trace commands (offline, no hub needed)
# ================================================================


class TestLocalTrace:
    def test_full_local_workflow(self, tmp_path):
        trace_file = str(tmp_path / "trace.json")

        # init
        r = cli("trace", "init", trace_file)
        assert "Created trace" in r.stdout
        assert os.path.exists(trace_file)

        # trigger
        r = cli("trace", "trigger", trace_file,
                "--type", "TaskReceived", "--description", "Fix bug #42")
        assert "Trigger set" in r.stdout

        # action
        r = cli("trace", "action", trace_file,
                "--type", "ReadFile", "--label", "Read main.py",
                "--rationale", "Understand the code")
        assert "Action #1" in r.stdout

        r = cli("trace", "action", trace_file,
                "--type", "EditFile", "--label", "Fix the bug",
                "--rationale", "Apply the fix",
                "--evidence", "src/main.py")
        assert "Action #2" in r.stdout

        # artifact
        r = cli("trace", "artifact", trace_file,
                "--type", "SourceCode", "--name", "main.py")
        assert "Artifact" in r.stdout

        # complete
        r = cli("trace", "complete", trace_file, "--summary", "Bug fixed")
        assert "Trace completed" in r.stdout

        # status
        r = cli("trace", "status", trace_file)
        assert "ProcessCompleted" in r.stdout
        assert "Bug fixed" in r.stdout
        assert "ReadFile" in r.stdout
        assert "EditFile" in r.stdout

        # check (no policies, should pass)
        r = cli("trace", "check", trace_file)
        assert "No policies to check" in r.stdout

        # Verify the file is valid JSON
        with open(trace_file) as f:
            data = json.load(f)
        assert data["spec_version"] == "1.1"
        assert len(data["actions"]) == 2
        assert len(data["artifacts"]) == 1
        assert data["outcome"]["type"] == "ProcessCompleted"

    def test_init_rejects_existing_file(self, tmp_path):
        trace_file = str(tmp_path / "trace.json")
        cli("trace", "init", trace_file)
        r = cli("trace", "init", trace_file, check=False)
        assert r.returncode != 0
        assert "already exists" in r.stderr


# ================================================================
# Error handling
# ================================================================


class TestErrorHandling:
    def test_show_nonexistent_trace(self):
        r = cli("traces", "show", "tr_nonexistent", check=False)
        assert r.returncode != 0

    def test_comment_on_nonexistent_trace(self):
        # The server still creates the comment (no trace existence check in comments endpoint),
        # so this just verifies it doesn't crash
        r = cli("comments", "add", "tr_nonexistent", "test comment")
        # This succeeds because the comment endpoint doesn't validate trace existence
        assert r.returncode == 0

    def test_attach_nonexistent_pack(self):
        r = cli("packs", "attach", "tr_1042", "pack_nonexistent", check=False)
        assert r.returncode != 0

    def test_invalid_status_transition(self):
        # argparse validates the status choices
        r = cli("traces", "status", "tr_1042", "banana", check=False)
        assert r.returncode != 0

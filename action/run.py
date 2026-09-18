#!/usr/bin/env python3
"""The ponens GitHub Action — a checked reasoning trace on every pull request.

Runs inside the workflow's own runner (nothing leaves it) and drives the `ponens` CLI:

  1. FIND the trace: `INPUT_TRACE`, else the single `.ponens/*.json` an agent published, else
     reconstruct one from a transcript with `ponens emit`.
  2. VALIDATE it (`ponens trace validate [--strict]`); a malformed trace is `invalid` and fails.
  3. GATE it (`ponens trace check --json`, plus gallery policies / a local policy file): every failed
     error-severity policy is a violation; `fail-on` decides whether the job goes red.
  4. RESOLVE it (`ponens trace enrich`): goals met / at risk, weakest-link strength, open residuals.
  5. REPORT: `ponens trace report` (Markdown) framed with the gate verdict and the goal scorecard —
     written to the job summary, to `.ponens-ci/report.md`, and (on a pull request) posted as ONE
     comment that is updated in place on every push.

Standard library only; the CLI does the reasoning. Pure functions (gate, scorecard, comment body,
trace discovery) are separated from the subprocess / GitHub calls so they can be unit-tested.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import urllib.parse
import sys
from pathlib import Path

MARKER = "<!-- ponens-action -->"
WORKDIR = ".ponens-ci"
SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


# ---------------------------------------------------------------- inputs

def env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def truthy(s: str) -> bool:
    return s.lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------- subprocess / github

def ponens_bin() -> str:
    return os.environ.get("PONENS_BIN") or shutil.which("ponens") or "ponens"


def run(args: list[str], check: bool = False) -> subprocess.CompletedProcess:
    proc = subprocess.run(args, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed ({proc.returncode}):\n{proc.stdout}\n{proc.stderr}")
    return proc


def gh_api(method: str, path: str, body: dict | None = None) -> str:
    args = ["gh", "api", "-X", method, path]
    if body is not None:
        args += ["--input", "-"]
    proc = subprocess.run(args, input=json.dumps(body) if body is not None else None,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    return proc.stdout


def pr_number() -> int | None:
    """The pull request number this run is for, from the event payload (pull_request events) or a
    `pull_request` field on other events; None outside a PR."""
    p = os.environ.get("GITHUB_EVENT_PATH")
    if not p or not os.path.exists(p):
        return None
    try:
        ev = json.load(open(p))
    except (OSError, ValueError):
        return None
    pr = ev.get("pull_request") or {}
    n = pr.get("number") or ev.get("number")
    return int(n) if isinstance(n, int) else None


# ---------------------------------------------------------------- pure: discovery

def find_trace(explicit: str, cwd: str = ".") -> str | None:
    """The trace to check: the explicit path, else the single `.ponens/*.json` (sidecars excluded)."""
    if explicit:
        return explicit if os.path.exists(os.path.join(cwd, explicit)) else None
    cands = sorted(p for p in glob.glob(os.path.join(cwd, ".ponens", "*.json")) if not p.endswith(".sync"))
    if len(cands) == 1:
        return os.path.relpath(cands[0], cwd)
    return None


# ---------------------------------------------------------------- pure: gate + scorecard

def severity_index(trace: dict, policy_file: dict | None = None) -> dict[str, str]:
    """policy_id -> severity, from the trace's own policies and an optional policy file / pack."""
    idx: dict[str, str] = {}
    for src in (trace.get("policies") or [], (policy_file or {}).get("policies") or []):
        for p in src:
            pid = p.get("policy_id") or p.get("name")
            if pid:
                idx[pid] = str(p.get("severity") or "error").lower()
    return idx


def gate(evaluations: list[dict], severities: dict[str, str], fail_on: str) -> dict:
    """Fold policy evaluations into a verdict.
       status: passed | advisory | failed; violations: failed policies by severity."""
    failed = [e for e in evaluations if str(e.get("status", "")).lower() == "failed"]
    rows = []
    for e in failed:
        pid = e.get("policy_id", "?")
        rows.append({"policy_id": pid, "severity": severities.get(pid, "error"), "note": e.get("note") or "",
                     "violating": (e.get("violating_artifact_ids") or e.get("violating_action_ids") or [])})
    errors = [r for r in rows if r["severity"] == "error"]
    if fail_on == "never":
        status = "passed" if not rows else "advisory"
    elif fail_on == "warning":
        status = "failed" if rows else "passed"
    else:  # error
        status = "failed" if errors else ("advisory" if rows else "passed")
    rows.sort(key=lambda r: (SEVERITY_ORDER.get(r["severity"], 9), r["policy_id"]))
    return {"status": status, "violations": rows, "checked": len(evaluations),
            "passed": sum(1 for e in evaluations if str(e.get("status", "")).lower() == "passed")}


def scorecard(enriched: dict) -> dict:
    """What a reviewer needs from `enrich`: per-goal resolution and the trace-level summary."""
    goals = []
    for g in enriched.get("goals") or []:
        f = g.get("faithfulness") or {}
        items = g.get("acceptance") or []
        goals.append({
            "id": g.get("id") or g.get("goal_id") or "goal",
            "intent": g.get("intent") or "",
            "met": bool(f.get("met")),
            "certified": bool(f.get("certified")),
            "progress": g.get("progress"),
            "at_risk": int(g.get("at_risk") or 0),
            "open_gaps": int(g.get("open_gaps") or 0),
            "min_strength": g.get("min_strength"),
            "items": [{"id": it.get("id"), "status": it.get("status"), "strength": it.get("evidence_strength"),
                       "freshness": it.get("freshness")} for it in items],
        })
    s = enriched.get("summary") or {}
    return {"goals": goals, "summary": {
        "goals_total": int(s.get("goals_total") or len(goals)),
        "goals_met": int(s.get("goals_met") or sum(1 for g in goals if g["met"])),
        "open_residuals": int(s.get("open_residuals") or 0),
        "open_high": int(s.get("open_high") or 0),
        "stale_evidence": int(s.get("stale_evidence") or 0),
    }}


# ---------------------------------------------------------------- pure: requirements (`cl requirements --json`, RECORD_OVERVIEW v0.1)

BINDINGS_FILE = os.path.join(".codelogician", "bindings.yaml")
BINDINGS_JSON = os.path.join(WORKDIR, "bindings.json")


def load_bindings(setting: str, cwd: str) -> dict | None:
    """The requirements check to report: `off` → None; a path → that JSON; `auto` → run
    `cl requirements --json` when the repo has a requirements file and `cl` is on PATH, else a JSON a
    previous step left at `.ponens-ci/bindings.json`, else None (nothing to check). The JSON is ponens's
    own `trace requirements` shape (spec/RECORD_OVERVIEW_v0_1.md): `requirements[]` + `summary`."""
    setting = (setting or "auto").strip()
    if setting.lower() == "off":
        return None
    if setting.lower() != "auto":
        try:
            return json.load(open(os.path.join(cwd, setting)))
        except (OSError, ValueError):
            return None
    if os.path.exists(os.path.join(cwd, BINDINGS_FILE)) and shutil.which("cl"):
        proc = subprocess.run(["cl", "requirements", "--json", "--dir", cwd], capture_output=True, text=True)
        try:
            return json.loads(proc.stdout)
        except ValueError:
            notice(f"cl requirements produced no JSON: {(proc.stderr or proc.stdout).strip()[:300]}", "warning")
    pre = os.path.join(cwd, BINDINGS_JSON)
    if os.path.exists(pre):
        try:
            return json.load(open(pre))
        except ValueError:
            return None
    return None


_STATE_ICON = {"met": "✅", "out_of_date": "🟡", "open": "🔴", "failed": "🔴"}
_STATE_WORD = {"met": "met", "out_of_date": "out of date", "open": "open", "failed": "failed"}


def _state_cell(state: str, reason: str | None) -> str:
    word = _STATE_WORD.get(state, state or "?")
    if reason and state != "met":
        word += f" ({reason})"
    return f"{_STATE_ICON.get(state, '⚪')} {word}"


def render_bindings(doc: dict) -> list[str]:
    """Markdown lines for the requirements section: one row per requirement (or per symbol), the gate on the
    summary line. Speaks the five words: requirement, evidence, gap, record, gate."""
    rows, summary = doc.get("requirements") or [], doc.get("summary") or {}
    if not rows:
        return []
    gate = "✅" if summary.get("gate") == "pass" else "❌"
    n = summary.get("requirements", len(rows))
    parts = [f"{n} requirement{'s' if n != 1 else ''}", f"{summary.get('met', 0)} met"]
    for k, word in (("open", "open"), ("failed", "failed"), ("out_of_date", "out of date")):
        if summary.get(k):
            parts.append(f"{summary[k]} {word}")
    lines = ["", f"**Requirements:** {gate} " + " · ".join(parts), "",
             "| Requirement | Symbol → model symbol | Evidence | State |", "|---|---|---|---|"]
    for r in rows:
        model = r.get("model") or {}
        head = f"`{r.get('id')}`" + (f" · `{model.get('reference') or model.get('entry')}`" if model else "")
        reading = r.get("reading") or {}
        if reading.get("state") == "missing":
            head += " · 🔴 no reading chosen"
        elif reading.get("chosen"):
            head += f" · reading {reading['chosen']}"
        if model.get("status") == "revised":
            head += f" · 🔴 model revised → {model.get('current_version')}"
        symbols = [s for s in (r.get("symbols") or []) if s.get("scope") != "project"]
        if not symbols:
            e = r.get("evidence") or {}
            ev = f"{e.get('grade') or 'unranked'} · {(e.get('freshness') or '?').replace('_', ' ')}" if e else "—"
            lines.append(f"| {head} | — | {ev} | {_state_cell(r.get('state'), r.get('reason'))} |")
            continue
        for s_ in symbols:
            e = s_.get("evidence") or {}
            ev = f"{e.get('grade') or 'unranked'} · {(e.get('freshness') or '?').replace('_', ' ')}" if e else "—"
            lines.append(f"| {head} | `{s_.get('symbol')}` → `{s_.get('entry_symbol')}` | {ev} | {_state_cell(s_.get('state'), s_.get('reason'))} |")
            head = ""
    return lines


def pr_base_sha() -> str | None:
    """The pull request's base commit, from the event payload; None outside a PR."""
    p = os.environ.get("GITHUB_EVENT_PATH")
    if not p or not os.path.exists(p):
        return None
    try:
        ev = json.load(open(p))
    except (OSError, ValueError):
        return None
    sha = ((ev.get("pull_request") or {}).get("base") or {}).get("sha")
    return sha if isinstance(sha, str) and sha else None


# ---------------------------------------------------------------- pure: the scan (`cl scan --json`, scan-result v1)

def load_scan(setting: str, cwd: str, base: str | None) -> dict | None:
    """The autonomous scan: `off` → None; `no-agent` reads the proposals and the record as they stand
    (no model call - the nightly mode, where a revised rulebook shows up as out-of-date evidence);
    `agent` runs the agent headless (needs the agent and its model credentials on the runner). On a pull
    request the scan is scoped to what changed since the base (`--diff <base sha>`). Returns the
    scan-result document (`cl scan --json`, RECORD_OVERVIEW's sibling in CodeLogician) or None."""
    setting = (setting or "off").strip().lower()
    if setting == "off":
        return None
    if setting not in ("no-agent", "agent"):
        notice(f"scan: unknown setting '{setting}' (off | no-agent | agent)", "warning")
        return None
    if not shutil.which("cl"):
        notice("scan: `cl` is not on PATH (npm i -g imandra-pi-agent); skipping", "warning")
        return None
    args = ["cl", "scan", "--json", "--dir", cwd] + (["--no-agent"] if setting == "no-agent" else []) + (["--diff", base] if base else [])
    proc = subprocess.run(args, capture_output=True, text=True)
    try:
        return json.loads(proc.stdout)
    except ValueError:
        notice(f"cl scan produced no JSON: {(proc.stderr or proc.stdout).strip()[:300]}", "warning")
        return None


def render_scan(doc: dict) -> list[str]:
    """Markdown lines for the scan section: the headline, then the report's own body (its title dropped)."""
    if not doc:
        return []
    head = (doc.get("report") or {}).get("headline") or ""
    scope = doc.get("scope") or {}
    where = f" · changes since `{scope.get('base', '')[:12]}`" if scope.get("base") else ""
    lines = ["", f"**Scan:** {head}{where}"]
    md = ((doc.get("report") or {}).get("markdown") or "").strip()
    body = [l for l in md.split("\n") if not l.startswith("## ")]
    # the headline is the report's first line; keep the sections that follow it
    while body and (not body[0].strip() or body[0].strip() == head):
        body.pop(0)
    if body:
        lines += [""] + body
    return lines


def scan_status(doc: dict | None, fail_on: str) -> str:
    """passed | failed | skipped - the scan folded by `fail-on`: something not met fails under error|warning."""
    if not doc:
        return "skipped"
    if int((doc.get("summary") or {}).get("not_met") or 0) > 0:
        return "passed" if fail_on == "never" else "failed"
    return "passed"


def upsert_issue(repo: str, title: str, body: str) -> str:
    """Create or update the single open issue with `title` (a scheduled scan's report). Returns 'created'|'updated'."""
    q = f"repo:{repo} is:issue is:open in:title \"{title}\""
    found = json.loads(gh_api("GET", f"/search/issues?q={urllib.parse.quote(q)}&per_page=5"))
    for it in found.get("items") or []:
        if it.get("title") == title:
            gh_api("PATCH", f"/repos/{repo}/issues/{it['number']}", {"body": body})
            return "updated"
    gh_api("POST", f"/repos/{repo}/issues", {"title": title, "body": body})
    return "created"


def bindings_status(doc: dict | None, fail_on: str) -> str:
    """passed | failed | skipped — the requirements gate folded by `fail-on` (never = report only)."""
    if not doc or not (doc.get("requirements") or []):
        return "skipped"
    if (doc.get("summary") or {}).get("gate") == "pass":
        return "passed"
    return "passed" if fail_on == "never" else "failed"


# ---------------------------------------------------------------- pure: rendering

_BADGE = {"passed": "✅ Governance passed", "advisory": "🟡 Governance passed with warnings",
          "failed": "❌ Governance failed", "invalid": "❌ Invalid trace", "no-trace": "⚪ No reasoning trace"}


def render_comment(status: str, trace_path: str | None, verdict: dict | None, card: dict | None,
                   report_md: str, note: str = "", run_url: str = "", bindings: dict | None = None, scan: dict | None = None) -> str:
    lines = [MARKER, f"## {_BADGE.get(status, status)}"]
    if trace_path:
        lines.append(f"`{trace_path}`" + (f" · [run]({run_url})" if run_url else ""))
    if note:
        lines += ["", note]
    if verdict:
        lines.append("")
        lines.append(f"**Policies:** {verdict['passed']}/{verdict['checked']} passed"
                     + (f", {len(verdict['violations'])} failed" if verdict["violations"] else ""))
        for v in verdict["violations"]:
            where = f" — `{'`, `'.join(str(x) for x in v['violating'][:4])}`" if v["violating"] else ""
            lines.append(f"- {'🔴' if v['severity'] == 'error' else '🟡'} **{v['policy_id']}** ({v['severity']})"
                         + (f": {v['note']}" if v["note"] else "") + where)
    if card and card["goals"]:
        s = card["summary"]
        lines.append("")
        lines.append(f"**Goals:** {s['goals_met']}/{s['goals_total']} met"
                     + (f" · {s['stale_evidence']} stale" if s["stale_evidence"] else "")
                     + (f" · {s['open_high']} high-severity gap{'s' if s['open_high'] != 1 else ''} open" if s["open_high"] else ""))
        lines.append("")
        lines.append("| Goal | Status | Progress | Weakest evidence | At risk | Open gaps |")
        lines.append("|---|---|---|---|---|---|")
        for g in card["goals"]:
            st = "✅ met" if g["met"] else "⏳ open"
            if g["at_risk"]:
                st += " (at risk)"
            prog = f"{round((g['progress'] or 0) * 100)}%" if isinstance(g["progress"], (int, float)) else "—"
            intent = g["intent"].strip().replace("|", "\\|")
            if len(intent) > 80:
                intent = intent[:77] + "…"
            lines.append(f"| {intent or g['id']} | {st} | {prog} | {g['min_strength'] or '—'} | {g['at_risk']} | {g['open_gaps']} |")
    if bindings:
        lines += render_bindings(bindings)
    if scan:
        lines += render_scan(scan)
    if report_md.strip():
        lines += ["", report_md.strip()]
    lines += ["", "<sub>ponens reasoning trace · every claim is checkable evidence, graded by how it was established · "
              "[what is this?](https://ponens.dev)</sub>"]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- github: one comment, updated in place

def upsert_comment(repo: str, number: int, body: str) -> str:
    """Create or update the single ponens comment on the PR (found by MARKER). Returns 'created'|'updated'."""
    existing = None
    page = 1
    while page <= 5:
        out = gh_api("GET", f"repos/{repo}/issues/{number}/comments?per_page=100&page={page}")
        items = json.loads(out or "[]")
        for c in items:
            if MARKER in (c.get("body") or ""):
                existing = c
                break
        if existing or len(items) < 100:
            break
        page += 1
    if existing:
        gh_api("PATCH", f"repos/{repo}/issues/comments/{existing['id']}", {"body": body})
        return "updated"
    gh_api("POST", f"repos/{repo}/issues/{number}/comments", {"body": body})
    return "created"


# ---------------------------------------------------------------- outputs

def set_output(k: str, v) -> None:
    p = os.environ.get("GITHUB_OUTPUT")
    if p:
        with open(p, "a") as f:
            f.write(f"{k}={v}\n")


def step_summary(md: str) -> None:
    p = os.environ.get("GITHUB_STEP_SUMMARY")
    if p:
        with open(p, "a") as f:
            f.write(md)


def notice(msg: str, level: str = "notice") -> None:
    print(f"::{level}::{msg}")


# ---------------------------------------------------------------- main

def main() -> int:
    cwd = os.getcwd()
    fail_on = env("INPUT_FAIL_ON", "error").lower()
    want_comment = truthy(env("INPUT_COMMENT", "true"))
    require_trace = truthy(env("INPUT_REQUIRE_TRACE", "false"))
    strict = truthy(env("INPUT_STRICT_VALIDATE", "false"))
    repo = env("GITHUB_REPOSITORY")
    run_url = (f"{env('GITHUB_SERVER_URL', 'https://github.com')}/{repo}/actions/runs/{env('GITHUB_RUN_ID')}"
               if repo and env("GITHUB_RUN_ID") else "")
    Path(WORKDIR).mkdir(exist_ok=True)
    report_path = os.path.join(WORKDIR, "report.md")

    def finish(status: str, body: str, violations: int = 0, goals: str = "0/0", trace: str = "") -> int:
        Path(report_path).write_text(body)
        step_summary(body)
        set_output("status", status)
        set_output("violations", violations)
        set_output("goals", goals)
        set_output("trace", trace)
        set_output("report", report_path)
        n = pr_number()
        if want_comment and n and repo and env("GH_TOKEN"):
            try:
                how = upsert_comment(repo, n, body)
                print(f"PR comment {how} on #{n}")
            except Exception as ex:  # noqa: BLE001 - never fail the gate on a comment error
                notice(f"could not post the PR comment: {ex}", "warning")
        print(body)
        return 0 if status in ("passed", "advisory", "no-trace") else 1

    # 0. the scan (optional; needs no trace - a scheduled run on a repository with no published trace still scans)
    scan = load_scan(env("INPUT_SCAN", "off"), cwd, pr_base_sha())
    sstatus = scan_status(scan, fail_on)
    set_output("scan", (scan or {}).get("report", {}).get("headline", "") if scan else "")
    set_output("scan-status", sstatus)
    if scan and not pr_number() and truthy(env("INPUT_SCAN_ISSUE", "false")) and repo and env("GH_TOKEN"):
        try:
            how = upsert_issue(repo, env("INPUT_SCAN_ISSUE_TITLE", "CodeLogician scan"), "\n".join(render_scan(scan)).strip() + "\n")
            print(f"scan issue {how}")
        except Exception as ex:  # noqa: BLE001 - never fail the job on an issue error
            notice(f"could not open the scan issue: {ex}", "warning")

    # 1. find
    trace_path = find_trace(env("INPUT_TRACE"), cwd)
    if not trace_path and env("INPUT_TRANSCRIPT"):
        out = os.path.join(WORKDIR, "trace.json")
        proc = run([ponens_bin(), "emit", "--from", env("INPUT_TRANSCRIPT_FORMAT", "claude-code"),
                    env("INPUT_TRANSCRIPT"), "-o", out])
        if proc.returncode == 0 and os.path.exists(out):
            trace_path = out
        else:
            notice(f"ponens emit failed: {(proc.stderr or proc.stdout).strip()[:400]}", "warning")
    if not trace_path:
        msg = ("No reasoning trace was found for this change. Publish one from the agent that made it "
               "(CodeLogician: `/cl-publish`, committed under `.ponens/`), or pass `transcript:` to "
               "reconstruct one from the session.")
        status = "failed" if sstatus == "failed" else "no-trace"
        body = render_comment(status, None, None, None, "", note=msg if not scan else "", run_url=run_url, scan=scan)
        rc = finish(status, body)
        return 1 if require_trace else rc

    # working copy (policies may be added; the repo file is never modified)
    work = os.path.join(WORKDIR, "trace.json")
    if os.path.abspath(trace_path) != os.path.abspath(work):
        shutil.copyfile(trace_path, work)

    # 2. validate
    vargs = [ponens_bin(), "trace", "validate", work] + (["--strict"] if strict else [])
    proc = run(vargs)
    if proc.returncode != 0:
        body = render_comment("invalid", trace_path, None, None, "",
                              note="```\n" + (proc.stdout + proc.stderr).strip()[:3000] + "\n```", run_url=run_url)
        return finish("invalid", body, trace=trace_path)

    # 3. gate — add gallery policies / a local policy file, then check
    policy_ids = [p.strip() for p in env("INPUT_POLICIES").split(",") if p.strip()]
    if policy_ids:
        run([ponens_bin(), "registry", "update"])
        for pid in policy_ids:
            p = run([ponens_bin(), "policies", "add", pid, "--into", work])
            if p.returncode != 0:
                notice(f"could not add policy {pid}: {(p.stderr or p.stdout).strip()[:300]}", "warning")
    policy_file = env("INPUT_POLICY_FILE")
    cargs = [ponens_bin(), "trace", "check", work, "--json"] + (["--policy-file", policy_file] if policy_file else [])
    proc = run(cargs)
    try:
        evaluations = json.loads(proc.stdout or "[]")
        if not isinstance(evaluations, list):
            evaluations = []
    except ValueError:
        evaluations = []
        notice(f"ponens trace check produced no JSON: {(proc.stderr or proc.stdout).strip()[:300]}", "warning")
    trace_doc = json.load(open(work))
    pf = None
    if policy_file and os.path.exists(policy_file):
        try:
            pf = json.load(open(policy_file))
            if isinstance(pf, list):
                pf = {"policies": pf}
        except ValueError:
            pf = None
    verdict = gate(evaluations, severity_index(trace_doc, pf), fail_on)

    # 4. resolve
    card = None
    proc = run([ponens_bin(), "trace", "enrich", work])
    if proc.returncode == 0:
        try:
            card = scorecard(json.loads(proc.stdout))
        except ValueError:
            card = None

    # 4b. bindings — the regulatory / specification bindings check (CodeLogician `cl bindings --json`)
    bindings = load_bindings(env("INPUT_BINDINGS", "auto"), cwd)
    bstatus = bindings_status(bindings, fail_on)
    set_output("bindings", bstatus)
    status = verdict["status"]
    if sstatus == "failed" and status != "failed":
        status = "failed"
        notice("the scan found something not met - see the summary", "error")
    if bstatus == "failed" and status != "failed":
        status = "failed"
        notice("the bindings gate failed — a bound symbol lacks conformance evidence at the required strength, "
               "is stale, or has no interpretation chosen", "error")

    # 5. report
    proc = run([ponens_bin(), "trace", "report", work])
    report_md = proc.stdout if proc.returncode == 0 else ""
    body = render_comment(status, trace_path, verdict, card, report_md, run_url=run_url, bindings=bindings, scan=scan)
    goals = f"{card['summary']['goals_met']}/{card['summary']['goals_total']}" if card else "0/0"
    if verdict["status"] == "failed":
        notice(f"{len(verdict['violations'])} policy violation(s) — see the summary", "error")
    return finish(status, body, violations=len(verdict["violations"]), goals=goals, trace=trace_path)


if __name__ == "__main__":
    sys.exit(main())

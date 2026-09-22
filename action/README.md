# ponens GitHub Action — a checked reasoning trace on every pull request

Agents write more code than anyone can review diff by diff. This action puts, next to the diff, the
one artifact a diff cannot give a reviewer: what the agent actually established, at what strength,
what it assumed, what is still open, and whether any of it has gone stale — as a status check and a
pull-request comment. It runs entirely inside your CI; nothing leaves the runner.

```yaml
# .github/workflows/ponens.yml
name: Reasoning trace
on: [pull_request]
permissions:
  contents: read
  pull-requests: write        # to post / update the scorecard comment
jobs:
  ponens:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: imandra-ai/ponens/action@v1.15.3
        with:
          policies: tests_before_commit,data_flow_integrity   # optional: gallery policies on top of the trace's own
          fail-on: error                                      # error (default) | warning | never
```

## What it does

1. **Finds the trace** — the single trace under `.ponens/` that the agent published (CodeLogician:
   `/cl-publish`), or `trace:` if you name one. With no trace but a session transcript, `transcript:`
   reconstructs one with `ponens emit` (Claude Code, Cursor, Gemini, Codex, pi).
2. **Validates it** — `ponens trace validate`; a malformed trace is reported as *invalid* and fails.
3. **Runs the gate** — `ponens trace check` over the policies the trace carries, plus any gallery
   `policies:` and a local `policy-file:`. A failed *error*-severity policy is a violation; `fail-on`
   decides whether the job goes red. Make the job a required check to block merges on it.
4. **Resolves the goals** — `ponens trace enrich`: met or open, progress, the weakest evidence the
   goal rests on (proof > sat > tests > static analysis > attested), what is at risk, open gaps.
5. **Reports** — `ponens trace report` framed with the verdict and the scorecard: in the job summary,
   as `.ponens-ci/report.md`, and on a pull request as **one comment updated in place** on every push.

## Inputs

| input | default | meaning |
|---|---|---|
| `trace` | the single `.ponens/*.json` | trace file to check |
| `scan` | `off` | the autonomous scan: `off` · `no-agent` (no model call; the nightly mode) · `agent` |
| `scan-issue`, `scan-issue-title` | `false` / `CodeLogician scan` | outside a PR, keep one issue up to date with the scan's report |
| `transcript`, `transcript-format` | — / `claude-code` | reconstruct a trace from a session transcript when none was published |
| `policies` | — | comma-separated gallery policy ids to add (`ponens policies add`) |
| `policy-file` | — | a local policy / pack JSON to check against as well |
| `fail-on` | `error` | `error` · `warning` · `never` |
| `comment` | `true` | post / update the PR comment |
| `require-trace` | `false` | fail when no trace can be found or reconstructed |
| `strict-validate` | `false` | `ponens trace validate --strict` (deep soundness) |
| `github-token` | workflow token | token for the comment |
| `ponens-version`, `ponens-source` | `1.15.3`, `git` | which ponens, from `git` (release tag) · `pypi` · `local` |

## Outputs

`status` (`passed` · `advisory` · `failed` · `invalid` · `no-trace`), `violations`, `goals-met`
(`met/total`), `trace`, `report` (path to the Markdown).

## What the comment looks like

> ## ✅ Governance passed
> `.ponens/codelogician.json` · run
>
> **Policies:** 13/13 passed
>
> **Goals:** 1/1 met
>
> | Goal | Status | Progress | Weakest evidence | At risk | Open gaps |
> |---|---|---|---|---|---|
> | refund never over-refunds; capture is gated | ✅ met | 100% | proof | 0 | 1 |
>
> ### 🧭 Ponens reasoning trace — … (proved)
> **Grade B (84/100)** · policies 13/13 ✓ · 7 steps · 23 artifacts
> *(the `ponens trace report` scorecard and declared gaps follow)*

## Notes

- The repository file is never modified: policies are added to a working copy under `.ponens-ci/`.
- No trace and no transcript is reported, not failed, unless `require-trace: true` — so the action can
  be installed org-wide before every repository publishes traces.
- Everything the action does is the open `ponens` CLI; run the same commands locally to reproduce a
  verdict. Signing, snapshots, retention and review cases are the hosted ponens hub's job, not this
  action's.


## The scan (CodeLogician)

`scan: no-agent` adds an autonomous look at the repository to the run: which formal models the code
implements, whether it meets them, evidence gone out of date, open gaps, edge cases. It reads the
proposals and the record as they stand, with no model call, so it is cheap enough for a nightly
schedule - which is the point: a revised rulebook or a re-issued specification shows up as out-of-date
evidence the morning after, with no change to any file the repository owns. A scan writes nothing into the checkout (its record lives under the runner's
`~/.codelogician/scans/`), so the working tree stays clean for the rest of the job. `scan: agent` runs
the agent headless instead, establishing what is not yet established (the agent and its model credentials must be
on the runner). On a pull request the scan is scoped to what changed since the base, so the report is
about this change. Something not met fails the job under `fail-on: error` / `warning`. Outside a pull
request, `scan-issue: true` keeps one open issue up to date with the report. Outputs: `scan` (the
headline) and `scan-status` (`passed | failed | skipped`).

```yaml
# .github/workflows/scan.yml — the nightly look
on:
  schedule: [{ cron: "0 6 * * *" }]
jobs:
  scan:
    runs-on: ubuntu-latest
    permissions: { contents: read, issues: write }
    steps:
      - uses: actions/checkout@v4
      - run: npm i -g imandra-pi-agent
      - uses: imandra-ai/ponens/action@v1.15.3
        with:
          scan: no-agent
          scan-issue: "true"
          require-trace: "false"
        env: { GH_TOKEN: ${{ github.token }} }
```

## Requirements (CodeLogician)

If the repository carries `.codelogician/bindings.yaml` (its requirements: the formal models the code
must meet — a regulation article, an API specification, a spec-first model), the action also reports the
**requirements check** as ponens states it (`spec/RECORD_OVERVIEW_v0_1.md`): one row per requirement, or
per code symbol → model symbol, with the evidence against the model (grade, fresh or out of date) and its
state — met, open, failed, out of date — and the gate on the summary line. With `bindings: auto` (the
default) it runs `cl requirements --json` when `cl` is on the PATH (`npm i -g imandra-pi-agent`), or reads
a JSON a previous step left at `.ponens-ci/bindings.json`; pass a path to read that file, or `off` to skip.
A blocked requirements gate fails the job under `fail-on: error` / `warning` (report only under `never`).
The `bindings` output is `passed | failed | skipped`.

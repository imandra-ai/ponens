# Ponens PR trace — GitHub Action

Puts the reasoning behind a change **where reviewers already are**. On a pull request, this
action reads the attached reasoning trace, posts a summary comment (grade, declared gaps, policy
result), and uploads the **interactive viewer** as a downloadable artifact so a reviewer can open
the meta-action timeline, lineage, and decisions.

It's a thin wrapper over the open CLI — `ponens trace report` (the comment body) and
`ponens trace view --out` (the self-contained viewer). No backend required.

## What it posts

```
🧭 Ponens reasoning trace — Make payment capture idempotent (proved)

Grade B (83/100) · policies 4/4 ✓ · 5 steps · 9 artifacts

▸ Scorecard (Structure / Rationale / Negative space / Reproducibility / Evidence / Lineage)

Declared gaps (residuals):
- 🔴 high — Assumes the gateway sends a stable idempotency key — check: confirm the retry contract
- 🟡 medium — Concurrent capture+refund races are not modelled

📎 View the full reasoning → download the ponens-trace-viewer artifact and open trace.html
```

The comment is **upserted** (updated in place on new pushes, not duplicated). If no trace is
found, it posts a one-line nudge to attach one.

## Usage

The author produces a trace and commits it (default location `.ponens/trace.json`):

```bash
ponens emit -o .ponens/trace.json     # derive it from the agent session
# ...enrich: declare residuals / artifacts, check the grade...
git add .ponens/trace.json && git commit
```

Then add a workflow:

```yaml
# .github/workflows/ponens.yml
name: Ponens
on: pull_request
permissions:
  contents: read
  pull-requests: write          # required to post the comment
jobs:
  trace:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: imandra-ai/ponens/.github/actions/pr-trace@main
        with:
          trace-path: .ponens/trace.json   # optional; this is the default
```

## Inputs

| Input | Default | Description |
|---|---|---|
| `trace-path` | `.ponens/trace.json` | Path to the committed trace JSON. |
| `github-token` | `${{ github.token }}` | Token used to post the comment (needs `pull-requests: write`). |

## Notes

- The viewer is uploaded as a workflow **artifact** (`ponens-trace-viewer/trace.html`) — fully
  self-contained, opens in any browser, no hosting needed.
- This is the open, hub-free integration. A hosted backend can instead render the viewer at a
  stable URL and link to it directly from the comment.

# ponens

**Turn an AI agent's session into a reviewable, verifiable reasoning record — and govern it.**

```bash
pip install ponens
```

When an AI coding agent finishes, all you really have is a diff and a chat log. `ponens` turns that
into a **reasoning trace**: a structured, reviewable record of *what was built and why* — the steps,
the decisions, the artifacts and their lineage, the declared goal and whether it was met, what was
verified, and what was left uncertain — at the altitude a reviewer actually reads, not a replay of
the dialogue.

Reasoner-agnostic, **local-first** (no backend required), MIT-licensed.

**Website & policy gallery:** https://ponens.dev

---

## Quick start

```bash
pip install ponens

ponens emit -o trace.json          # capture an agent session as a reasoning trace
ponens trace view trace.json       # open the interactive viewer (flow · lineage · goals · policies)
ponens trace grade trace.json      # score the record on a reviewer-oriented rubric
ponens trace check trace.json      # computable governance — machine-checked policies, PASS/FAIL
```

Already instrumented with OpenTelemetry or Langfuse? Bring those traces in and add the governance layer:

```bash
ponens otel import spans.json -o trace.json
ponens langfuse import lf.json  -o trace.json
```

## What you get

- **A reasoning trace, not a transcript** — atomic actions, typed artifacts, and a lineage DAG
  (what produced what), plus a declared **residual surface** (the gaps the agent left open).
- **Goals graded *met* vs *certified*** — did it meet its definition of done (resolved from the
  trace's own evidence), *and* did a reviewer other than the doer confirm that was the *right*
  definition? "Done" separated from "right."
- **Computable governance** — organizational and best-practice policies as machine-checked formulas
  over the trace (temporal + structural), a deterministic PASS/FAIL gate that runs offline in CI.
  Ready policy packs (formal-methods, the FIX Community's AI guidelines, and more) in the gallery.
- **An interactive viewer** — `ponens trace view` renders the flow, the lineage graph, the goals,
  and the policy verdicts in a single self-contained page.

## Learn more

- Website & policy gallery — https://ponens.dev
- Specs (trace, policy language, goal faithfulness) — https://ponens.dev/spec
- Source & issues — https://github.com/imandra-ai/ponens

## License

MIT — © Imandra, Inc.

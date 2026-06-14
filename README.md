# ponens

**Turn an AI agent's session into a higher-level reasoning record — a curated, verifiable
account of *what it built and why*.**

When an AI coding agent finishes, all you really have is a diff and a chat log. `ponens` turns
that into a **reasoning trace**: a structured, reviewable record of the work — the steps, the
decisions, the artifacts and their lineage, what was verified, and *what was left uncertain* — at
the altitude a reviewer actually reads, not a replay of the dialogue.

**The objective isn't just to *record* the reasoning — it's to make it *rigorous*, and to find
where rigor is missing**: to separate what was *established* from what was merely *asserted*, and
to point at where formal methods and other verification tools belong.

Reasoner-agnostic, **local-first** (no backend required), and built so the agent does the capture.

> Website & policy gallery: **https://ponens.dev**

---

## Not a log. A record.

A transcript is what was *said*. A trace is a curated account of what was *done* — and that
distinction is the whole point. `ponens` keeps **two layers** and treats them differently:

- **Atomic actions — ground-truth evidence.** Every file touched, command run, and result,
  derived mechanically from the session. Faithful and ungameable — this is what makes the trace
  *verifiable and reproducible*. **Never rewritten.**
- **The meta-action narrative — the curated story.** The agent groups its work into steps and
  rewrites the raw back-and-forth (*"yes"*, *"ok now fix it"*) into a clean, outcome-oriented
  account of *what was built and why*.

Faithful evidence underneath, a readable narrative on top. That is what makes a trace
**trustworthy *and* worth reading** — a higher-level record, not a log dump.

And it declares its own **negative space**: the assumptions it relied on, the claims it left
unverified, the questions it defers. A trace tells a reviewer *where to look* instead of forcing
them to re-derive the whole change to discover what's missing.

---

## Make the reasoning rigorous — and find where it isn't

Recording the work is table stakes. The point of `ponens` is to make the reasoning **rigorous**,
and to surface **where rigor is missing** — so you apply the heavy tools where they actually pay off:

- It separates what was **established** — proved, tested, verified, backed by an artifact — from
  what was merely **asserted** (rationale, confident prose). A "verified" claim with no backing
  artifact is treated as *unverified*.
- It makes the agent declare its **negative space** — the load-bearing assumptions and the claims
  it never checked.
- And it **points at where to bring the heavier tools** — formal methods (machine-checked proofs,
  model-checking), property-based tests, conformance checks — exactly where an unverified claim
  sits on a high-stakes path.

So a trace is not just a record of *what happened*; it's a **map of where the reasoning is solid
and where it needs rigor**. That is the on-ramp to formal verification: ponens finds the
high-value targets, so proof effort goes where it catches bugs — not everywhere, and not nowhere.

Policies make it enforceable — `reasoning_required_for_high_stakes`, `formalize_before_verify`,
`high_severity_residuals_acknowledged_before_commit`, `counterexample_triggers_fix` — so "where
rigor is required" becomes a gate, not a hope.

---

## The workflow

The agent produces the trace as part of finishing the work — five steps, all from the CLI:

```bash
# 1. EMIT — derive a faithful draft from the agent session (you write nothing).
#    Captures actions, file lineage, decisions, and the reasoning, automatically.
ponens emit -o trace.json

# 2. SCRUB the narrative — turn the raw directives into a clean account.
#    Only the *story* is curated; the atomic actions stay untouched and honest.
ponens trace meta ls trace.json                       # see the draft steps
ponens trace meta set trace.json m4 \
    --title  "Add idempotency to payment capture" \
    --intent "Stop double-charges on gateway retries" --status completed
ponens trace meta merge trace.json m7 m8 m9           # fold dead-ends into one step
ponens trace retitle trace.json --title "…" --outcome "…"

# 3. ENRICH — declare what emission can't derive: produced artifacts and the gaps.
ponens trace artifact trace.json --type VerificationResult --name "no double-charge" \
    --producer-action-id 12
ponens trace residual add trace.json --kind assumption --severity high \
    --statement "Assumes the gateway sends a stable idempotency key" \
    --suggested-check "confirm the retry contract"

# 4. GRADE — the quality rubric: structure, reasoning, gaps, reproducibility, lineage.
ponens trace grade trace.json

# 5. VIEW — read the reasoning behind the commit, zoomable from steps to atomic actions.
ponens trace view trace.json
```

Then **share** it — it travels with the commit, or lands on the pull request:

```bash
ponens bind && ponens push        # bind 1:1 to the commit; publish for review

# or post it on the PR — grade + declared gaps + a one-click interactive viewer:
#   uses: imandra-ai/ponens/.github/actions/pr-trace@main   (see that action's README)
```

---

## Why it's worth producing

For the **reviewer**, a trace replaces "read this large diff and guess why":

- **See the reasoning at the right altitude** — the meta-action view shows the change as a handful
  of intent-named steps; drill into any one to see its atomic actions.
- **Know where to look** — the declared residual surface routes attention to the assumptions and
  unverified claims, by severity.
- **Verify, don't trust** — `ponens trace reproduce` re-runs the recorded commands and reports
  divergence; the lineage DAG ties every result back to what produced it.

For the **team**, the trace is governable — see [Computable Governance](#computable-governance) below.

---

## Computable Governance

Most "AI governance" is a checklist or a dashboard. ponens makes governance **computable**: a
policy is a *machine-checkable rule over the reasoning trace*, evaluated automatically — a real
gate, not a social "Approved."

This isn't a new idea, and that's the point. It's **conformance checking** — the proven technique
behind runtime verification and declarative process mining (temporal logic over finite traces) —
brought to AI-coding-agent best practice. A policy compiles to a temporal / structural formula and
runs over the trace:

```bash
ponens registry update                       # pull the gallery of best-practice policies
ponens policies search testing
ponens policies add tests_before_commit --into trace.json
ponens trace check trace.json                # a real gate — runs fully offline
```

The community gallery codifies good engineering *and* reasoning discipline — what "did this well"
actually means, made checkable:

- **Good coding discipline** — `research_before_edit` (understand it before you change it),
  `tests_pass_before_commit`, `lint_before_commit`, `type_check_before_commit`,
  `no_secrets_committed`, `no_force_push`, `destructive_actions_confirmed`.
- **Good reasoning discipline** — `all_decisions_justified` (every decision records its *why*),
  `explain_before_complex_change`, `high_severity_residuals_acknowledged_before_commit` (don't
  commit over an unacknowledged gap), `reasoning_required_for_high_stakes`,
  `formalize_before_verify`, `counterexample_triggers_fix`.

Teams compose their own packs on top; the open gallery is the shared baseline of what good
AI-assisted engineering looks like, turned into something a machine can enforce. And because a
policy is a formula over a *typed* trace — not a regex over a transcript — it can quantify over the
**residual surface** (the declared gaps) and the **lineage DAG**, not just the action sequence.

---

## What's in this repo

The monorepo for the whole open ecosystem:

| Path | What it is |
|---|---|
| [`cli/`](cli/) | The `ponens` tool — emission + narrative curation, grading, the residual surface, the LTL policy compiler, the registry client, and git/hub sync. Pluggable per-agent adapters under [`cli/ponens/adapters/`](cli/ponens/adapters/). |
| [`spec/`](spec/) | The open standards — the Trace (incl. meta-actions §8.4 and the residual surface §13), Policy, and Review-Case specifications. |
| [`gallery/`](gallery/) | The community policy gallery — versioned, content-hashed policies + the generated catalog the CLI pulls. |
| [`viewer/`](viewer/) | The interactive trace viewer — the meta-action zoom, lineage DAG, reasoning, and policies. |
| [`examples/`](examples/) | The canonical sample traces (`manifest.json` drives the viewer dropdown; CI validates them all). |
| [`website/`](website/) | The `ponens.dev` site. |

---

## Install

```bash
# from this repo
pip install "ponens @ git+https://github.com/imandra-ai/ponens.git#subdirectory=cli"

# or for local development
pip install -e ./cli
```

## Backend-agnostic by design

Everything above runs with **no server** — `emit`, `grade`, `reproduce`, `check`, and the viewer
are all local. The CLI can sync a trace to a **hub** backend for hosted, multi-player review and
audit, but the hub is just one backend: the trace format, the policies, and the local gate are all
backend-agnostic. See [`spec/CLI_SYNC_MODEL_v0_1.md`](spec/CLI_SYNC_MODEL_v0_1.md) for the git/hub
sync model and [`AGENT_PROMPT.md`](AGENT_PROMPT.md) for driving the whole workflow from an agent.

## The name

From *modus ponens* — the rule of inference that derives a conclusion from its premises
(`P → Q`, `P ⊢ Q`). Given the recorded work and the policies, the tool derives whether the
reasoning holds.

## Contributing

New policies, spec improvements, agent adapters, and tooling fixes are welcome — see
[`CONTRIBUTING.md`](CONTRIBUTING.md). Every gallery policy and every sample trace is validated in
CI before it merges.

## License

MIT — see [`LICENSE`](LICENSE).

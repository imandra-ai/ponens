# Changelog

All notable changes to the `ponens` CLI. The format is based on
[Keep a Changelog](https://keepachangelog.com/); the project uses semantic versioning.

This file is the single source for release news: `make release` turns the matching section into the
GitHub release notes, and the website's **/whats-new** page renders this file directly. Keep a
`## [x.y.z]` heading per version, with `### Added` / `### Changed` / `### Fixed` subsections.

## [1.6.0] — 2026-07-25

### Added
- **Goal contracts** — an acceptance criterion is now *a required evidence artifact over a code
  component*: it names the `component` and the `evidence` artifact that must exist in its lineage
  (`{ "artifact": "VerificationResult" | "Decomp" | "Tests" | "Diff" | … }`). A goal also carries its
  own **policy bar**. State the goal as a contract - *accomplish these things, subject to these
  policies* - and `ponens trace enrich` returns three independent verdicts: **met** (each component has
  its evidence artifact), **governed** (the goal's policies held), and **certified** (a non-doer
  confirmed the criteria were the right ones). Author the whole contract in one shot with
  `ponens trace goal set --json`. See the new `GOAL_CONTRACT_v0_1` spec.
- **Met and governed are cleanly separated** — a criterion is *met* the moment its evidence artifact
  exists; **whether that evidence was derived correctly** (proved, autoformalized, tests pass, a proof
  required on a high-stakes path) is decided entirely by **policies**, the governed axis. One mechanism
  for rigor, no overlap. New pack policy `refuted_results_must_be_reproved` enforces that a verification
  result offered as evidence is actually proved, not left refuted.
- **Goal-scoped policies — the governed axis** — a goal can name policy `packs` and `policies`; they
  **block by default** unless explicitly `disabled` (recorded on the trace, never silent). Pack names
  resolve against the registry, and `enrich` attaches the governance result per goal.
- **Artifact lineage / provenance API** — a new dependency-free `ponens.lineage` module answers what a
  specific artifact was derived from: `ancestor_ids`, `lineage_types`, `source_symbols`, `autoformalized`,
  `decomposition_backed`, and a one-call `provenance` summary.

### Changed
- **`ponens agent`** now teaches the goal-contract workflow — evidence-artifact criteria, the goal's
  policy bar, and the three axes (met / governed / certified), including the rule that the agent
  *proposes* the rigor bar while a human *selects* it, and never self-certifies.
- **`ponens trace enrich`** now reports the **governed** axis alongside met and certified, and its
  summary counts `goals_governed`.
- **Evidence rigor moved from faithfulness grading to policy.** `faithfulness_of` no longer emits
  `weakly_specified` (and `certified` no longer depends on it) — "is a diff enough, or do you need a
  proof?" is now a policy question on the governed axis. `GOAL_FAITHFULNESS_v0_1` §6 is superseded.

### Fixed
- **Goals now reach *met* when the work is real** — a criterion resolves by artifact **lineage** (does
  an artifact of the required type root in this component?) instead of matching the verification goal's
  description text. This fixes goals that never ticked even though the evidence existed.
- **Lineage is component-precise** — an artifact that declares its own `target_symbol` (a VG, a Decomp,
  a targeted Diff) is about *that* component, so a decomposition of one function no longer looks like it
  roots in every symbol the shared model formalized.

## [1.5.0] — 2026-07-22

### Added
- **Goal authoring from the CLI** — a new `ponens trace goal` command group brings the desktop's goal
  workflow to the CLI, so every trace operation can be done from the command line: `set` (declare the
  intent + definition of done, or load one via `--json`), `accept` (add an acceptance item bound to
  evidence), `certify` (record a non-doer's sign-off — the *certified* axis), `drop` / `rm` (remove an
  item or a goal), and `ls` (show each goal's resolved status + met/certified/weakly-specified). Goals
  are written in the spec's snake_case shape.

### Fixed
- **PyPI project page** — the package now ships a README (`readme` in `pyproject.toml`), so the PyPI
  project page renders a description instead of "The author has not provided a project description."

## [1.4.1] — 2026-07-22

### Added
- **Faithfulness grading in `enrich`** — `ponens trace enrich` now grades each goal's *definition* of
  done (`GOAL_FAITHFULNESS_v0_1`), not just its progress: **met** (required criteria resolved from the
  trace's own evidence) vs **certified** (a reviewer other than the doer approved the criteria, every
  intent clause is covered, and the definition is not weakly specified), plus `weakly_specified` and
  `uncovered_clauses` per goal. The trace `summary` gains `goals_met` / `goals_certified` /
  `goals_weakly_specified` counts.
- **Faithfulness gate in `trace check`** — the checker reports each goal's met/certified status and,
  under `--strict`, fails on the deficiencies the agent controls: a weakly-specified definition
  (nothing proved or policy-checked backs "done") or an uncovered intent clause. "Met but not
  certified" is surfaced as a warning — certification needs a human, so it is never a hard failure.

## [1.4.0] — 2026-07-22

### Added
- **Goal faithfulness — met vs certified** — a goal's "done" is now graded on two orthogonal
  axes: *met* (its acceptance criteria resolved from the trace's own evidence) and *certified* (a
  reviewer other than the agent confirmed those were the *right* criteria). The new
  `GOAL_FAITHFULNESS_v0_1` spec (under `/spec`) refines Trace Spec §18 with authorship
  (`intent_author`, per-item `author`), clause coverage (`intent_clauses` + `covers`), and a
  `criteria_review`. It guards the principal–agent seam where the agent both *authors* and *meets* its
  own definition of done — an honest resolution can still "succeed" against a bar set too low.
- **Goals view in the visualizer** — `ponens trace view` now shows a trace's declared goals with their
  acceptance criteria and renders the faithfulness signals inline: *Met* / *Certified* badges, a
  weakly-specified warning (a goal backed only by code edits, with nothing proved or policy-checked),
  uncovered-intent-clause warnings, and the intent→criteria authorship seam. Each acceptance
  criterion's evidence chip is a link — click it to jump to the backing artifact in the lineage graph
  (or, for a policy obligation, the Policies view).

### Changed
- **Richer flagship demo** — the Stripe payment-flow trace is now the default demo: a declared goal
  with a certified definition of done, a seven-step meta-action narrative (formalize → catch the amount
  bug with a counterexample → fix → prove both new controls individually *and* together → conformance →
  ship), full lineage, and three honestly-declared residuals. The bundled `sample_payment_idempotency`
  trace also gained a declared goal, so the Goals view is populated out of the box.
- **Goal-oriented framing on the site** — the "not another tracing tool" comparison is reframed as
  *descriptive* (OpenTelemetry / Langfuse record what happened) vs *evaluative* (ponens judges each
  trace against its declared **goal** and its **policies**), and the header version badge now links to
  **/whats-new**.

### Fixed
- **Switching demos refreshes every view** — picking a different trace in the viewer's dropdown now
  re-renders the active tab against the new trace and hides tabs the new trace doesn't populate.
  Previously a pane could keep stale content from the previously-selected trace — e.g. the Goals tab
  still showing the last trace's goal.

## [1.3.0] — 2026-07-22

### Added
- **OpenTelemetry bridge** — `ponens otel import <otlp.json>` converts an OTLP-JSON span export into a
  ponens trace: spans → actions, parent-span tree → meta-actions, span start/end → action timestamps,
  and the `ponens.inputs/outputs` attribute convention → artifact lineage.
- **Langfuse bridge** — `ponens langfuse import <trace.json>` does the same for a Langfuse trace export
  (nested `SPAN` / `GENERATION` / `EVENT` observations).
- **`ponens demos`** — `list` and `get` bundled, checkable sample traces that ship with the CLI.
- **Machine-readable checks** — `ponens trace check --json` emits the `policy_evaluations` array;
  `--write` stamps it back into the trace file (self-describing traces).
- **Policy evidence** — evaluations now carry `evidence_action_ids` / `violating_action_ids` (plus the
  matching artifact ids); the visualizer renders these on each policy card.
- **Data-driven high-stakes surface** — the `high_stakes_path` predicate reads `trace.high_stakes_paths`
  (falling back to the demo defaults), so "where formal methods make sense" is decided by evidence.
- **Policy packs** — "Apply Formal Methods Where It Makes Sense", and the "Agentic Execution Provenance"
  spec mapping the FIX AI Working Group's six discussion points onto the trace model (with worked
  pass/fail example traces under `examples/fix_ai_wg/`).

### Fixed
- `make release` reads the version from `pyproject.toml` (no longer depends on `uv version --short`).
- `pyproject.toml` uses an SPDX `license = "MIT"` expression, removing the setuptools ≥77 deprecation
  warning on upload.

## [1.2.x] — 2026-07-21

### Added
- Artifact-DAG **node isolation** in the visualizer — click a node to isolate its connected lineage
  (upstreamed to `viewer/core`, so the CLI `ponens trace view` and the VS Code plugin both get it).

### Changed
- Packaging, license, and author-metadata fixes; version alignment across the desktop wrapper.

_Earlier releases predate this changelog — see the
[GitHub releases](https://github.com/imandra-ai/ponens/releases) for full history._

# Changelog

All notable changes to the `ponens` CLI. The format is based on
[Keep a Changelog](https://keepachangelog.com/); the project uses semantic versioning.

This file is the single source for release news: `make release` turns the matching section into the
GitHub release notes, and the website's **/whats-new** page renders this file directly. Keep a
`## [x.y.z]` heading per version, with `### Added` / `### Changed` / `### Fixed` subsections.

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

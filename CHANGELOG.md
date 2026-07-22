# Changelog

All notable changes to the `ponens` CLI. The format is based on
[Keep a Changelog](https://keepachangelog.com/); the project uses semantic versioning.

This file is the single source for release news: `make release` turns the matching section into the
GitHub release notes, and the website's **/whats-new** page renders this file directly. Keep a
`## [x.y.z]` heading per version, with `### Added` / `### Changed` / `### Fixed` subsections.

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

# Sample traces

This directory is the **single source of truth** for Ponens' demo traces. The viewer
dropdown, the website (`/viewer`), and CI all read from here — there are no
hand-maintained copies elsewhere.

## Layout

- **`*.json`** — the sample traces themselves.
- **`manifest.json`** — the curated list that drives the viewer dropdown (file → display
  name + summary). Add a sample here to surface it in the UI.
- **`make_samples.py`** — generator for the rich `sample_*.json` traces (spec 1.6). It
  builds them so the lineage DAG, meta-action overlay, and policy/residual references are
  consistent by construction. Re-run with `python3 examples/make_samples.py`.

## How they're used

- **Viewer / website** — `website/scripts/prepare.mjs` reads `manifest.json` and syncs each
  sample into the served `demo-traces/` directories (build outputs, git-ignored). The viewer's
  dropdown is generated from the same list.
- **CI** — `.github/workflows/validate-samples.yml` runs the CLI over every `*.json` here on
  each build: `ponens trace validate` (must pass) and `ponens trace check` (policies must
  pass), and confirms every `manifest.json` entry exists.

## Adding a sample

1. Write or generate the trace JSON into this directory.
2. Confirm it passes locally: `ponens trace validate <file>` and `ponens trace check <file>`.
3. Add an entry to `manifest.json` to feature it in the viewer.

CI will then keep it honest: any sample that stops validating fails the build.

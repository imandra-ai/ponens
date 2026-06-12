# CodeLogician Traces

View and inspect [Imandra CodeLogician](https://codelogician.dev) reasoning traces inside VS Code.

## Features

- **Flow View** -- Step through the agent's action trace with phase-grouped cards, data connectors, and a detail panel showing IML source, verification results, and counterexamples.
- **Lineage View** -- Trace any artifact back through its full dependency chain.
- **Artifacts (DAG)** -- Interactive node-link diagram of the artifact dependency graph with pan, zoom, and detail overlays.
- **Reasoning Funnel** -- Dashboard showing the formal reasoning pipeline: formalizations, verification goals, proofs, edge cases, and test generation.
- **Policies Dashboard** -- Compliance view with pass/fail status, LTL formulas, and severity grouping.
- **Voronoi Region Diagrams** -- Interactive decomposition diagrams for exploring edge-case regions.
- **Reference Models** -- Inspect reference models, their IML source, verification goals, and linked policies.
- **PDF Report** -- Generate a print-ready report of the full trace (browser view).
- **Dark and Light Themes** -- Full dual-theme support with readable syntax highlighting in both modes.

## Getting Started

1. Open the Command Palette (`Cmd+Shift+P`) and run **CodeLogician: Open Trace Viewer**.
2. The viewer opens in a side panel with a bundled demo trace.
3. Use the dropdown to switch between demo traces or select your own file.

## Loading Traces

| Method | How |
|---|---|
| **Demo selector** | Use the dropdown in the header to switch between bundled demos |
| **File picker** | Select "Select a file to view" from the dropdown |
| **Right-click** | Right-click any `.json` file in the Explorer and choose "Open with CodeLogician Traces" |
| **Configuration** | Set `codelogician.traceFile` in settings to auto-watch a trace file |
| **Browser** | Click the "Browser" button to open the current trace in a full browser window |

## Commands

| Command | Description |
|---|---|
| `CodeLogician: Open Trace Viewer` | Open the viewer in a side panel |
| `CodeLogician: Open in Browser` | Open the current trace in the browser |
| `CodeLogician: Select Trace File` | Pick a trace JSON file to watch |
| `CodeLogician: Select Demo Trace` | Choose from bundled demo traces |

## Configuration

| Setting | Description |
|---|---|
| `codelogician.traceFile` | Path to a trace JSON file to auto-watch on startup. Supports workspace-relative paths. |

## Trace Format

The viewer accepts CodeLogician trace JSON files in both v1.0 and v1.1 formats. A normalization layer transparently handles version differences.

## Learn More

- [CodeLogician](https://codelogician.dev)
- [Imandra](https://www.imandra.ai)

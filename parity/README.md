# Evaluator parity harness

There are two independent implementations of the ponens trace-policy language:

| Engine | File | Used by |
| --- | --- | --- |
| Browser evaluator | [`website/src/lib/ltl.mjs`](../website/src/lib/ltl.mjs) | the `/playground` page |
| CLI runtime evaluator | [`cli/ponens/trace.py`](../cli/ponens/trace.py) | `ponens trace check` (the oracle) |

They share neither a trace format nor an implementation, so they can drift. The
playground's contract (stated at the top of `ltl.mjs`) is that it must **never
disagree** with `ponens trace check`: for any policy it either returns the same
verdict, or it abstains (`{supported: false}`) and points the user at the CLI —
it must never show a concrete verdict the CLI would contradict.

This harness encodes that contract.

## How it works

`cases.json` holds a corpus of `(formula, canonical trace)` pairs. Each canonical
trace is rendered into *both* engines' native shapes by adapters in the two
runners, both verdicts are computed, and the harness asserts, per case:

> **JS abstains, or `JS.verdict == CLI.verdict`.**

- `run_js.mjs` — imports `ltl.mjs`, adapts the canonical trace to the browser's
  flat position-indexed array, prints per-case verdicts as JSON.
- `check_parity.py` — the orchestrator. Adapts the canonical trace to the CLI's
  `{actions: [...]}` shape (1-based ids, `result_summary` / `vg_result` /
  `request.path` fields), evaluates in-process via `ponens.trace.evaluate_policy`,
  shells out to `run_js.mjs`, compares, and exits non-zero on any violation.

Run locally (needs `node` on PATH and the CLI importable — `pip install -e ./cli`):

```sh
python3 parity/check_parity.py
```

## Canonical action fields

| Field | Meaning | Browser shape | CLI shape |
| --- | --- | --- | --- |
| `type` (req.) | action type | `action.type` | `action.type` |
| `category` | gateway/reasoning/activity | `action.category` | `action.category` |
| `target` | file/artifact the action touches | `action.target` | `request.path` |
| `status` | completed/failed/proved/refuted/sat | `action.status` | `result_summary` (completed/failed) or `vg_result.status` (proved/refuted/sat) |
| `rationale` | bool: rationale present | truthy `action.rationale` | non-empty `rationale` string |
| `flags` | lowercase predicate words | `action.flags[]` membership | surfaced in `detail` for the CLI's keyword fallback |

Any operator dialect works — `∧ ∨ ¬ → ≠ ∅`, `/\` `\/`, and `&&` `||` all parse in
both engines. Past/scoped/`X` operators must appear under `G` — their bare
top-level semantics differ between the engines and never occur in real policies.

## Unified semantics

The two engines were reconciled (the browser was extended to match the CLI oracle).
What used to diverge and now agrees:

1. **Operator dialects.** Both engines accept all three: Unicode `∧ ∨`, the
   browser's `/\` `\/`, and the CLI's `&&` `||`.
2. **`start_event` / `end_event`.** Both read the trace-level `trigger` / `outcome`
   type (`start_event` ⇔ trigger ∈ {TaskReceived, TriggeredByEvent}; `end_event` ⇔
   outcome ∈ {ProcessCompleted, ProcessAborted, ProcessInterrupted}). Set them via a
   case's `trigger` / `outcome` fields (and the playground's trigger/outcome
   selectors).
3. **CamelCase atom resolution.** A CamelCase atom is an exact action/artifact type
   match in both engines (so `Read` does **not** match `ReadFile`). `GitPush` and
   `Deploy` were added to the CLI's known types.
4. **Custom predicates.** Lowercase/snake_case predicates are matched by substring
   keyword (underscores read as spaces) against the action text in both engines, and
   `high_stakes_path` is a path-pattern check on the target in both.

`"divergent": true` remains supported for any future intentional mismatch (reported
but non-failing), but the corpus currently has none.

Adding a case: drop a new object into `cases.json` with `expect` (the intended
verdict, which also locks the browser side as a regression guard), or mark it
`unsupported` / `divergent`. CI runs `.github/workflows/parity.yml` on any change
to either evaluator or to this directory.

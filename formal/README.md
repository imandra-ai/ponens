# `formal/`: Ponens's own logic, proved in IML

The Ponens reasoning framework is modelled specification-first in IML and proved by
ImandraX, so the system verifies its own logic. The framework is a single state machine
whose state is the trace. Each invariant that a silent bug would break is a theorem over
that state.

## Re-verify

`check.sh` is the regression gate. It reads `manifest.toml`, runs
`codelogician-lite check --json` on every model file, and compares the proof obligation
(PO) counts with the manifest:

```
IMANDRAX_ENV=prod ./check.sh
```

It needs `codelogician-lite` (`uv tool install codelogician`) and `jq` on `PATH`, and
`IMANDRA_UNI_KEY` or `IMANDRAX_API_KEY` in the environment. It sets
`CODELOGICIAN_TIMEOUT=600` unless you set it yourself. Set `VERBOSE=1` to print the full
output of a failing file.

To check one file, run it from `machine/` so that `[@@@import ...]` paths resolve:

```
cd machine && codelogician-lite check goals.iml
```

An import is trusted: checking `goals.iml` does not re-check `machine.iml`. Check each
file on its own, which is what `check.sh` does.

## The state machine (`machine/`)

The state is `{ actions; artifacts }`: the ordered action log and the artifact lineage
DAG. Every artifact is produced by a recorded action. The transitions are `extend`
(record an action and the artifact it produces), `supersede` (retire a target's current
revision) and `merge` (join two branches of a shared base). The model is split into one
file per concern, 194 POs in total, all proved:

| File | POs | What it proves |
|---|---|---|
| `machine.iml` | 59 | `wf` (I2 lineage-ordered, I3 grounded, increasing ids, closed lineage) holds of `[]` and is preserved by `extend` and `supersede`; I1 append-only; ids are unique; the dependency closure |
| `freshness.iml` | 9 | I4: `fresh_is_sound`, `no_false_fresh`, and no-false-fresh over the dependency closure |
| `reuse.iml` | 5 | I5: never reuse stale evidence; the trace grows by at most one; the reuse step preserves `wf` |
| `goals.iml` | 20 | the met axis: met is all-done, at_risk never demotes, progress is in [0,1], done and not at risk means fresh |
| `policy.iml` | 6 | the governed axis: LTLf `G` and `F` over the action timeline |
| `orthogonality.iml` | 2 | governed and met are independent |
| `merge.iml` | 22 | `classify` totality, no-false-fresh and never-guess; `merge_preserves_wf`; carried-forward results stay fresh |
| `identity.iml` | 30 | `resolve_component` never conflates; append-only alias equivalence |
| `escalation.iml` | 9 | the verify ladder always decides, a verdict has a witness, the first decider wins |
| `rename.iml` | 6 | `find_rename` never guesses when ambiguous; every accepted rename is justified |
| `verdict.iml` | 6 | every terminal verdict lands somewhere; a defect always carries a residual |
| `state.iml` | 20 | `wf_state` (artifact DAG well-formed, every artifact listed by its producer action) is preserved by `extend_state`, `supersede_state` and `merge_state` |

`manifest.toml` is the single source of truth and drives `check.sh`.

## The trace and policy reference model (`trace-policy-model/`)

A layered, executable IML model of the trace and policy vocabulary itself: types, accessors, binding,
runtime, evaluation, a policy library, and worked examples (read `01_trace_policy_types` to
`09_trace_policy_examples`; each `[@@@import]`s the earlier layers). This is the concrete vocabulary the
Trace and Policy specs project to a wire format.
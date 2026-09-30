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

To check one file, run it from its own directory so that `[@@@import ...]` paths resolve:

```
cd core && codelogician-lite check goals.iml
```

Checking a file also checks the files it imports, and a failure in an import fails the
file. `check.sh` counts only a file's own POs (a PO from an import is named after the
import alias, such as `Core.Trace.wf_empty`), so the per-file counts add up to the total.

## The state machine (`core/`)

The state is `{ actions; artifacts }`: the ordered action log and the artifact lineage
DAG. Every artifact is produced by a recorded action. The transitions are `extend`
(record an action and the artifact it produces), `supersede` (retire a target's current
revision) and `merge` (join two branches of a shared base). `core.iml` defines the state
in three modules: `Artifact` (ids, kinds, the artifact record), `Trace` (the artifact DAG
and its transitions) and `State` (actions and artifacts together). The other files are
queries over the state, the theorem that two of them are independent, and the two
operations that combine a query with a transition. Start with `core.iml`;
`examples.iml` evaluates each part on a small trace.

| File | POs | What it proves |
|---|---|---|
| `core.iml` | 72 | `wf` (I2 lineage-ordered, I3 grounded, increasing ids, closed lineage) holds of `[]` and is preserved by `extend` and `supersede`; I1 append-only; ids are unique; the dependency closure; `wf_state` (every artifact listed by its producer action) is preserved by `extend_state` and `supersede_state` |
| `freshness.iml` | 9 | I4: `fresh_is_sound`, `no_false_fresh`, and no-false-fresh over the dependency closure |
| `goals.iml` | 20 | the met axis: met is all-done, at_risk never demotes, progress is in [0,1], done and not at risk means fresh |
| `policy.iml` | 6 | the governed axis: LTLf `G` and `F` over the action timeline |
| `axes.iml` | 2 | governed and met are independent |
| `reuse.iml` | 5 | I5: never reuse stale evidence; the trace grows by at most one; the reuse step preserves `wf` |
| `merge.iml` | 27 | `classify` totality, no-false-fresh and never-guess; `merge_preserves_wf`; carried-forward results stay fresh; `merge_state` preserves `wf_state` |

The paper names a third axis, `certified` (the definition of done was reviewed by
someone other than the doer). It is not modelled yet.

## The pipeline (`pipeline/`)

Models of the procedures that produce what goes into the state. They do not read or
write the state, and no file here imports `core/`.

| File | POs | What it proves |
|---|---|---|
| `identity.iml` | 31 | `resolve_component` never conflates two components; append-only alias equivalence |
| `rename.iml` | 6 | `find_rename` never guesses when ambiguous; every accepted rename is justified |
| `escalation.iml` | 9 | the verify ladder always decides, a verdict has a witness, the first decider wins |
| `verdict.iml` | 6 | every terminal verdict lands somewhere; a defect always carries a residual |

The two directories hold 193 POs in total, all proved.

`manifest.toml` is the single source of truth and drives `check.sh`.

## The trace and policy reference model (`trace-policy-model/`)

A layered, executable IML model of the trace and policy vocabulary itself: types, accessors, binding,
runtime, evaluation, a policy library, and worked examples (read `01_trace_policy_types` to
`09_trace_policy_examples`; each `[@@@import]`s the earlier layers). This is the concrete vocabulary the
Trace and Policy specs project to a wire format.
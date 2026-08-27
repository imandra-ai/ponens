# `formal/` — Ponens's own logic, proved in IML

The Ponens reasoning framework modelled **specification-first in IML** and proved by **ImandraX** — the
system verifying its own logic. The whole framework is now a **single state-transition machine in which the
trace is the state**; every invariant a silent bug would break is a theorem over that one state.

Re-verify (the regression gate):

```
IMANDRAX_API_KEY=$IMANDRA_UNI_KEY ./check.sh        # reads manifest.toml
```

or directly: `imandrax-cli check formal/machine/trace_machine.iml` (its header states the `RECHECK` line).

## The state machine — the trace IS the state (`machine/trace_machine.iml`)

Ponens as a state-transition machine. The state is `{ actions; artifacts }` — the ordered action log **and**
the artifact lineage DAG (events are first-class; every artifact is produced by a recorded action). The
transitions are `extend` (record an action + the artifact it produces), `supersede` (retire a target's
current revision), and `combine` (a two-parent merge). Over this one state, in a single file — **195 POs, 0
failures** — it proves the entire evidence logic:

| Concern | In the machine |
|---|---|
| **state** (actions + artifacts) | `wf_state` = artifact DAG well-formed **and** every artifact grounded in a recorded action; preserved by `extend_state`/`supersede_state`/`combine_state` |
| **I1** append-only | `extend` grows the state; `supersede` only flips flags |
| **I2** lineage-ordered / acyclic | `lineage_ordered` preserved by `extend`; no self-reference |
| **I3** evidence-grounded | `grounded` preserved by `extend` |
| **`wf` = I1∧I2∧I3** | an *inductive invariant*: `wf []`, preserved by every transition |
| **I4** freshness | `freshness_of` query, recomputed vs the current model; `fresh_is_sound`, `no_false_fresh` |
| **I5** reuse | `plan_reuse` reads the state; never-reuse-stale; conditional growth; preserves `wf` |
| **goals** (met axis) | `met` = all-done; `at_risk_never_demotes`; `progress ∈ [0,1]`; done-not-at-risk ⇒ fresh |
| **policies** (governed axis) | LTLf `G`/`F` over the timeline; **`governed ⊥ met`** |
| **merge** (composition) | `classify` totality / no-false-fresh / never-guess; `combine_preserves_wf` |
| **component identity** | `resolve_component`: **never-conflate**; append-only alias equivalence |
| **verify escalation** | the ordered ladder: always decides; a verdict has a witness; first-decider-wins |
| **rename ambiguity** | `find_rename`: never guess when ambiguous; every accepted rename is justified |
| **verdict totality** | every terminal verdict lands somewhere (a defect ⇒ a residual) |

`manifest.toml` is the single source of truth and drives `check.sh`. (Some secondary properties of the
former standalone models were intentionally simplified away when unifying — the freshness rescue/worst-wins
lattice, store revision-numbering, lineage no-islands presence, and the opaque-contract taxonomy; the machine
keeps the load-bearing invariants.)

## The trace + policy reference model (`trace-policy-model/`)

A layered, executable IML model of the trace and policy vocabulary itself — types, accessors, binding,
runtime, evaluation, a policy library, and worked examples (read `01_trace_policy_types` →
`09_trace_policy_examples`; each `[@@@import]`s the earlier layers). This is the concrete vocabulary the
Trace and Policy specs project to a wire format.

## Notes for authoring more models (ImandraX build specifics)

- `theorem`s with `[@@by …]` are discharged at admission time (`check`); no separate open VGs.
- List-recursion theorems need `[@@by induct ()]`; predicate-distributes-over-append/concat lemmas tagged
  `[@@rw]`. Prefer append/concat *rewrite* lemmas over accumulator inductions — a fold `f (extend acc x) r`
  will not generalize the accumulator under `induct ()`; exploit per-node-self-contained invariants so the
  predicate distributes over `@` (see `lineage_ordered_concat` / `grounded_concat`).
- Multi-hint form is `[@@by [%use lemma args] @> auto]` (chain with `@>`), **not** `[@@by [l1; l2]]`.
- Real division bounds: abstract the quotient and use the cancellation identity
  (`y <> 0. ==> y *. (x /. y) = x`), reducing to an RCF-decidable polynomial — see `real_ratio_bounded` /
  `g_progress_bounded`.

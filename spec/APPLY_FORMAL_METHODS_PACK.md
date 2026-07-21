# Apply Formal Methods Where It Makes Sense — ponens Policy Pack

This pack governs the **pragmatic adoption of formal methods**: use a theorem
prover (ImandraX) exactly where correctness is high-stakes and machine-checkable,
and — once formal methods are in play — run the pipeline rigorously end to end.
It is authored by Imandra for the **CodeLogician / SpecLogician** formal-reasoning
workflow.

**Source:** Imandra — CodeLogician / SpecLogician formal-reasoning pipeline.

## Why this maps onto ponens

Formal methods pay off unevenly. Proving everything is wasteful; proving nothing
is negligent for the code that actually carries risk — money math, state machines,
access control, bounds, parsing. This pack encodes *where* to apply formal effort
and *how* to apply it well, as computable policies over the reasoning trace.

The pack has two halves:

- **Coverage — "where it makes sense".** High-stakes code must be backed by a
  proof or a region decomposition **in its lineage** before it ships. The
  high-stakes surface is **data-driven**: a producer sets the trace's
  `high_stakes_paths` (e.g. from a formalization-target scan that scores money /
  state-machine / access-control code), so "where it makes sense" is decided by
  evidence, not hard-coded paths.
- **Rigor — "do it properly".** Once the pipeline runs, it must run correctly:
  verification goals are formalized first, refuted goals get fixed, decompositions
  produce tests, and generated tests trace back to a decomposition.

| Formal methods | ponens |
| --- | --- |
| The formal-reasoning session record | the **trace** |
| A discipline of the pipeline | a **policy** (temporal formula) |
| Hard requirement vs good practice | `error` (Red) / `warning` (Amber) |
| The code that warrants a prover | `high_stakes_paths` on the trace |

## Trace model

Reuses the existing formal-reasoning vocabulary — actions `Formalize`,
`DefineVG`, `Verify`, `Decompose`, `GenerateTests`, `EditFile`; artifacts
`IMLModel`, `VerificationResult`, `Decomposition`, `GeneratedTests`; predicates
`proved`, `sat`, `refuted`, and the data-driven `high_stakes_path`. No new
action types.

## Policies

### Coverage — apply where it matters

| Policy | Sev | Formula |
| --- | --- | --- |
| `reasoning_required_for_high_stakes` | error | `G(EditFile ∧ high_stakes_path → P_chain(VerificationResult(proved ∨ sat) ∨ Decomposition))` |

### Rigor — a proper pipeline

| Policy | Sev | Formula |
| --- | --- | --- |
| `formalize_before_verify` | error | `G(DefineVG → P_chain Formalize)` |
| `counterexample_triggers_fix` | warning | `G(Verify ∧ refuted → F(EditFile))` |
| `decomposition_drives_tests` | warning | `G(Decompose → F(GenerateTests))` |
| `generated_tests_require_decomposition` | error | `G(GeneratedTests → Decomposition ∈ ancestors(derived_from))` |

## How "high-stakes" is decided

`high_stakes_path` matches an action's target against the trace's
`high_stakes_paths` list (substring match), falling back to demo defaults when
the field is absent. A formalization-target scan is the natural producer: it
scores which functions warrant ImandraX and writes their files into
`high_stakes_paths`, so this pack's coverage requirement tracks the same
opportunities the scan surfaces.

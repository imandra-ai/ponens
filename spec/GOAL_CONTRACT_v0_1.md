# Goal Contract — accomplish these things, subject to these policies (v0.1)

**Status:** design spec. Refines [Trace Spec §18 (Goals & Acceptance)](TRACE_SPEC_v1_7.md) and
complements [Goal Faithfulness v0.1](GOAL_FAITHFULNESS_v0_1.md), [Policy Spec v0.2](POLICY_SPEC_v0_2.md),
and the [Apply Formal Methods Pack](APPLY_FORMAL_METHODS_PACK.md). Additive and backward-compatible —
existing text-bound acceptance items keep resolving (§8). Driven by the CodeLogician Desktop goal loop
(`declare_goal` → per-session active goal → `ponens trace enrich`).

## 1. Motivation — two unstructured seams

§18 makes acceptance rigorous *once an item binds to evidence*. But the binding for the two kinds that
carry the load is a **fuzzy text query**, and evidence **rigor/provenance is implicit**:

1. **Binding by description text.** A `property` item binds via `{symbol?, property?}` where `property`
   is *"a keyword expected in the goal description"*. Resolution is *"does this keyword appear in the
   VG's description string."* When the agent proves `rank_transitivity` but the VG description reads
   "rank transitivity", the substring misses and the criterion silently stays **Not checked** even
   though it is proved. (This is the desktop's "goal never ticks" bug — a *structural* defect, not a
   UI one.)
2. **Provenance is unspecified.** "A test suite" and "a test suite generated from an exhaustive region
   decomposition" resolve identically, though one is far stronger. Rigor lives nowhere.

This spec fixes both by making the goal a **contract** with two explicit halves:

> **Accomplish these things** — typed acceptance criteria over code components, resolved by artifact
> **lineage** (not text). **Subject to these policies** — the rigor/governance bar, declared on the
> goal with sensible defaults.

## 2. Three orthogonal axes (all declared in the goal)

| Axis | Question | Mechanism | Principal |
| --- | --- | --- | --- |
| **Met** | Does evidence of the required *kind* exist for this component? | criterion ↔ artifact by kind + component **lineage** (§4) | the doer's evidence |
| **Governed** | Is that evidence *rigorous enough* / does it obey the rules? | the goal's **policies** over its cone (§5) | org / context (a pack) |
| **Certified** | Is the definition of done itself *right*? | criteria review (Faithfulness v0.1) | a party ≠ the doer |

> **Trustworthy done = met ∧ governed ∧ certified.** Each is independent and separately reported. A
> criterion can be **met but not governed** — evidence exists but is too weak for the goal's pack —
> which today reads silently as "done" and here becomes a first-class, surfaced state.

This *refines* Faithfulness v0.1 §6: evidence **strength/provenance moves out of faithfulness grading
and into the governed axis** (policies over lineage). Faithfulness keeps *rightness* — coverage,
review, non-retrofit; policy owns *rigor*.

## 3. Acceptance criterion = a typed evidence requirement

A criterion names a **code component**, the **kind of evidence** that satisfies it, and (for
`verification`) the **property** to establish. It does **not** encode strength — that is policy (§5).

```ocaml
type evidence_req =
  (* proved verification goal over a model autoformalized from the component *)
  | Verification of { property : string; expect : [ `Proved | `Refuted | `Explored ] }
  (* a generated test suite for the component; all pass. Provenance (direct vs
     decomposition-backed) is NOT asserted here — it is a policy (§5). *)
  | Tests        of { min : int option; all_pass : bool }
  (* a region decomposition of the component's input space *)
  | Decomposition of { min_regions : int option; boundaries : bool }

type acceptance_criterion = {
  id        : string;
  statement : string;                       (* human "what must be true" — for reading + certification *)
  component : { function_ : string; file : string option };
  evidence  : evidence_req;
  required  : bool;                         (* Faithfulness v0.1 *)
  covers    : string list;                  (* intent clauses it covers — Faithfulness v0.1 §5 *)
}
```

The evidence kinds and their provenance chains (the chain is *recorded in the trace*, not restated in
the criterion):

| Kind | Provenance (pipeline that yields it) | Met when |
| --- | --- | --- |
| **Verification** | component → autoformalize → `IMLModel` → `DefineVG(property)` → `Verify` | a `VerificationResult` for that VG is **proved** |
| **Tests** | component → *(optionally)* `Decompose` → `GenerateTests` → suite | suite exists (≥ `min`) and **all pass** |
| **Decomposition** | component → autoformalize → `Decompose` → region map | regions cover the domain (≥ `min_regions`, boundaries) |

## 4. Resolution by lineage (the #1 fix)

A criterion resolves to **met** when the trace holds an artifact of the required kind **whose lineage
roots in autoformalizing `component.function_`**, meeting the pass condition. Resolution reads
structured provenance, never a description string.

- **Verification** — find `VerificationResult`s whose goal's model artifact (`IMLModel`) has the
  component in its lineage AND whose VG `property_name == property`; take the latest by producer action;
  `met` iff its status matches `expect` (default `Proved`).
- **Tests** — find a `Tests` artifact whose lineage roots in the component; `met` iff `count ≥ min`
  (when set) and all pass.
- **Decomposition** — find a `Decomp` artifact rooted in the component; `met` iff `regions ≥ min_regions`.

Matching is on **artifact identity + lineage + structured fields** (`property_name`, `target_symbol`,
producer chain), which the reasoning tools already record. No `_vg_matches`-style substring search.

*Recommended (airtight):* the verify/decompose/gen-test tools may stamp each produced artifact with
`satisfies: <criterion_id>` — a back-reference — so resolution is by exact id with no matching at all.
Optional; lineage matching is the floor.

## 5. Subject to policies — governance on the goal

A goal declares the packs/policies that govern it. Governance is **layered**, so a goal that names
nothing still has a floor, and a regulated project raises the bar in one place:

```ocaml
type goal_policies = {
  packs    : string list;   (* e.g. ["apply_formal_methods"], ["do_178c"] *)
  policies : string list;   (* individual policy ids, additive *)
  disabled : string list;   (* pack/policy ids turned OFF at this layer — recorded, never silent (§6) *)
}
(* effective set = (goal.packs ∪ project_default_packs ∪ GLOBAL_BASELINE) \ disabled(any layer) *)
```

| Layer | Set by | Example |
| --- | --- | --- |
| **Global baseline** | this spec | no `required` criterion is edit-only; proofs carry obligations / no unverified axioms |
| **Project default** | repo / org config | a fintech repo defaults to `apply_formal_methods`; a DO-178C project to `do_178c` |
| **Goal override** | the goal | this component additionally requires the stricter pack |

### Proposed by the agent, selected by a human

The agent MAY **propose** packs/policies — the high-stakes scan flags money math → it suggests
`apply_formal_methods`. A proposal is recorded on the goal but is **not effective on its own**.

> **Normative rule.** The party that *meets* a goal must not be the sole party that sets its **rigor
> bar** — parallel to Faithfulness v0.1's rule for the *definition of done*.

The **effective** set is what a *human* has sanctioned: the **global baseline** (this spec) and the
**project default** (a prior org decision) are already human-set and apply from the start; per-goal
additions the agent proposes take effect only once a human (a party ≠ the doer) **approves** them. The
trace records **proposed vs approved**, so the audit shows whether the human raised, lowered, or
rubber-stamped the bar. Approving the effective set is part of **certification** (§6) — you certify the
criteria *and* the bar they were held to.

**Governed** = no effective `error`-severity policy fails **unwaived** over the goal's **relevance cone**
(the trace region the goal touches — §18); see §6 for blocking + overrides. The trace records, per
goal: `{ criteria, effective_policies, disabled, evidence, per-policy verdict, waivers }` — a complete,
reproducible contract.

The provenance rigor the criterion deliberately omits is exactly what these policies assert over
lineage — and most of it **already exists** in [`apply_formal_methods`](APPLY_FORMAL_METHODS_PACK.md):

- high-stakes code is backed by a proof **or** a decomposition *in its lineage*;
- verification targets an **autoformalized** model (not hand-authored IML);
- refuted goals get fixed; decompositions produce tests; **generated tests trace back to a decomposition**.

So "tests must be decomposition-backed" is not a criterion field — it is a policy the goal opts into.

## 6. Composition, blocking & overrides

Per goal: `met` (all required criteria resolved), `governed`, `certified` (Faithfulness v0.1).

**Severity decides blocking.** A policy is `error` (Red) or `warning` (Amber):

- an **`error`** policy failing over the cone → **blocks "done"** (the goal is *met but not governed*,
  and NOT done);
- a **`warning`** failing → annotates, does not block.

So **Done = met ∧ governed**, where *governed* = no `error`-severity policy fails **unwaived** over the cone.

**Overrides are explicit and recorded — never silent.** You can proceed past an `error`, but only by
turning the rule off *in the record*:

| Override | Scope | Recorded as |
| --- | --- | --- |
| **Disable** a policy / pack | a layer (global / project / goal) — e.g. this project doesn't run DO-178C | `disabled` on the effective-policy set (which ids, where, why) |
| **Waive** a specific failure | one criterion instance — "accept this refund suite isn't decomposition-backed" | a residual `status: waived` + justification + waiver identity (ideally a party ≠ the doer) |

A disabled policy does not evaluate; a waived failure does not block — **but the trace shows both**. So
"done" always names the rules that were turned off and the risks accepted, and by whom. **There is no
path to a green goal that hides a bypassed `error`** — that invariant is the entire point of blocking
by default.

**Certification sees the overrides.** Certifying a goal certifies its *effective* bar: a goal certified
with `apply_formal_methods` **disabled** is a visibly weaker claim than one certified with it enforced.
The reviewer approves the definition **and** the overrides, or rejects them.

The enriched goal exposes `met / governed / certified` plus the residuals that explain any gap:

- required criterion **not met** → open acceptance gap;
- criterion **met** but an `error` policy fails → **blocking governance residual** (until fixed or waived);
- criterion **met** but a `warning` policy fails → advisory governance residual;
- uncovered clause / weak / retrofitted definition → faithfulness residuals (v0.1).

## 7. Backward compatibility & migration

- Legacy `property/change` items (text bindings) **still resolve** via the §18 path; new typed criteria
  resolve via §4. `enrich` accepts both; a criterion is typed iff it carries `component` + `evidence`.
- The JS resolver (`viewer/core/faithfulness.mjs`) and the Python resolver (`cli/ponens/goals.py`)
  **must move together** — the parity harness gates it.
- Goals with no `policies` behave as today plus the global baseline (§5) — no behavior change unless a
  baseline policy actually bites.

## 8. What changes where

| Component | Change |
| --- | --- |
| `declare_goal` tool schema | acceptance items gain `component` + typed `evidence`; goal gains `policies`; drop "keyword in description" guidance |
| `cli/ponens/goals.py` (`resolve_item`) | lineage-based resolution per §4; retire `_vg_matches` text search for typed items |
| verify / decompose / gen-test tools | record structured provenance (component in lineage, `property_name`); optionally stamp `satisfies` (§4) |
| desktop `goalStore` / `GoalHome` / Manage UI | author criteria via structured fields (kind + component + property/expect); render met / governed / certified |
| policy engine | evaluate a goal's effective policy set over its cone; default layering (§5) |
| `viewer/core/faithfulness.mjs` | mirror §4 resolution (parity) |

## 9. Open questions

1. **Component cardinality** — is a criterion always 1 component, or may `component` be a set ("these
   three functions each verified")? (Proposed: singular; use one criterion per component for clarity.)
2. **Property identity** — does the criterion pin a *named, reusable* property (strongest — you specify
   the spec), or just `evidence.kind` and let the agent choose? (Proposed: `verification` pins a
   property name; other kinds don't.)
3. **Baseline contents** — exactly which rules are non-optional global baseline vs. opt-in pack.
4. **`satisfies` back-reference** — adopt now (airtight) or defer behind lineage matching.

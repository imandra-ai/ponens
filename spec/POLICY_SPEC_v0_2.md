# Policy Specification

## Version

**Version:** 0.2  
**Status:** Draft  
**Format:** Canonical typed specification with OCaml / IML-oriented DSL  
**Positioning:** Companion specification to the Trace Specification

> **Changes in 0.2 (additive).** Adds the **residual-surface vocabulary** (§15.1) — the `residuals` collection, residual field accessors, and the severity ordering — so policies can quantify over a trace's declared negative space (Trace Specification §13). Adds the **standard residual-surface policies** (§17.4). Existing policies are unaffected.

---

# 1. Purpose

A **policy** is a governance formula interpreted over a trace or review case.

Policies are **Computable Governance** — governance you *run*, not a checklist or a sign-off. A
policy is a machine-checkable rule, evaluated automatically over the structured trace to a pass /
fail: a real gate, not a social "Approved." This is **conformance checking** — the established
technique behind runtime verification and declarative process mining (temporal logic over finite
traces, e.g. DECLARE) — applied to the reasoning traces of AI agents.

Policies do **not** define execution history.  
They constrain, require, forbid, or validate properties of that history.

A policy may also **require a reasoner** — an automated-reasoning tool (e.g. CodeLogician,
ImandraX, a model checker, an SMT solver) that produces the verification artifacts a policy depends
on. The optional `reasoner` field names one from the **reasoner registry** (`gallery/reasoners`),
so a policy can demand not just *that* a claim was verified, but *by what* — the engine through
which a claim becomes *established* rather than merely asserted.

This specification defines:

- the **policy object model**
- the **policy evaluation model**
- the **policy DSL**
- the **formal role of policies relative to traces**
- the **binding between policy predicates and the trace schema**
- an **OCaml / IML-oriented canonical representation** of policy formulas

---

# 2. Relationship to the Trace Specification

This document is intended to be used together with the trace specification.

The split is:

- the **trace specification** defines what a trace is semantically
- the **policy specification** defines what a policy is semantically
- the **binding section** defines how policy formulas are interpreted over concrete trace objects and fields

A good one-line summary is:

> **Traces define the execution world; policies define the rules evaluated over that world.**

More formally:

- let `T` be the set of valid traces defined by the trace specification
- let `φ` be a well-formed policy formula in this DSL
- then `τ ⊨ φ` means that trace `τ ∈ T` satisfies policy `φ`

This document defines `φ` and the meaning of `⊨`.

---

# 3. Scope

This specification currently focuses on policies interpreted over:

- a **single trace**
- optionally a **review case context** when explicitly enabled by the binding layer

The core policy language is primarily designed for:
- agent workflow constraints
- reasoning requirements
- lineage requirements
- conformance requirements
- approval and governance requirements

---

# 4. Design Principles

The policy system is built around six core principles:

1. **Policies are formulas, not prose**  
   Human-readable descriptions are helpful, but the authoritative meaning of a policy is its formula.

2. **Trace semantics are primary**  
   Policies are interpreted over traces; they do not redefine trace meaning.

3. **The DSL is reasoner-agnostic**  
   Policies should be written against semantic roles, not engine-specific artifact names or tool invocations.

4. **Temporal + structural expressiveness**  
   Policies must express both ordering constraints and structural / lineage constraints.

5. **Canonical typed model first**  
   The authoritative policy representation is a strict typed model suitable for OCaml / IML reasoning.

6. **Interchange is derived**  
   JSON/Pydantic projections are derived from the canonical model.

---

# 5. What a Policy Is Semantically

A policy is a well-formed formula interpreted over a trace.

Informally, a policy says things like:

- something must happen before a commit
- a high-stakes edit must have upstream reasoning evidence
- a target must conform to an approved reference artifact
- a destructive action must have approval in its lineage
- a result must be reproducible before approval
- generated tests must derive from a state-space analysis

Policies may constrain:

- **temporal order**
- **action categories and types**
- **artifact existence**
- **artifact lineage**
- **field values**
- **review / approval state**
- **reproducibility metadata**

---

# 6. Canonical Policy Object Model

## 6.1 Policy object

```ocaml
type policy_severity =
  | Info
  | Warning
  | ErrorSeverity

type policy_scope =
  | TraceScope
  | ActionScope
  | ArtifactScope
  | ModuleScope

type policy_kind =
  | TraceInvariant
  | ApprovalRequirement
  | ReasoningRequirement
  | LineageRequirement
  | ReferenceIntegrity
  | ConformanceRequirement

type policy_selector =
  { action_type : string option
  ; artifact_type : string option
  ; artifact_role : string option
  ; category : string option
  ; path_matches : string option
  ; path_matches_any : string list
  }

type policy =
  { policy_id : string
  ; name : string
  ; description : string option
  ; severity : policy_severity
  ; scope : policy_scope
  ; kind : policy_kind
  ; applies_when : policy_selector option
  ; formula : policy_formula
  ; reference_artifact_id : string option
  }
```

## 6.2 Semantics of policy fields

- **`policy_id`** — stable identifier
- **`name`** — short human-readable name
- **`description`** — explanatory prose; not authoritative
- **`severity`** — consequence or significance of failure
- **`scope`** — the primary level at which the policy is interpreted
- **`kind`** — governance intent classification
- **`applies_when`** — optional selector narrowing the intended applicability
- **`formula`** — the authoritative policy meaning
- **`reference_artifact_id`** — optional approved reference artifact tied to this policy

The `formula` field is authoritative.  
If `description` and `formula` disagree, `formula` wins.

---

# 7. Policy Evaluation Model

## 7.1 Policy evaluation object

```ocaml
type policy_evaluation_status =
  | Passed
  | Failed
  | UnknownEvaluation
  | NotApplicable

type policy_evaluation =
  { policy_id : string
  ; status : policy_evaluation_status
  ; checked_at_action_id : int option
  ; evidence_action_ids : int list
  ; evidence_artifact_ids : string list
  ; violating_action_ids : int list
  ; violating_artifact_ids : string list
  ; note : string option
  }
```

## 7.2 Evaluation semantics

A policy evaluation is a concrete record of checking a policy against a trace.

- `Passed` means the policy formula was satisfied
- `Failed` means the formula was violated
- `UnknownEvaluation` means the checker could not determine the result
- `NotApplicable` means the policy did not apply in the current context

Evidence and violation references are supporting metadata; they are not themselves the formal semantics of the policy.

---

# 8. Satisfaction Relation

Let:

- `T` be the set of valid traces
- `τ ∈ T` be a trace
- `φ` be a well-formed policy formula

Then:

```text
τ ⊨ φ
```

means:

> trace `τ` satisfies policy formula `φ`

and:

```text
τ ⊭ φ
```

means:

> trace `τ` does not satisfy `φ`

This specification defines the syntax and intended semantics of `φ`.

---

# 9. DSL Overview

The policy DSL is:

- **LTL-based**
- extended with **past-time operators**
- extended with **scoped temporal operators**
- extended with **first-order predicates**
- extended with **lineage predicates**
- extended with **field predicates**
- optionally extended with **quantifiers and set comprehensions**

This means the DSL is not merely propositional LTL.  
It is a policy language over structured traces — a scoped, first-order, finite-trace temporal logic.

The foundation is deliberately well-established: LTL over finite traces (LTL_f) is the semantics
behind declarative process mining (DECLARE) and runtime verification, where it has been used for
conformance checking of event logs for years. This DSL extends that proven core with the
predicates and quantifiers a *typed* trace needs — lineage, residuals (the declared negative
space), and field access — so a policy can govern not just the action sequence but the trace's
structure.

---

# 10. Canonical OCaml / IML-Oriented DSL

This section defines the **canonical typed representation** of policy formulas.

## 10.1 Basic identifiers

```ocaml
type action_id = int
type artifact_id = string
type reference_id = string
type symbol = string
type path_pattern = string
```

## 10.2 Atomic values

```ocaml
type value =
  | VString of string
  | VInt of int
  | VBool of bool
  | VFloat of float
```

## 10.3 Comparison operators

```ocaml
type cmp_op =
  | Eq
  | Neq
  | Lt
  | Le
  | Gt
  | Ge
  | In
```

## 10.4 Temporal operators

```ocaml
type temporal_unary =
  | G      (* globally *)
  | F      (* finally *)
  | X      (* next *)
  | P      (* previously *)
  | H      (* historically *)
  | PTarget
  | PChain
  | HTarget
  | HChain

type temporal_binary =
  | U      (* until *)
  | S      (* since *)
  | SLast  (* since last *)
```

## 10.5 Variables

```ocaml
type var = string
```

## 10.6 Terms

Terms are used inside predicates and comparisons.

```ocaml
type term =
  | Var of var
  | Val of value
  | Field of term * string
  | Inputs of term
  | Outputs of term
  | Target of term
  | AncestorsOf of term
  | Count of set_expr
  | SetLiteral of term list
```

## 10.7 Set expressions

```ocaml
type set_expr =
  | TermSet of term
  | SetComprehension of
      { binder : var
      ; source : set_expr
      ; guard : policy_formula option
      ; body : term
      }
```

## 10.8 Quantifiers

```ocaml
type quantifier =
  | Forall
  | Exists
  | ExistsUnique
```

## 10.9 Atomic predicates

These are the semantic predicates the DSL can talk about.

```ocaml
type atomic_predicate =
  | ActionTypeIs of term * string
  | ActionCategoryIs of term * string
  | ArtifactTypeIs of term * string
  | ArtifactRoleIs of term * string
  | StatusIs of term * string
  | StartEvent
  | EndEvent
  | HighStakesPath of term
  | HasRationale of term
  | Completed of term
  | FailedAction of term
  | FormalModelArtifact of term
  | ApprovedReferenceArtifact of term
  | ReasoningAction of term
  | VerificationAction of term
  | StateSpaceAnalysisAction of term
  | StateSpaceAnalysisResultPred of term
  | AncestorOf of term * term
  | DerivedFrom of term * term
  | UpstreamOf of term * term
  | PredicateApp of string * term list
```

## 10.10 Policy formulas

```ocaml
type policy_formula =
  | True
  | False
  | Atom of atomic_predicate
  | Not of policy_formula
  | And of policy_formula list
  | Or of policy_formula list
  | Implies of policy_formula * policy_formula
  | Iff of policy_formula * policy_formula
  | Compare of term * cmp_op * term
  | Temporal1 of temporal_unary * policy_formula
  | Temporal2 of temporal_binary * policy_formula * policy_formula
  | Quantified of
      { quantifier : quantifier
      ; binder : var
      ; source : set_expr
      ; body : policy_formula
      }
```

This is the **canonical typed DSL**.  
It is suitable as an OCaml representation and also naturally maps to an IML algebraic datatype.

---

# 11. IML-Oriented View

The same policy language should be representable in IML as algebraic datatypes.

A sketch of the same shape in IML-style notation would be:

```ocaml
type value =
  | VString of string
  | VInt of int
  | VBool of bool
  | VFloat of float

type cmp_op =
  | Eq | Neq | Lt | Le | Gt | Ge | In

type temporal_unary =
  | G | F | X | P | H | PTarget | PChain | HTarget | HChain

type temporal_binary =
  | U | S | SLast

type quantifier =
  | Forall | Exists | ExistsUnique

type term =
  | Var of string
  | Val of value
  | Field of term * string
  | Inputs of term
  | Outputs of term
  | Target of term
  | AncestorsOf of term
  | Count of set_expr
  | SetLiteral of term list

and set_expr =
  | TermSet of term
  | SetComprehension of string * set_expr * formula option * term

and atomic_predicate =
  | ActionTypeIs of term * string
  | ActionCategoryIs of term * string
  | ArtifactTypeIs of term * string
  | ArtifactRoleIs of term * string
  | StatusIs of term * string
  | StartEvent
  | EndEvent
  | HighStakesPath of term
  | HasRationale of term
  | Completed of term
  | FailedAction of term
  | FormalModelArtifact of term
  | ApprovedReferenceArtifact of term
  | ReasoningAction of term
  | VerificationAction of term
  | StateSpaceAnalysisAction of term
  | StateSpaceAnalysisResultPred of term
  | AncestorOf of term * term
  | DerivedFrom of term * term
  | UpstreamOf of term * term
  | PredicateApp of string * term list

and formula =
  | True
  | False
  | Atom of atomic_predicate
  | Not of formula
  | And of formula list
  | Or of formula list
  | Implies of formula * formula
  | Iff of formula * formula
  | Compare of term * cmp_op * term
  | Temporal1 of temporal_unary * formula
  | Temporal2 of temporal_binary * formula * formula
  | Quantified of quantifier * string * set_expr * formula
```

This is not meant to define the full executable evaluator here; it defines the **canonical abstract syntax** of the language.

---

# 12. Concrete Surface Notation

The strict typed DSL above may be rendered into a lighter textual syntax for authoring.

Examples:

## 12.1 Pure temporal policy

```text
G(GitCommit -> P(RunTests /\ completed))
```

Meaning:
- globally, if a `GitCommit` occurs, then previously some `RunTests` action completed

## 12.2 Scoped temporal policy

```text
G(EditFile -> P_target(ReadFile \/ ReadDocumentation \/ SearchCode \/ AnalyzeCode))
```

Meaning:
- every edit must be preceded by relevant research on the same target

## 12.3 Structural policy

```text
G(forall input in inputs(a) -> exists! b in actions_before(a) . input in outputs(b))
```

Meaning:
- every consumed input should have exactly one producer earlier in the trace

## 12.4 Role-based policy

```text
G(VerificationGoal -> target_artifact_id in {x.id | formal_model_artifact(x)})
```

Meaning:
- verification goals must target valid formal-model artifacts

---

# 13. Temporal Semantics

## 13.1 Future-time operators

| Operator | Meaning |
|---|---|
| `G φ` | `φ` holds globally at every trace position |
| `F φ` | `φ` holds at some future position |
| `X φ` | `φ` holds at the next position |
| `φ U ψ` | `φ` holds until `ψ` holds |

## 13.2 Past-time operators

| Operator | Meaning |
|---|---|
| `P φ` | `φ` held at some earlier position |
| `H φ` | `φ` held at every earlier position |
| `φ S ψ` | `φ` has held since `ψ` last held |
| `φ S_last ψ` | `φ` held in the window since the most recent `ψ` |

## 13.3 Scoped operators

These restrict the temporal search space:

- `P_target φ` — previously on the same target
- `P_chain φ` — previously in the artifact dependency chain
- `H_target φ` — historically on the same target
- `H_chain φ` — historically in the dependency chain

---

# 14. First-Order and Structural Semantics

The DSL supports richer policies than pure propositional LTL.

## 14.1 Quantifiers

- `forall x in S`
- `exists x in S`
- `exists! x in S`

## 14.2 Set comprehensions

The DSL may derive sets such as:
- all outputs of reasoning actions
- all modified files
- all approved reference artifacts
- all ancestors of an artifact

## 14.3 Lineage predicates

The DSL may reason over:
- direct derivation
- transitive ancestry
- upstream/downstream relationships
- membership in dependency chains

---

# 15. Reasoner-Agnostic Vocabulary

Policies should be written against **semantic roles**, not implementation-specific tool names.

Preferred predicates include:

- `formal_model_artifact(x)`
- `approved_reference_artifact(x)`
- `reasoning_action(a)`
- `verification_action(a)`
- `state_space_analysis_action(a)`
- `state_space_analysis_result(x)`
- `ancestor_of(x, y)`
- `derived_from(x, y)`
- `upstream_of(x, y)`

Avoid:
- `x.type = IMLModel`
- `tool = imandrax` inside policy formulas unless the governance intent truly depends on a particular engine

## 15.1 Residual-surface vocabulary

Policies may quantify over a trace's **residual surface** — its declared negative space
(Trace Specification §13). The residual surface is the collection:

- `residuals` — the list of declared `residual` objects on the trace

bound by the first-order quantifiers already defined in §10.8 / §14.1 (`∀ r ∈ residuals . …`,
`∃ r ∈ residuals . …`). Within a quantified body, the following **field accessors** are available
on the bound residual `r`:

| Accessor | Meaning |
|---|---|
| `r.kind` | one of `Assumption`, `Unverified`, `OutOfScope`, `Limitation`, `OpenQuestion` |
| `r.severity` | one of `Info`, `Low`, `Medium`, `High`, `Critical` |
| `r.status` | one of `Open`, `Acknowledged`, `Addressed`, `Waived` |
| `r.target` | the `target_ref` the residual points at (may be empty) |
| `r.related_artifact_ids` | the affected/supporting artifacts (may be empty) |
| `r.suggested_check` | how a reviewer could close the gap (may be empty) |

`severity` is **totally ordered**: `Info < Low < Medium < High < Critical`. Comparisons such as
`r.severity ≥ High` are interpreted against this order. `status` and `kind` are unordered enums
compared by equality. `∅` denotes the empty value (a missing `target`/`suggested_check`, or an
empty `related_artifact_ids` list).

> A residual-surface policy expresses a requirement not on what the trace *did*, but on how
> honestly and navigably it declares what it did **not** do.

---

# 16. Binding to the Trace Specification

This section defines how the semantic DSL is grounded in the trace model.

## 16.1 Example mappings

| Policy predicate | Trace grounding |
|---|---|
| `reasoning_action(a)` | action is a `ReasoningAction` |
| `verification_action(a)` | reasoning action subtype is `Verify` |
| `state_space_analysis_action(a)` | reasoning action subtype is `StateSpaceAnalysis` |
| `formal_model_artifact(x)` | artifact constructor is `FormalModelArtifact` |
| `approved_reference_artifact(x)` | artifact role is `ApprovedReferenceRole` or object is a reference artifact |
| `ancestor_of(x, y)` | reachability through `derived_from` links |
| `inputs(a)` | `action_common.inputs` |
| `outputs(a)` | `action_common.outputs` |
| `target(a)` | target carried in action-specific payload if present |
| `policy_failed(p)` | policy evaluation status is `Failed` |
| `residuals` | `trace.residuals` (the residual surface, Trace Spec §13) |
| `r.severity`, `r.status`, `r.kind` | the corresponding fields of a `residual` |
| `r.severity ≥ High` | severity rank, where `Info < Low < Medium < High < Critical` |

## 16.2 Binding rule

The policy DSL is interpreted over the **canonical trace semantics**, not directly over raw JSON.

JSON/Pydantic must first be decoded into the canonical trace model before policy evaluation.

---

# 17. Standard Example Policies

## 17.1 Pure temporal policies

### Tests before commit
```text
G(GitCommit -> P(RunTests /\ completed))
```

### Every action has rationale
```text
G(action -> rationale != empty)
```

### Trace has lifecycle
```text
start_event /\ F(end_event)
```

## 17.2 Scoped temporal policies

### Research before edit
```text
G(EditFile -> P_target(ReadFile \/ ReadDocumentation \/ SearchCode \/ AnalyzeCode))
```

### Reasoning for high-stakes edits
```text
G(EditFile /\ high_stakes_path(a) ->
  P_chain(VerificationResult \/ StateSpaceAnalysisResult \/ ConformanceResult))
```

## 17.3 Structural policies

### Data flow integrity
```text
G(forall input in inputs(a) ->
  exists! b in actions_before(a) . input in outputs(b))
```

### Goals reference valid models
```text
G(VerificationGoal ->
  target_artifact_id in {x.id | formal_model_artifact(x)})
```

### Generated tests require state-space analysis
```text
G(GeneratedTests ->
  exists x . ancestor_of(x, GeneratedTests) /\ state_space_analysis_result(x))
```

## 17.4 Residual-surface policies

These quantify over `residuals` (§15.1) to govern a trace's declared negative space. They make
the realistic bar — *gaps declared, located, and triaged* — enforceable, rather than requiring
traces to be gap-free.

### No open critical residuals
```text
¬∃ r ∈ residuals . r.severity = Critical /\ r.status = Open
```
Intended as an approval gate: no critical declared gap may remain open at sign-off.

### High-severity residuals acknowledged before commit
```text
G(GitCommit -> ∀ r ∈ residuals . r.severity ≥ High -> r.status ≠ Open)
```
A commit must not silently carry an unacknowledged high- or critical-severity gap.

### Unverified residuals have a suggested check
```text
∀ r ∈ residuals . r.kind = Unverified -> r.suggested_check ≠ ∅
```
Every unverified claim must say how a reviewer could close it — turning the negative space into a
work-list.

### Assumptions are located
```text
∀ r ∈ residuals . r.kind = Assumption -> (r.target ≠ ∅ \/ r.related_artifact_ids ≠ ∅)
```
Every relied-upon assumption must point at what it touches, so a reviewer can find it.

These four ship in the policy gallery. Beyond them, the residual-quantifier forms of §15.1 are
evaluated **generally** by the reference compiler — any `∀` / `∃` / `∃!` policy over `residuals`
with field comparisons (`=`, `≠`, `≥`, …, and `≠ ∅`) is enforceable, not only this standard set,
and may be freely composed under temporal operators (e.g. `G(GitCommit → ∀ r ∈ residuals . …)`).

---

# 18. Interchange Model Notes

The canonical policy model is authoritative.

For interchange, policies may be projected into JSON/Pydantic as:

- metadata fields represented directly
- `formula` represented either as:
  - a textual DSL string, or
  - a structured JSON AST

## 18.1 Recommended rule

Use a **structured canonical AST internally**, and allow a **textual representation externally**.

That means:
- OCaml / IML / formal tooling uses `policy_formula`
- APIs / files may use a textual DSL form
- parsers and printers connect the two

## 18.2 Pydantic strategy

Recommended Python generation:
- `Policy` and `PolicyEvaluation` as normal `BaseModel`s
- formula represented as:
  - either `str`
  - or a discriminated AST union if structured interchange is desired

---

# 19. Recommended Implementation Strategy

## 19.1 Internal semantic layer

Use the canonical typed policy model in:
- OCaml
- IML
- policy analysis tooling
- runtime policy checking infrastructure

## 19.2 Parsing layer

Implement:
- parser: textual DSL → `policy_formula`
- pretty-printer: `policy_formula` → textual DSL

## 19.3 Binding layer

Implement policy evaluation against:
- canonical traces
- optional review-case contexts where enabled

## 19.4 Serialization layer

Generate:
- JSON schema
- Pydantic models
- encoders/decoders

from the strict model, not the reverse.

---

# 20. Intended Outcomes

The intended outcomes of this policy specification are:

- **clean separation from the trace spec**
- **strong formal semantics for policy formulas**
- **reasoner-agnostic governance logic**
- **stable semantic predicates over traces**
- **OCaml / IML-friendly policy representation**
- **clear path to parsing, evaluation, and serialization**

---

# 21. Summary

The clean conceptual distinction is:

- a **trace** is a typed execution structure with formal semantics
- a **policy** is a formula interpreted over that structure
- **policy satisfaction** determines whether a trace obeys the declared governance constraints

Or, in one sentence:

> **Traces define the execution world; policies define the rules evaluated over that world.**

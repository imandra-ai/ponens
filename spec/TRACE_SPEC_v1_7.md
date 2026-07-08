# Ponens Trace Specification

## Version

**Version:** 1.7  
**Status:** Draft  
**Format:** Canonical typed specification with JSON/Pydantic projection notes  
**Positioning:** Reasoner-agnostic trace specification, with IML / ImandraX as one concrete instantiation

> **Changes in 1.7 (additive, backward-compatible).** Adds **Goals & Acceptance** (§18) — an optional, typed record of a trace's *intent and definition of done*. A **goal** states what is being changed and why, and decomposes it into **acceptance items** (change / property / obligation / gap): the *end node*, what "done" means. Acceptance introduces no new evaluator — each item **resolves** against machinery already in the trace (a verification result, a policy evaluation, a residual, a diff), so progress is grounded in evidence rather than self-reported. Where §8.4 meta-actions capture the *structure* of the work (how atomic actions group into intent), a goal captures its *target* (the conditions the work must meet), and may reference a meta-action via `meta_action_id`. The resolved state — per-item status, progress, the goal's relevance cone, and its open gaps — is a **derived** projection, not an authored field. Existing 1.6 traces remain valid; `goals` canonicalizes to the empty list.

> **Changes in 1.6 (additive, backward-compatible).** Adds **Meta-actions** (§8.4) — an optional, typed *overlay* that groups the atomic `actions` into units of **intent** (a goal → steps → tool-calls hierarchy), so a trace can be read, reviewed, and graded at the level of *what was being attempted* rather than only *what tool ran*. The atomic actions remain the ground-truth record; meta-actions are a producer's claim about their structure, carrying their own intent, outcome, residuals, and produced artifacts. Existing 1.5 traces remain valid; `meta_actions` canonicalizes to the empty list and `meta_action_id` is optional.

> **Changes in 1.5 (additive, backward-compatible).** Adds the **Residual Surface** (§13) — a first-class, typed record of a trace's *negative space*: the assumptions it relied on, the claims it left unverified, what it deliberately left out of scope, its known limitations, and the questions it defers to review. This exists to support review, and in particular **agent-to-agent handoff**, where the consuming agent needs to know where to point rather than re-deriving the whole trace. Existing 1.4 traces remain valid; `residuals` canonicalizes to the empty list.

---

# 1. Purpose

A **trace** is the complete formal record of an AI agent's work session.

It captures not only **what** the agent did, but also:

- which **artifacts** existed at each step
- how those artifacts were **transformed**
- what **reasoning** justified each consequential action
- which **policies** were checked over the execution
- how every output can be traced back through its full dependency chain
- how key reasoning outcomes can be independently reviewed and, where supported, reproduced

The trace format is designed to support:

- **artifact lineage**
- **formal reasoning provenance**
- **policy-checkable execution**
- **audit and replay**
- **system-level reasoning over agent workflows**
- **reasoner-agnostic integration**, with concrete engines represented via metadata

This specification treats a trace as more than an activity log. A trace is a typed execution record that can be analyzed, validated, and, in future, formally verified.

---

# 2. Canonical Model vs Interchange Model

This specification distinguishes between two layers:

## 2.1 Canonical model

The **canonical model** is the semantic source of truth.

It is:
- strongly typed
- algebraic where appropriate
- designed for formal reasoning
- the model against which invariants and semantics are defined

The canonical model should use:
- algebraic variants for closed enums and tagged unions
- typed records for structured objects
- typed constructors for actions and artifacts
- explicit payload types for structured reasoning objects

## 2.2 Interchange model

The **interchange model** is a JSON-friendly representation derived from the canonical model.

It exists to support:
- file persistence
- API transport
- UI integration
- Pydantic model generation
- cross-language interoperability

## 2.3 Design rule

> **Specify the strongest semantic model first; derive the wire format from it, not the other way around.**

The canonical model is authoritative.  
JSON and Pydantic schemas are projections of that model.

---

# 3. Design Principles

The trace model is built around eight core principles:

1. **Typed artifacts**  
   All meaningful objects in the trace are represented explicitly as typed artifacts.

2. **Producer-consumer lineage**  
   Actions consume input artifacts and produce output artifacts, forming a directed acyclic graph (DAG).

3. **Explicit reasoning steps**  
   Formalization, reasoning goals, reasoning results, state-space analyses, conformance checks, simulations, and generated tests are first-class trace objects.

4. **Policy evaluation**  
   Engineering, safety, and governance requirements are represented explicitly and evaluated over the trace.

5. **Execution semantics**  
   The trace records a sequence of state-changing actions, not just a flat activity history.

6. **Collaborative and iterative review**  
   Traces may accumulate structured human commentary and may be linked into explicit chains of reruns, fixes, and re-evaluations over time.

7. **Reasoner-agnostic semantics**  
   Core action and artifact types describe the semantic reasoning operation. Specific engines, model languages, and methods are recorded through metadata.

8. **Strict internal semantics**  
   The specification prefers typed semantic constructors over loosely typed payload objects, even when the interchange format remains JSON-shaped.

---

# 4. Semantic Layer vs Implementation Layer

This specification is intentionally **reasoner-agnostic**.

## 4.1 Semantic layer

The core schema uses semantic action and artifact types such as:

- `Formalize`
- `DefineVerificationGoal`
- `Verify`
- `StateSpaceAnalysis`
- `ConformanceCheck`
- `CoSimulate`
- `GenerateTests`

and artifacts such as:

- `Formalization`
- `FormalModel`
- `VerificationGoal`
- `VerificationResult`
- `StateSpaceAnalysisResult`
- `ConformanceResult`
- `CoSimulationResult`
- `GeneratedTests`

These identify **what kind of reasoning operation occurred**.

## 4.2 Implementation layer

Concrete engines and methods identify **how that operation was realized**.

Examples:
- `tool = "imandrax"`
- `format = "iml"`
- `model_language = "iml"`
- `method = "region_decomposition"`

## 4.3 Example

A trace may record:

- semantic action: `StateSpaceAnalysis`
- concrete implementation: `tool = "imandrax"`, `method = "region_decomposition"`

This means the trace remains portable while preserving the specific capabilities of a concrete reasoner.

---

# 5. Canonical Top-Level Structure

The canonical trace is a typed record.

```ocaml
type trace =
  { trace_id : string
  ; spec_version : string
  ; assistant : string
  ; model : string
  ; timestamp : string
  ; trigger : event
  ; actions : action list
  ; meta_actions : meta_action list
  ; outcome : event
  ; artifacts : artifact list
  ; reference_artifacts : reference_artifact list
  ; policies : policy list
  ; policy_evaluations : policy_evaluation list
  ; execution_environments : execution_environment list
  ; reproducibility : trace_reproducibility option
  ; comments : comment list
  ; review_items : review_item list
  ; residuals : residual list
  ; goals : goal list
  ; trace_links : trace_link list
  ; trace_lineage : trace_lineage option
  ; files_modified : string list
  ; metrics : metrics option
  }
```

`residuals` is the trace's **residual surface** — its declared negative space (§13).

`goals` is the trace's **goals & acceptance** — its declared intent and definition of done (§18). It canonicalizes to the empty list.

## 5.1 Metrics

```ocaml
type metrics =
  { total_actions : int option
  ; decision_points : int option
  ; parallel_blocks : int option
  ; loops : int option
  ; max_loop_iterations : int option
  }
```

Lists are canonicalized as empty lists rather than omitted values.

---

# 6. Events

Events mark the start and end of the process.

## 6.1 Canonical model

```ocaml
type event_type =
  | TaskReceived
  | TriggeredByEvent
  | ProcessCompleted
  | ProcessAborted
  | ProcessInterrupted

type event =
  { typ : event_type
  ; description : string option
  ; summary : string option
  ; from_user : string option
  ; reason : string option
  }
```

## 6.2 Event semantics

Events are not generic log lines. They delimit the lifecycle of a trace:
- the `trigger` event identifies how the process began
- the `outcome` event identifies how the process ended

---

# 7. Artifacts

Artifacts are the core typed objects of the trace.

Actions do not exchange free-form names. They exchange **artifact identities**.

## 7.1 Canonical artifact model

The canonical artifact model is **strictly typed**.

### Common artifact fields

```ocaml
type artifact_common =
  { artifact_id : string
  ; artifact_role : artifact_role option
  ; name : string option
  ; format : string option
  ; revision : int option
  ; producer_action_id : int option
  ; derived_from : string list
  ; supersedes : string option
  ; content_ref : string option
  ; summary : string option
  ; metadata : artifact_metadata option
  }
```

### Artifact roles

Artifact roles are semantic tags used by policy evaluation and reasoning.

```ocaml
type artifact_role =
  | FormalModelRole
  | ApprovedReferenceRole
  | ReasoningGoalRole
  | ReasoningResultRole
  | ProofRole
  | CounterexampleRole
  | StateSpaceAnalysisRole
  | GeneratedTestRole
  | AuditEvidenceRole
  | CustomArtifactRole of string
```

### Strict artifact type

```ocaml
type artifact =
  | UserInstructionArtifact of artifact_common
  | SourceCodeArtifact of artifact_common
  | DocumentationArtifact of artifact_common
  | SearchResultsArtifact of artifact_common
  | AnalysisNoteArtifact of artifact_common
  | PlanArtifact of artifact_common
  | FormalizationArtifact of artifact_common * formalization_payload
  | FormalModelArtifact of artifact_common * formal_model_payload
  | VerificationGoalArtifact of artifact_common * verification_goal_payload
  | VerificationResultArtifact of artifact_common * verification_result_payload
  | StateSpaceAnalysisResultArtifact of artifact_common * state_space_analysis_result_payload
  | ConformanceResultArtifact of artifact_common * conformance_result_payload
  | CoSimulationResultArtifact of artifact_common * cosimulation_result_payload
  | GeneratedTestsArtifact of artifact_common * generated_tests_payload
  | CommandResultArtifact of artifact_common * command_result_payload
  | DiffArtifact of artifact_common
  | UserApprovalArtifact of artifact_common
  | CommitArtifact of artifact_common
  | ReproductionBundleArtifact of artifact_common * reproduction_bundle_payload
```

## 7.2 Why strict artifacts

This form is preferred because it ensures:
- payload presence is aligned with artifact kind
- impossible combinations are unrepresentable
- internal reasoning and IML modeling remain precise

## 7.3 Artifact revisioning

Artifacts are immutable once produced.

To represent evolution:
- `revision` identifies the version number
- `derived_from` identifies immediate inputs
- `supersedes` identifies a replaced predecessor

---

# 8. Actions

Actions are the ordered steps taken by the agent.

## 8.1 Canonical action model

The canonical action model is also **strictly typed**.

### Common action fields

```ocaml
type action_common =
  { id : int
  ; label : string
  ; rationale : string
  ; detail : string option
  ; inputs : string list
  ; outputs : string list
  ; evidence : evidence list
  ; observations : observation list
  ; execution : execution_metadata option
  ; reproducibility : action_reproducibility option
  ; meta_action_id : string option   (* enclosing meta-action, §8.4 *)
  }
```

### Activity actions

```ocaml
type activity_action_type =
  | ReadFile
  | SearchCode
  | SearchWeb
  | AnalyzeCode
  | ExploreDirectory
  | ReadDocumentation
  | EditFile
  | CreateFile
  | DeleteFile
  | RenameFile
  | RunCommand
  | RunTests
  | TypeCheck
  | Lint
  | ManualVerification
  | GitStatus
  | GitDiff
  | GitCommit
  | AskUser
  | ReportProgress
  | Explain
  | FormulatePlan
  | DecomposeTask
  | EstimateImpact
```

### Gateway actions

```ocaml
type gateway_action_type =
  | ExclusiveDecision
  | ParallelSplit
  | EventBasedDecision
  | LoopGateway

type decision_option =
  { label : string
  ; chosen : bool
  ; rejected_because : string option
  ; next_action_id : int option
  }

type gateway_payload =
  { decision_basis : string option
  ; supporting_inputs : string list
  ; options : decision_option list
  }
```

### Reasoning actions

```ocaml
type reasoning_action_type =
  | Formalize
  | DefineVerificationGoal
  | Verify
  | StateSpaceAnalysis
  | ConformanceCheck
  | CoSimulate
  | GenerateTests
```

### Governance actions

```ocaml
type governance_action_type =
  | EvaluatePolicy
  | CreateReviewItem
  | AcknowledgeReviewItem
  | ResolveReviewItem
  | AddComment
  | RequestApproval
  | Approve
  | Reject
  | CreateSnapshot
  | RecordAudit
  | LinkTrace
```

### Strict action type

```ocaml
type action =
  | ActivityAction of action_common * activity_action_type * action_payload option
  | GatewayAction of action_common * gateway_action_type * gateway_payload
  | ReasoningAction of action_common * reasoning_action_type * action_payload option
  | GovernanceAction of action_common * governance_action_type * action_payload option
```

## 8.2 Open request/result fields

Some actions carry implementation-specific request/result structures.

To preserve a strict semantic model, these should remain abstract at the canonical layer:

```ocaml
type action_payload
```

Implementations may refine `action_payload` further, or keep it open if needed.

## 8.3 Execution metadata

```ocaml
type determinism =
  | Deterministic
  | Mixed
  | Nondeterministic

type execution_metadata =
  { tool : string option
  ; version : string option
  ; method_ : string option
  ; determinism : determinism option
  ; duration_ms : int option
  ; cost : float option
  }
```

A reasoning action without at least `tool` should be considered underspecified.

## 8.4 Meta-actions

The `actions` list is the trace's **atomic, ground-truth record** — one entry per tool call. But work has *structure*: a session pursues a goal, broken into steps, each carried out by several tool calls. A **meta-action** captures that structure — a unit of *intent* that groups the atomic actions which carried it out — so a trace can be read, reviewed, and graded at the level of *what was being attempted* rather than only *what tool ran*.

A meta-action is an **interpretive overlay, not a replacement**. The atomic `actions` remain the evidence — the unit that `reproduce`, lineage, and `data_flow_integrity` operate over; meta-actions are a producer's *claim about how those actions group into intent*. This mirrors the positive/negative-space split of §13: the atomic layer is *what happened*; the meta layer is the *structure asserted over it*.

### Canonical model

```ocaml
type meta_action_status =
  | MetaCompleted      (* the intent was achieved *)
  | MetaPartial        (* attempted, not fully achieved *)
  | MetaAbandoned      (* started, then dropped or superseded *)

type meta_action_source =
  | PlanDeclared       (* from the agent's own plan / todo list — highest fidelity *)
  | TurnSegmented      (* inferred from directive (turn) boundaries *)
  | IntentInferred     (* inferred from a contiguous run of shared intent / rationale *)

type meta_action =
  { id : string
  ; title : string                       (* the unit of intent, in plain language *)
  ; intent : string option               (* why — the goal of this step *)
  ; action_ids : int list                (* member atomic actions, in order *)
  ; outcome : string option              (* what resulted *)
  ; status : meta_action_status option
  ; source : meta_action_source option   (* how the grouping was determined *)
  ; parent_id : string option            (* enclosing meta-action, for multi-level zoom *)
  ; produced_artifact_ids : string list  (* artifacts this step produced *)
  ; residual_ids : string list           (* gaps declared at this level (§13) *)
  ; tags : string list
  }
```

The trace record (§5) carries `meta_actions : meta_action list`, canonicalized as the empty list. Each atomic action carries a back-reference `meta_action_id : string option` (§8.1) to its enclosing meta-action, so navigation works in both directions.

### Semantics

- **Overlay, ordered, non-overlapping.** A meta-action references its members by id; the `actions` list is unchanged. An atomic action belongs to **at most one** meta-action, and a meta-action's `action_ids` are a contiguous, ordered slice of the timeline. Coverage need not be **total** — incidental actions may remain ungrouped.
- **Hierarchy via `parent_id`.** Meta-actions may nest (a *goal* contains *steps* contains atomic actions), giving the consumer discrete **zoom levels**. One level (steps over actions) is the common case; `parent_id` enables more without changing the model.
- **Intent + outcome make it reviewable as a unit.** `title`/`intent` state what was being attempted; `outcome`/`status` state whether it was achieved — so a reviewer can triage a handful of meta-actions ("did each do what it claims?") before drilling into the atomic actions of the suspect ones.
- **Gaps and artifacts attach at the level they belong.** `residual_ids` lets an assumption or unverified claim be located at the *step* (not only at an atomic action via `introduced_by_action_id`, §13.1); `produced_artifact_ids` makes the meta-action a coarse node in the lineage DAG (§7).

### Source and fidelity

`source` records **how** the grouping was determined, because not all groupings are equally trustworthy — it is a *fidelity ladder*:

1. `PlanDeclared` — the boundaries come from the agent's **own declared plan** (a `FormulatePlan` / `DecomposeTask` action, §8.1, or an external todo list). Most authentic: the agent's stated intent, with its own start/finish markers.
2. `TurnSegmented` — inferred from **directive boundaries** (a new instruction begins a new unit).
3. `IntentInferred` — inferred from a **contiguous run of shared rationale/intent**, the weakest signal.

A producer should use the highest-fidelity signal available and record which via `source`, so a consumer knows whether the structure is *declared* (the agent said so) or *inferred* (tooling guessed). As with the residual surface, a *declared* grouping carries more weight across a trust boundary than an inferred one.

### Relationship to existing constructs

- `FormulatePlan` / `DecomposeTask` activity actions (§8.1) record the *act* of planning; a meta-action records the resulting *plan unit* spanning the actions that executed it. The planning action is typically the producer of a `PlanDeclared` meta-action.
- Gateway actions (§8.1) — decisions, splits, loops — sit **inside** the meta-action whose intent they served, at the point they occurred.
- `metrics` (§5.1) may summarize a `meta_action_count`; `decision_points` is unchanged — it counts gateways, which meta-actions *contain*, not replace.

### Interchange projection

```json
"meta_actions": [
  {
    "id": "m2",
    "title": "Make the embedded-trace viewer robust to any content",
    "intent": "Traces of HTML/JS broke the script parse; embed so no content can corrupt it",
    "action_ids": [180, 181, 182, 183],
    "outcome": "application/json block + unicode-escaped '<'; renders 389 actions cleanly",
    "status": "completed",
    "source": "plan_declared",
    "produced_artifact_ids": [],
    "residual_ids": ["r3"],
    "tags": ["viewer"]
  }
]
```

An action that belongs to it back-references it:

```json
{ "id": 181, "label": "Switch the embed to an application/json block", "meta_action_id": "m2" }
```

---

# 9. Evidence and Observations

## 9.1 Evidence

```ocaml
type evidence_type =
  | FileRef
  | UrlRef
  | CommandOutput
  | SearchResult

type evidence =
  { typ : evidence_type
  ; ref_ : string
  ; exit_code : int option
  }
```

## 9.2 Observation

```ocaml
type confidence =
  | High
  | Medium
  | Low

type observation =
  { observation_id : string option
  ; derived_from : string list
  ; statement : string
  ; confidence : confidence option
  }
```

---

# 10. Artifact Payload Types

The following structured payloads are canonical.

## 10.1 Formalization

```ocaml
type formalization_status =
  | Transparent
  | Opaque
  | Failed

type formalization_payload =
  { status : formalization_status
  ; src_lang : string
  ; src_code : string
  ; formal_code : string
  ; model_language : string option
  ; symbols : string list
  }
```

## 10.2 Formal model

```ocaml
type formal_model_payload =
  { model_language : string
  ; formal_code : string
  ; symbols : string list
  ; scope : string option
  }
```

## 10.3 Verification goals

```ocaml
type verification_goal_kind =
  | VerifyGoal
  | Instance
  | Theorem
  | Lemma
  | Axiom

type property_status =
  | Pending
  | Proved
  | Refuted
  | UnknownProperty

type property_item =
  { name : string
  ; status : property_status
  ; src : string
  ; note : string option
  }

type verification_goal_payload =
  { goal_id : int
  ; goal_revision : int option
  ; kind : verification_goal_kind
  ; description : string
  ; src : string
  ; target_artifact_id : string
  ; target_symbol : string option
  ; properties : property_item list
  }
```

## 10.4 Verification results

```ocaml
type verification_result_status =
  | VrProved
  | VrRefuted
  | VrSat
  | VrUnknown

type sat_model_type =
  | InstanceModel
  | CounterexampleModel

type sat_model =
  { m_type : sat_model_type
  ; src : string
  }

type verification_result_variant =
  | ProvedResult of
      { proof_pp : string
      ; properties : property_item list
      }
  | RefutedResult of
      { counterexample : string
      }
  | SatResult of
      { model : sat_model
      }
  | UnknownResult of
      { note : string option
      }

type verification_result_payload =
  { goal_id : int
  ; goal_artifact_id : string
  ; status : verification_result_status
  ; engine : string option
  ; completed_at : string option
  ; result : verification_result_variant
  }
```

## 10.5 State-space analysis

```ocaml
type witness_model

type region =
  { constraints : string list
  ; invariant : string option
  ; model : witness_model option
  ; model_eval : string option
  }

type state_space_analysis_result_payload =
  { target_artifact_id : string
  ; target_symbol : string option
  ; analysis_kind : string
  ; analysis_revision : int option
  ; description : string option
  ; complete : bool option
  ; regions : region list
  ; coverage_summary : string option
  ; notes : string option
  }
```

`StateSpaceAnalysisResult` is generic.  
ImandraX region decomposition is one valid instantiation via:
- `analysis_kind = "region_decomposition"`
- `execution.tool = "imandrax"`
- `execution.method = "region_decomposition"`

## 10.6 Conformance

```ocaml
type conformance_status =
  | ConformancePassed
  | ConformanceFailed
  | ConformancePartial
  | ConformanceUnknown

type conformance_result_payload =
  { reference_artifact_id : string
  ; target_artifact_id : string
  ; status : conformance_status
  ; engine : string option
  ; findings : string list
  ; note : string option
  }
```

## 10.7 Co-simulation

```ocaml
type divergence_point

type cosimulation_status =
  | Matched
  | Mismatched
  | Partial
  | ErrorStatus

type cosimulation_result_payload =
  { target_artifact_id : string
  ; input_artifact_ids : string list
  ; status : cosimulation_status
  ; engine : string option
  ; replayed_steps : int option
  ; divergence_points : divergence_point list
  ; summary : string option
  ; observations : string list
  }
```

## 10.8 Generated tests

```ocaml
type generated_test =
  { name : string
  ; region_index : int option
  ; constraints : string list
  ; inputs : witness_model option
  ; expected : witness_model option
  ; code : string
  }

type generated_tests_payload =
  { function_ : string
  ; language : string
  ; source_analysis_artifact_id : string
  ; tests : generated_test list
  }
```

## 10.9 Command results

```ocaml
type command_result_payload
```

This may be refined by implementations.

## 10.10 Reproduction bundle

```ocaml
type reproduction_bundle_payload =
  { entry_action_ids : int list
  ; artifact_ids : string list
  ; environment_ids : string list
  ; notes : string option
  }
```

---

# 11. Reference Artifacts

Reference artifacts are approved models, specifications, interfaces, contracts, or domain references used as governance ground truth.

## 11.1 Canonical model

```ocaml
type reference_artifact_type =
  | RefFormalModel
  | RefDocumentation
  | RefContractModel
  | RefProtocolSpec
  | RefOther of string

type reference_vg_kind =
  | Conformance
  | Invariant
  | Refinement

type reference_vg =
  { vg_id : string
  ; description : string
  ; kind : reference_vg_kind
  ; src : string
  }

type reference_payload

type reference_artifact =
  { reference_artifact_id : string
  ; name : string
  ; description : string option
  ; domain : string
  ; version : string option
  ; source : string option
  ; artifact_type : reference_artifact_type
  ; format : string option
  ; content_ref : string option
  ; payload : reference_payload option
  ; verification_goals : reference_vg list
  }
```

---

# 12. Reproducibility

## 12.1 Trace-level reproducibility

```ocaml
type reproducibility_status =
  | NotReproducible
  | PartiallyReproducible
  | Reproducible

type trace_reproducibility =
  { status : reproducibility_status
  ; entrypoints : string list
  ; required_artifact_ids : string list
  ; required_environment_ids : string list
  ; limitations : string list
  ; notes : string option
  }
```

## 12.2 Action-level reproducibility

```ocaml
type reproduction_kind =
  | DeterministicReplay
  | ToolReexecution
  | ProceduralReplay
  | ManualReproduction
  | NotReproducibleKind

type reproduction_procedure_kind =
  | CommandProcedure
  | WorkflowProcedure
  | ReferenceProcedure
  | ManualProcedure

type reproduction_procedure =
  { kind : reproduction_procedure_kind
  ; command : string option
  ; working_directory : string option
  ; arguments : string list
  ; steps : string list
  ; reference : string option
  }

type expected_output =
  { artifact_ids : string list
  ; result_summary : string option
  }

type action_reproducibility =
  { status : reproducibility_status
  ; reproduction_kind : reproduction_kind
  ; input_artifact_ids : string list
  ; environment_id : string option
  ; procedure : reproduction_procedure
  ; expected_output : expected_output option
  ; limitations : string list
  ; notes : string option
  }
```

## 12.3 Execution environments

```ocaml
type execution_environment_kind =
  | Toolchain
  | Container
  | Service
  | ExternalSystem

type environment_component =
  { name : string
  ; version : string option
  }

type environment_configuration

type execution_environment =
  { environment_id : string
  ; kind : execution_environment_kind
  ; name : string
  ; components : environment_component list
  ; configuration : environment_configuration option
  ; notes : string option
  }
```

Consequential reasoning outcomes should either be reproducible directly or linked to a reproducible downstream validation step.

---

# 13. Residual Surface

A trace records what the agent **established** — its actions, artifacts, proofs, and checks. This is the *positive space*. For review, and especially for **agent-to-agent handoff**, the consumer also needs the *negative space*: what the producing agent did **not** establish.

The **residual surface** is the explicit, uniform, queryable record of that negative space — the assumptions relied upon, the claims left unverified, the parts left out of scope, the known limitations, and the questions deferred to review.

> A positive claim can be checked against the artifacts that back it. The residual surface is what *cannot* be taken for granted — it tells a reviewer (human or agent) **where to point**, instead of forcing them to re-derive the whole trace to discover what is missing.

Declaring the residual surface honestly is what makes a trace trustworthy across a trust boundary: a reviewing agent need not assume the trace is complete, because the trace states its own gaps.

> The protocol by which a reviewing agent *consumes* the residual surface — triage by severity, follow `target`, run `suggested_check`, and hunt undeclared gaps — is defined in the companion **Trace Review Handoff Specification** (`REVIEW_HANDOFF_v0_1.md`).

## 13.1 Canonical model

```ocaml
type residual_kind =
  | Assumption       (* a premise relied upon but not established within the trace *)
  | Unverified       (* an action taken or output produced, but not checked or proved *)
  | OutOfScope       (* deliberately not addressed in this trace *)
  | Limitation       (* a known constraint under which the established results hold *)
  | OpenQuestion     (* a decision deferred to a reviewer or human *)

type residual_severity =
  | InfoResidual
  | LowResidual
  | MediumResidual
  | HighResidual
  | CriticalResidual

type residual_source =
  | AgentDeclared    (* self-reported by the producing agent *)
  | PolicyDerived    (* surfaced by a policy evaluation over the trace *)
  | ToolInferred     (* inferred by analysis tooling *)
  | ReviewerAdded    (* added during review *)

type residual_status =
  | ResidualOpen          (* outstanding *)
  | ResidualAcknowledged  (* seen and accepted as a known gap by a reviewer *)
  | ResidualAddressed     (* closed, typically by a successor trace *)
  | ResidualWaived        (* accepted as permanent / not to be addressed *)

type residual =
  { residual_id : string
  ; kind : residual_kind
  ; statement : string                    (* the gap, in plain language *)
  ; severity : residual_severity option   (* impact if wrong or left unaddressed *)
  ; target : target_ref option            (* where it bites (see §14.1) *)
  ; related_artifact_ids : string list    (* affected or supporting artifacts *)
  ; rationale : string option             (* why assumed / not verified / out of scope *)
  ; suggested_check : string option       (* how a reviewer could close it *)
  ; source : residual_source option
  ; status : residual_status option
  ; introduced_by_action_id : int option  (* the action that gave rise to it, if any *)
  ; tags : string list
  }
```

The trace record (§5) carries `residuals : residual list`, canonicalized as an empty list when there is no declared negative space.

## 13.2 Semantics

**Kinds** partition the negative space by *why* something is unestablished:

- `Assumption` — the work is correct *only if* this premise holds, and the premise was not checked (e.g. "the upstream API returns results already sorted").
- `Unverified` — something was done but not validated (e.g. a transition that was implemented but has no verification goal).
- `OutOfScope` — a deliberate exclusion (e.g. "idempotency under retries was not addressed").
- `Limitation` — a boundary on the established results (e.g. "invariants hold under single-threaded application only").
- `OpenQuestion` — a genuine decision punted to review (e.g. "should a refund reset the approval count?").

**Severity is impact, not probability.** `severity` records how much it matters *if* the residual is wrong or left unaddressed, independent of how likely that is, so a reviewer can triage by consequence.

**`target` routes attention.** Reusing `target_ref` (§14.1), a residual points at the action, artifact, policy, or trace region where it bites. A reviewing agent navigates by following targets, not by re-reading everything.

**`suggested_check` makes it actionable.** Where possible a residual states how it could be closed — the verification goal to add, the test to write, the question to answer — turning the negative space from a warning into a work-list.

**Source and trust.** `source` records who surfaced the residual: `AgentDeclared` is the producing agent's honest self-report, `PolicyDerived` is surfaced mechanically (§13.5), `ReviewerAdded` accrues during review. A trace with *no* declared residuals is not assumed complete — the absence of residuals is itself reviewable.

## 13.3 Lifecycle and relationship to review items

A **residual** is the *producer-side declaration* of a gap; a **review item** (§14.3) is the *reviewer-side action* taken about it. The two are linked but distinct:

- a residual may be **promoted** to a review item when a reviewer decides it must be tracked or that it blocks approval;
- a residual is typically **addressed** not by mutating the trace (traces are immutable) but by a **successor trace** linked via `Supersedes` (§15.1), in which the gap no longer appears or is marked `ResidualAddressed`;
- `ResidualWaived` records an explicit, auditable decision to accept a gap permanently.

The residual surface therefore *shrinks across a chain* as successor traces close gaps — mirroring the trace-immutability / append-only-chain model.

## 13.4 Relationship to existing constructs

The residual surface **consolidates and elevates** negative-space signals that otherwise remain implicit and scattered:

- `reproducibility.limitations` (§12) are *replay-specific*; a `Limitation` residual is broader (constraints on the result itself). One may surface the other, but they need not coincide.
- `observation.confidence = Low` (§9.2) marks a *positive* statement held with low confidence; such an observation **may be promoted** to an `Assumption` or `Unverified` residual when a reviewer needs to act on it.
- `property_status = Pending` (§10.3), `coverage_summary`, and `complete = false` (§10.5) are *verification-internal*. The residual surface should **summarize** the resulting coverage gap at the trace level — typically an `Unverified` residual whose `target` is the uncovered symbol and whose `related_artifact_ids` reference the relevant goal or analysis — so a reviewer need not walk every goal to discover what was left unproved.
- `policy_evaluations` express *requirements checked*; a `failed` or `not_applicable` evaluation **may derive** a `PolicyDerived` residual (§13.5).

The rule of thumb: anything a reviewer would otherwise have to *infer* about what is missing should be stated explicitly in the residual surface.

## 13.5 Policy hooks

Because the residual surface is typed and queryable, policies (see the Policy Specification) can govern it directly. Illustrative policies for the review handoff:

- **no unaddressed critical gaps at approval** — `G(Approve → ¬∃ r ∈ residuals . r.severity = Critical ∧ r.status = ResidualOpen)`
- **commits acknowledge their residual surface** — `G(GitCommit → ∀ r ∈ residuals . r.severity ≥ High → r.status ≠ ResidualOpen)`
- **high-stakes gaps must say how they close** — every `Unverified` residual whose `target` lies on a `high_stakes_path` must carry a non-empty `suggested_check`
- **assumptions must be locatable** — every `Assumption` residual must carry a `target` or non-empty `related_artifact_ids`

These let an organization require not that traces be *gap-free*, but that their gaps be *declared, located, and triaged* — a far more realistic and reviewable bar.

## 13.6 Interchange projection

A payments trace declaring its negative space:

```json
"residuals": [
  {
    "residual_id": "r1",
    "kind": "limitation",
    "statement": "Amount invariants are proved for single-threaded application of transitions only; under concurrent capture/refund the invariant is not established.",
    "severity": "high",
    "target": { "target_type": "artifact", "target_id": "a8" },
    "related_artifact_ids": ["a10"],
    "rationale": "The formal model applies one transition at a time; interleavings are not modeled.",
    "suggested_check": "Add a concurrency model (or a DB-level lock) and re-verify the amount invariant under interleaved capture/refund.",
    "source": "agent_declared",
    "status": "open",
    "introduced_by_action_id": 22,
    "tags": ["concurrency", "payments"]
  },
  {
    "residual_id": "r2",
    "kind": "unverified",
    "statement": "Dispute and chargeback transitions were not formalized; only 7 of the documented transitions are covered by verification goals.",
    "severity": "medium",
    "target": { "target_type": "artifact", "target_id": "a17" },
    "related_artifact_ids": ["a9"],
    "suggested_check": "Add verification goals for the dispute and chargeback transitions.",
    "source": "agent_declared",
    "status": "open",
    "tags": ["coverage"]
  },
  {
    "residual_id": "r3",
    "kind": "open_question",
    "statement": "Should a refund reset approval_count for a subsequent re-capture? The model currently leaves prior approvals intact.",
    "severity": "low",
    "target": { "target_type": "artifact", "target_id": "a8" },
    "source": "agent_declared",
    "status": "open",
    "tags": ["product-decision"]
  }
]
```

Following §16.1, the discriminators `kind`, `severity`, `source`, and `status` serialize as lowercase snake_case strings, and `target` reuses the `target_ref` projection.

---

# 14. Comments and Review Items

## 14.1 Common target reference

```ocaml
type target_type =
  | TraceTarget
  | ActionTarget
  | ArtifactTarget
  | PolicyTarget
  | PolicyEvaluationTarget
  | ReferenceArtifactTarget

type target_ref =
  { target_type : target_type
  ; target_id : string option
  }
```

## 14.2 Comments

```ocaml
type comment_status =
  | Open
  | Resolved

type comment =
  { comment_id : string
  ; author : string
  ; created_at : string
  ; body : string
  ; target : target_ref
  ; thread_parent_id : string option
  ; status : comment_status option
  ; resolved_at : string option
  ; tags : string list
  }
```

## 14.3 Review items

```ocaml
type review_item_status =
  | ReviewOpen
  | Acknowledged
  | ReviewResolved
  | Waived

type review_item =
  { review_item_id : string
  ; author : string
  ; created_at : string
  ; title : string
  ; body : string option
  ; target : target_ref
  ; assignee : string option
  ; status : review_item_status
  ; blocking : bool option
  ; acknowledged_at : string option
  ; acknowledged_by : string option
  ; resolved_at : string option
  ; resolved_by : string option
  ; resolution_note : string option
  ; tags : string list
  }
```

---

# 15. Trace Links and Lineage

## 15.1 Trace links

```ocaml
type trace_relationship =
  | Supersedes
  | Reruns
  | DerivedFrom
  | SameTask
  | SamePr
  | PolicyRecheckOf
  | ConformanceRecheckOf
  | ForkedFrom
  | RelatedTo

type trace_link =
  { link_id : string
  ; from_trace_id : string
  ; to_trace_id : string
  ; relationship : trace_relationship
  ; created_at : string option
  ; created_by : string option
  ; note : string option
  }
```

## 15.2 Trace lineage summary

```ocaml
type chain_status =
  | Active
  | Superseded
  | Archived

type trace_lineage =
  { parent_trace_id : string option
  ; root_trace_id : string option
  ; chain_position : int option
  ; chain_status : chain_status option
  ; latest_descendant_trace_id : string option
  }
```

Traces are immutable; iteration is represented by linked successor traces.

---

# 16. Interchange Projection Notes

The canonical model above is authoritative.

For interchange, a JSON/Pydantic projection may be derived as follows.

## 16.1 General rule

Each algebraic variant must be serialized using an explicit discriminator.

Examples:
- artifacts use `artifact_type`
- actions use `category` and `type`
- result variants use explicit tags such as `proved`, `refuted`, `sat`, `unknown`

## 16.2 Artifact projection

A strict artifact constructor such as:

```ocaml
FormalModelArtifact (common, payload)
```

may be projected to JSON as:

```json
{
  "artifact_id": "...",
  "artifact_type": "FormalModel",
  "artifact_role": "formal_model",
  "name": "...",
  "format": "iml",
  "revision": 1,
  "producer_action_id": 2,
  "derived_from": ["a1"],
  "supersedes": null,
  "content_ref": null,
  "summary": "...",
  "payload": {
    "model_language": "iml",
    "formal_code": "...",
    "symbols": ["..."],
    "scope": null
  },
  "metadata": null
}
```

## 16.3 Action projection

A strict action such as:

```ocaml
ReasoningAction (common, Verify, payload)
```

may be projected to JSON as:

```json
{
  "id": 4,
  "category": "reasoning",
  "type": "Verify",
  "label": "...",
  "rationale": "...",
  "detail": null,
  "inputs": ["a3"],
  "outputs": ["a4"],
  "request": { "...": "..." },
  "result": { "...": "..." },
  "result_summary": "...",
  "evidence": [],
  "observations": [],
  "execution": {
    "tool": "imandrax",
    "version": "2026.04",
    "method": "model_check",
    "determinism": "deterministic",
    "duration_ms": 1840,
    "cost": null
  },
  "reproducibility": null
}
```

## 16.4 Pydantic generation notes

Reference Pydantic models should be generated as **discriminated unions**.

Recommended approach:
- one `BaseModel` per strict constructor family
- discriminator fields such as `artifact_type`, `category`, and `type`
- decoding must reconstruct the strict canonical model
- invalid discriminator/payload combinations must be rejected during deserialization

## 16.5 Serialization boundary rule

> **JSON and Pydantic are interchange formats. The strict typed model remains the semantic source of truth.**

---

# 17. Recommended Implementation Strategy

## 17.1 Internal model
Use the strict canonical types from this specification in:
- OCaml
- IML
- reasoning-oriented internal tooling

## 17.2 Serialization layer
Generate:
- JSON schema
- Pydantic models
- encoders/decoders

from the strict model, not the reverse.

## 17.3 Validation strategy
Validation should occur at two levels:

1. **wire validation**  
   ensure JSON/Pydantic payloads are structurally well-formed

2. **semantic decoding**  
   ensure the payload can inhabit the canonical strict model

---

# 18. Goals & Acceptance

A trace records what an agent *did*. A **goal** records what it was *trying to do* and how you would know it *succeeded*: the **intent** (what is being changed and why) together with its **acceptance conditions** — the *end node*, an explicit, typed statement of what "done" means.

Where §8.4 **meta-actions** capture the *structure* of the work (how atomic actions group into units of intent), a goal captures its *target* — the conditions the work must satisfy — and, crucially, whether the trace **meets** them. The two are complementary: a goal states the criteria; a meta-action carries them out. A goal may reference the meta-action pursuing it via `meta_action_id`, but neither requires the other.

> Goals are the **positive-target** counterpart to the §13 residual surface's negative space. Residuals say what a trace does *not* establish; a goal's acceptance says what it *must* establish, and its resolution says whether it has. Read together, they let a reviewer see the target, the evidence for it, and the gaps against it in one place.

## 18.1 Canonical model

```ocaml
type acceptance_kind =
  | Change        (* an edit to a symbol *)
  | Property      (* a property that must hold *)
  | Obligation    (* a policy that must be satisfied *)
  | Gap           (* a declared residual that must be closed *)

type acceptance_status =
  | AcceptTodo
  | AcceptDoing
  | AcceptDone
  | AcceptBlocked

(* the selector: which trace object resolves this criterion *)
type acceptance_binding =
  | ChangeBinding    of { symbol : string; file : string option }
  | PropertyBinding  of { symbol : string option; property : string option }
  | ObligationBinding of { policy_id : string }
  | GapBinding       of { residual_id : string }

type acceptance_item =
  { acceptance_id : string
  ; kind : acceptance_kind
  ; label : string                        (* what this criterion means, in plain language *)
  ; binding : acceptance_binding option    (* how it resolves; if absent, `status` is manual *)
  ; status : acceptance_status option      (* authored fallback when unbound or unresolved *)
  }

type goal_status =
  | GoalScratch      (* activity not yet attributed to a named intent *)
  | GoalActive
  | GoalDone
  | GoalAbandoned

type goal =
  { goal_id : string
  ; intent : string                       (* the change and why, in plain language *)
  ; scope : string list                   (* files / symbols the goal touches *)
  ; acceptance : acceptance_item list       (* the end node: what "done" means *)
  ; status : goal_status option
  ; meta_action_id : string option         (* the meta-action pursuing this goal, if any (§8.4) *)
  }
```

The trace record (§5) carries `goals : goal list`, canonicalized as an empty list when no intent is declared.

## 18.2 Semantics

**Acceptance reuses existing evaluation — no new evaluator.** Each acceptance kind *binds* to machinery already in the trace, and its status is **resolved** from that evidence rather than asserted:

- `Change` — resolves from a `Diff` / `IMLModel` artifact touching the bound `symbol` → `AcceptDone` when the edit has landed.
- `Property` — resolves from a `VerificationGoal` (§10.3) matching the binding and its **latest** `VerificationResult` (§10.4) → `AcceptDone` when *proved*, `AcceptBlocked` when *refuted* (carrying the counterexample).
- `Obligation` — resolves from the `policy_evaluation` for the bound `policy_id` → `AcceptDone` when *passed*, `AcceptBlocked` when *failed*.
- `Gap` — resolves from the bound residual's status (§13) → `AcceptDone` when `ResidualAddressed` / `ResidualWaived`.

An item with no binding falls back to its authored `status`. Because resolution reads only established evidence, **progress is grounded, not self-reported**: a goal cannot claim done without the trace object that backs it.

**The end node.** A goal is **reached** when all of its required acceptance items resolve `AcceptDone`. This is the positive dual of the residual surface: the residual surface says a trace declares its gaps; the acceptance surface says a goal declares — and the trace evidences — its target.

> **No evaluator decides whether a goal is met — the evidence does.** Resolution is a **deterministic** function of the trace: each binding is matched against the typed artifacts already present, and the relevance cone (§18.3) is a walk over the existing `derived_from` lineage. There is no model, no heuristic, no scoring in the loop. Every `AcceptDone` therefore traces to a *specific* artifact in the record, and re-running the resolution on the same trace always yields the same result. This is what makes a goal's progress **grounded** (backed by an artifact, not a claim), **auditable** (anyone can re-derive it), and **impossible to self-report** — the same discipline (§2.3) that makes the atomic actions the ground truth.

## 18.3 Derived layer (resolution)

Like the grade, and unlike the *authored* residual surface, a goal's **resolved state is computed from the trace, not stored in it**. It is a projection, produced by enriching the trace against its own evidence (in the reference implementation, `ponens trace enrich`):

- each acceptance item's resolved `status` and an **evidence** pointer (the artifact / evaluation / residual that resolves it);
- the goal's `progress` — resolved items over total (`AcceptDoing` counts as a half);
- the goal's **relevance cone** — the set of `action`s that produced the goal's evidence, obtained by walking each resolved item's evidence artifact backward through `derived_from` lineage; this is the goal-scoped slice of the trace (the steps that mattered for *this* goal);
- the goal's **open gaps** — the goal-scoped residuals: declared residuals bound to a `Gap` item or touching the goal's `scope`, plus derived stale-evidence residuals for the goal's symbols;
- **exploration** — the actions in *no* goal's cone.

These are **derived** and never mutate the record, preserving the ground-truth discipline of §2.3: the authored trace carries only `goals`; a consumer computes their resolution on demand.

**Stale evidence.** A `Property` item is resolved from the *latest* verification result, and a proof is only as current as the code it verified. If the symbol a proof constrains is edited at a *later* action than the proof, the proof is stale — surfaced as a **derived** stale-evidence residual (a computed `Gap`, §13). Consequently a goal cannot silently remain reached after the code underlying one of its proofs changes; the reopened gap is visible in its open-gap set.

## 18.4 Relationship to existing constructs

- **Meta-actions (§8.4)** group actions by *intent* (structure); goals declare *acceptance* (target) and resolve it. A goal *may* be pursued by a meta-action (`meta_action_id`); they need not coincide — a meta-action may exist with no acceptance, and a goal may span several meta-actions.
- **Residual surface (§13)** is the dual. A `Gap` acceptance item *binds to* a residual; a goal's open-gap set is its scoped residuals. Target and negative space are two readings of the same pursuit.
- **Verification goals (§10.3)** are reasoner-level objects; a `Property` acceptance item is *not* a verification goal but a trace-level criterion that **resolves from** one (or more) `VerificationGoal` + `VerificationResult` artifacts. The acceptance item is the intent; the verification goal is the mechanism.
- **Policies** express requirements checked over the whole trace; an `Obligation` acceptance item scopes one such requirement to a goal ("this policy must hold *for this goal*"), resolving from its `policy_evaluation`.

## 18.5 Policy hooks

Because goals and their acceptance are typed and queryable, policies (see the Policy Specification) can govern them. Illustrative:

- **active goals declare acceptance** — every `GoalActive` goal must have a non-empty `acceptance` list.
- **no commit against an unreached goal** — `G(GitCommit → ∀ i ∈ active_goal.acceptance . i.status = AcceptDone)` (for the required items).
- **reached goals carry no open critical gaps** — `G(GoalDone → ¬∃ r ∈ open_gaps(goal) . r.severity = Critical ∧ r.status = ResidualOpen)`.
- **proofs stay current** — a `Property` item whose evidence is stale (§18.3) must not resolve `AcceptDone`.

As with the residual surface, the bar is not that goals be *trivially* met, but that their intent, criteria, and evidence be *declared and checkable*.

## 18.6 Interchange projection

A goal declaring its intent and acceptance (authored form):

```json
"goals": [
  {
    "goal_id": "g-3ds-approval",
    "intent": "Add 3DS/SCA and a high-risk two-approval requirement to the capture flow",
    "scope": ["stripe_payment_flow.py", "capture_payment", "confirm_payment_intent"],
    "status": "GoalActive",
    "meta_action_id": "m-payment-hardening",
    "acceptance": [
      { "acceptance_id": "a1", "kind": "Change", "label": "Require two approvals before capture",
        "binding": { "symbol": "capture_payment" } },
      { "acceptance_id": "a2", "kind": "Property", "label": "Capture blocked unless 3DS done and two approvals",
        "binding": { "property": "blocked" } },
      { "acceptance_id": "a3", "kind": "Obligation", "label": "Conforms to the payment reference model",
        "binding": { "policy_id": "stripe_conformance_required" } },
      { "acceptance_id": "a4", "kind": "Gap", "label": "Dispute / chargeback transitions unverified",
        "binding": { "residual_id": "r2" } }
    ]
  }
]
```

The same goal after resolution (derived; `status`, `evidence`, `progress`, `cone`, and `open_gaps` are computed, not authored):

```json
{
  "goal_id": "g-3ds-approval",
  "progress": 0.5,
  "cone": [3, 7, 8, 9, 12],
  "open_gaps": 2,
  "acceptance": [
    { "acceptance_id": "a1", "kind": "Change",     "status": "AcceptDone",    "evidence": "art-diff-14" },
    { "acceptance_id": "a2", "kind": "Property",   "status": "AcceptDone",    "evidence": "art-vr-19" },
    { "acceptance_id": "a3", "kind": "Obligation", "status": "AcceptTodo",    "evidence": null },
    { "acceptance_id": "a4", "kind": "Gap",        "status": "AcceptTodo",    "evidence": "r2" }
  ]
}
```

---


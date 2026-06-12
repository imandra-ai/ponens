# Trace, Policy, and Review-Case Semantics

## Version

**Version:** 0.2  
**Status:** Draft  
**Purpose:** Clarify the distinction and relationship between the trace specification, policy specification, and review-case specification, and define how policy satisfaction is interpreted over traces and review-case context

---

# 1. Three Connected but Distinct Specifications

The computable governance framework is built on **three separate but connected specifications**:

1. a **trace specification**
2. a **policy specification**
3. a **review-case specification**

These should be treated as distinct but composable semantic layers.

## 1.1 Trace specification

The **trace specification** defines the execution record and its formal semantics.

It describes:
- what objects exist in a trace
- what actions mean
- what artifacts mean
- how lineage and derivation work
- how execution evolves over time
- how reproducibility and review metadata attach to a trace

A trace is therefore not just a log format. It is a **typed execution structure with formal meaning**.

## 1.2 Policy specification

The **policy specification** defines:
- the policy object model
- the policy DSL
- the semantics of policy formulas
- how policies are evaluated over traces
- how policies may be evaluated over review-case context where enabled

A policy is therefore not a trace object. It is a **constraint or formula interpreted over traces and, optionally, review-case state**.

## 1.3 Review-case specification

The **review-case specification** defines:
- the workflow object that governs one or more traces over time
- problem statements and acceptance criteria
- active-trace semantics
- workflow, approval, audit, and explanation state
- local-first and remote synchronization semantics

A review case is therefore not a trace and not a policy. It is the **governed workflow context** within which traces are produced, reviewed, and approved.

## 1.4 Relationship between the three

The dependency structure is:

```text
Trace semantics ─────────────┐
                             ├──> Policy semantics / satisfaction
Review-case semantics ───────┘
```

A more workflow-oriented reading is:

```text
Trace semantics
    ↓
Review-case semantics over traces
    ↓
Policy semantics over traces and review-case context
```

Both views are useful:

- traces define execution history
- review cases organize governed work across traces over time
- policies constrain and validate those structures

---

# 2. What a Trace Is Semantically

A **trace** is a typed execution structure representing one concrete run of an AI agent workflow.

Semantically, a trace contains:

- a finite sequence of actions
- a typed collection of artifacts
- explicit producer-consumer relationships between actions and artifacts
- lineage and derivation relations across artifacts
- workflow and review metadata attached at the trace level
- an execution history over which governance statements may be evaluated

## 2.1 Informal semantic view

A trace is the record of:

- what the agent did
- what data and artifacts it used
- what reasoning steps it performed
- what outputs it produced
- how those outputs depend on prior actions and artifacts

## 2.2 Operational semantic view

A trace can be viewed as a sequence of state transitions:

```text
TraceState_0 --(Action_1)--> TraceState_1 --(Action_2)--> ... --(Action_n)--> TraceState_n
```

Each action may:
- consume existing artifacts
- produce new artifacts
- record observations or evidence
- change the set of available objects for future steps

This gives the trace an operational interpretation, not just a documentary one.

## 2.3 Structural semantic view

A trace also induces one or more graph structures:

- an **action sequence**
- an **artifact DAG**
- optional **trace lineage** across reruns and successors
- optional **review / approval / audit relationships** at the trace level

These structures are semantically meaningful and may be referenced by policy formulas.

## 2.4 Trace semantics as domain of discourse

The trace specification defines the objects and relations that policies can talk about at execution level.

Examples include:
- actions
- artifacts
- inputs
- outputs
- derivation
- ancestry
- trace-level review items
- trace-level approvals or approval actions
- policy evaluations
- reproducibility metadata

A trace is therefore the **execution substrate** of the governance system.

---

# 3. What a Review Case Is Semantically

A **review case** is the workflow-level object that governs one or more traces over time.

A trace shows one run. A review case shows where the overall governed change stands.

Semantically, a review case contains:

- a **problem formulation**
- acceptance criteria and scope hints
- a set of **linked traces**
- one usually **active trace**
- workflow state
- approval and audit state
- explanation state
- local/remote synchronization state
- optional anchoring to PRs, branches, tasks, or tickets

## 3.1 Informal semantic view

A review case is the record of:

- what problem is being solved
- which traces belong to that solving effort
- which trace is currently active
- what blockers, approvals, and audits still matter
- whether the current work is still explained by the original problem formulation

## 3.2 Workflow semantic view

A review case does not redefine the internal structure of traces.  
Instead, it organizes them into a governed solving process.

It answers questions such as:

- what is the active trace?
- are there unresolved blocking items?
- is the case ready for approval?
- is the case auditable?
- has the current workspace diverged from the original governed effort?
- has the review case been synchronized remotely?

## 3.3 Governing principle

The core invariant is:

> **All meaningful current modifications should retrace to the original problem formulation through the review-case graph, and all steps used to reach them should remain within policy.**

This makes the review case more than a ticket or container.  
It is a **governed solving context**.

## 3.4 Review-case semantics as domain of discourse

The review-case specification defines the objects and relations that policies may talk about at workflow level.

Examples include:
- problem statements
- active trace
- review-case status
- approval records
- audit records
- case-level review items
- case-level explanation state
- sync state
- external anchors

A review case is therefore the **workflow substrate** of the governance system.

---

# 4. What a Policy Is Semantically

A **policy** is a well-formed formula in the policy DSL interpreted over a trace and, optionally, review-case context.

Policies do not create execution history.  
They constrain, require, forbid, or validate properties of that history and context.

## 4.1 Informal semantic view

A policy expresses a governance rule such as:

- something must happen before a commit
- some reasoning step must exist before a high-stakes change
- some artifact must derive from approved upstream evidence
- some approval must be present before progression
- some output must be reproducible
- no review case may enter approval while blocking items remain open
- the active trace must explain all current modified files before approval

## 4.2 Policies as predicates over traces and review cases

Semantically, a policy is a predicate over:
- traces
- and, where explicitly enabled, review-case state

A policy may refer to:
- the temporal ordering of actions
- the existence of specific artifacts
- lineage relationships between artifacts
- the presence or absence of approvals or review items
- properties of action fields, artifact fields, or trace-level metadata
- review-case workflow state
- explanation status
- audit or approval readiness

## 4.3 Temporal + structural + workflow nature

The policy language is not only temporal.

It may include:
- temporal operators
- scoped temporal operators
- first-order predicates
- quantifiers
- set comprehensions
- lineage / reachability predicates
- field predicates over actions and artifacts
- workflow predicates over review-case state

So a policy is best understood as a **governance formula over a structured execution-and-workflow model**, not just as a simple temporal rule.

## 4.4 Policy semantics depend on trace and review-case semantics

A policy formula only has meaning relative to the semantics of the objects it refers to.

For example:
- `reasoning_action(a)` must be grounded in the trace action model
- `ancestor_of(x, y)` must be grounded in artifact lineage
- `active_trace(c)` must be grounded in review-case semantics
- `blocking_items_open(c)` must be grounded in case-level review items

Therefore, the policy DSL must be interpreted **with respect to the trace specification and, where used, the review-case specification**.

---

# 5. How Policy Satisfaction Is Defined

The key semantic relation is:

> **A trace or review-case context satisfies a policy if the policy formula evaluates to true over the relevant semantic structures.**

## 5.1 Trace-only satisfaction

Let:

- `T` be the set of valid traces
- `τ ∈ T` be a particular trace
- `φ` be a well-formed policy formula that is trace-interpretable

Then:

```text
τ ⊨ φ
```

means:

> trace `τ` satisfies policy `φ`

and:

```text
τ ⊭ φ
```

means:

> trace `τ` does not satisfy policy `φ`

## 5.2 Review-case-context satisfaction

Let:

- `C` be the set of valid review cases
- `c ∈ C` be a review case
- `τ_active(c)` be its active trace when defined
- `φ` be a well-formed policy formula whose semantics may refer to both trace and review-case objects

Then satisfaction may be evaluated relative to the combined context:

```text
(c, τ_active(c)) ⊨ φ
```

meaning:

> review case `c`, together with its relevant trace context, satisfies policy `φ`

## 5.3 What evaluation may depend on

Evaluating policy satisfaction may depend on:

- action order
- trace positions
- artifact existence
- lineage and ancestry relations
- field values
- review / approval state
- reproducibility metadata
- review-case workflow state
- explanation state
- sync state
- any other semantics defined by the trace or review-case specifications

---

# 6. Examples of Satisfaction Contexts

## 6.1 Trace-only example

A policy like:

```text
G(GitCommit -> P(RunTests /\ completed))
```

is satisfied if, at every commit action in the trace, there exists an earlier test action satisfying the required condition.

## 6.2 Structural trace example

A policy like:

```text
G(GeneratedTests -> ancestor_of(StateSpaceAnalysisResult, GeneratedTests))
```

is satisfied if every generated-tests artifact has the required upstream state-space analysis evidence in its lineage.

## 6.3 Review / approval trace example

A policy like:

```text
G(high_stakes_edit(a) -> F approval_action_for(a))
```

is satisfied if every high-stakes edit is eventually followed by the required approval action.

## 6.4 Review-case workflow example

A policy like:

```text
ReadyForApproval(review_case) -> not blocking_items_open(review_case)
```

is satisfied if a review case only enters approval-ready state when no blocking case-level review items remain open.

## 6.5 Explanation-status example

A policy like:

```text
Approved(review_case) -> explanation_status(review_case) = Explained
```

is satisfied if a review case can only be approved when the current work remains fully explained by the original problem and active trace.

---

# 7. Best Architectural Rule

The architectural rule is:

> **Traces define execution semantics, review cases define workflow semantics over traces, and policies define the governance logic evaluated over those structures.**

This implies:

- trace meaning is primary at execution level
- review-case meaning is primary at workflow level
- policy meaning is secondary and interpretive
- policy formulas should never redefine trace or review-case semantics
- policy formulas should instead be evaluated against the semantics already established by the underlying specifications

---

# 8. Recommended Specification Structure

To make this distinction explicit, the system should now be documented as **four linked pieces**:

## 8.1 Trace Specification
Defines:
- trace object model
- action semantics
- artifact semantics
- lineage semantics
- trace-level review / approval / audit semantics
- reproducibility semantics

## 8.2 Policy Specification
Defines:
- policy object model
- DSL syntax
- temporal operators
- first-order predicates
- semantic vocabulary
- satisfaction semantics

## 8.3 Review-Case Specification
Defines:
- problem statements
- active-trace semantics
- workflow state
- approval and audit state
- explanation state
- local/remote sync semantics
- external anchoring semantics

## 8.4 Binding Specification
Defines:
- how policy predicates map to trace fields and constructors
- how lineage predicates map to artifact derivation
- how action-role predicates map to action categories / types
- how artifact-role predicates map to artifact types / roles / metadata
- how workflow predicates map to review-case semantics
- how combined trace/review-case policy evaluation is performed

This fourth piece is the bridge that turns the three semantic specifications into one coherent system.

---

# 9. Current Architecture and Remaining Open Work

The architecture is now more mature than when this note was first written.

## 9.1 What now exists

There is now a clearer split between:
- a trace specification
- a policy specification
- a review-case specification

## 9.2 What remains open

The main remaining open work is:

### A. Binding specification
A dedicated document or section defining:
- policy-to-trace binding
- policy-to-review-case binding
- combined evaluation context rules

### B. Snapshot specification
A dedicated snapshot specification for:
- approval candidates
- audit handoff points
- reproducibility checkpoints

### C. Explanation algorithms
A precise specification of:
- how explanation status is computed
- how active trace relates to current workspace state
- how unexplained files / changes are identified

### D. Case-level policy semantics
A more formal treatment of:
- when a policy is trace-only
- when it is review-case-only
- when it is interpreted over combined context

### E. Projection / serialization guidance
A unified guide for:
- JSON projection
- Pydantic generation
- canonical typed OCaml / IML models

---

# 10. Summary

The clean conceptual distinction is:

- a **trace** is a typed execution structure with formal semantics
- a **review case** is a workflow object governing one or more traces over time
- a **policy** is a formula interpreted over those structures
- **policy satisfaction** determines whether the governed execution and workflow obey the declared constraints

Or, in one sentence:

> **Traces capture runs, review cases govern the broader solving process, and policies define the rules evaluated over both.**

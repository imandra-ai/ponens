# Trace Semantics vs. Policy Semantics

## Version

**Version:** 0.1  
**Status:** Draft  
**Purpose:** Clarify the distinction between the trace specification and the policy specification, and define how policy satisfaction is interpreted over traces

---

# 1. Two Connected but Distinct Specifications

The computable governance framework is built on **two separate but connected specifications**:

1. a **trace specification**
2. a **policy specification**

These should be treated as distinct layers.

## 1.1 Trace specification

The **trace specification** defines the execution record and its formal semantics.

It describes:
- what objects exist in a trace
- what actions mean
- what artifacts mean
- how lineage and derivation work
- how review and audit objects are represented
- how execution evolves over time

A trace is therefore not just a log format. It is a **typed execution structure with formal meaning**.

## 1.2 Policy specification

The **policy specification** defines:
- the policy object model
- the policy DSL
- the semantics of policy formulas
- how policies are evaluated over traces

A policy is therefore not a trace object. It is a **constraint or formula interpreted over a trace**.

## 1.3 Relationship between the two

The dependency is one-way:

```text
Trace semantics
    ↓
Policy semantics over traces
```

The trace specification defines the domain of discourse.  
The policy specification defines formulas interpreted over that domain.

Policies should not redefine trace meaning.  
Instead:

- the **trace specification** defines the semantics of actions, artifacts, lineage, and workflow objects
- the **policy specification** defines statements about those semantics

---

# 2. What a Trace Is Semantically

A **trace** is a typed execution structure representing one concrete run of an AI agent workflow.

Semantically, a trace contains:

- a finite sequence of actions
- a typed collection of artifacts
- explicit producer-consumer relationships between actions and artifacts
- lineage and derivation relations across artifacts
- workflow and review metadata
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
- optional **review / approval / audit relationships**

These structures are semantically meaningful and may be referenced by policy formulas.

## 2.4 Trace semantics as domain of discourse

The trace specification defines the objects and relations that policies can talk about.

Examples include:
- actions
- artifacts
- inputs
- outputs
- derivation
- ancestry
- review items
- approvals
- policy evaluations
- reproducibility metadata

A trace is therefore the **semantic substrate** of the governance system.

---

# 3. What a Policy Is Semantically

A **policy** is a well-formed formula in the policy DSL interpreted over a trace.

Policies do not create execution history.  
They constrain, require, forbid, or validate properties of that history.

## 3.1 Informal semantic view

A policy expresses a governance rule such as:

- something must happen before a commit
- some reasoning step must exist before a high-stakes change
- some artifact must derive from approved upstream evidence
- some approval must be present before progression
- some output must be reproducible

## 3.2 Policies as predicates over traces

Semantically, a policy is a predicate over traces.

A policy may refer to:
- the temporal ordering of actions
- the existence of specific artifacts
- lineage relationships between artifacts
- the presence or absence of approvals or review items
- properties of action fields, artifact fields, or trace-level metadata

## 3.3 Temporal + structural nature

The policy language is not only temporal.

It may include:
- temporal operators
- scoped temporal operators
- first-order predicates
- quantifiers
- set comprehensions
- lineage / reachability predicates
- field predicates over actions and artifacts

So a policy is best understood as a **governance formula over a structured trace**, not just as a simple temporal rule.

## 3.4 Policy semantics depend on trace semantics

A policy formula only has meaning relative to the trace semantics.

For example:
- `reasoning_action(a)` must be grounded in the trace action model
- `ancestor_of(x, y)` must be grounded in artifact lineage
- `active_trace(...)` must be grounded in review-case semantics if used

Therefore, the policy DSL must be interpreted **with respect to the trace specification**.

---

# 4. How Policy Satisfaction over Traces Is Defined

The key semantic relation is:

> **A trace satisfies a policy if the policy formula evaluates to true over the trace under the trace semantics.**

## 4.1 Satisfaction relation

Let:

- `T` be the set of valid traces defined by the trace specification
- `τ ∈ T` be a particular trace
- `φ` be a well-formed formula in the policy DSL

Then:

```text
τ ⊨ φ
```

means:

> trace `τ` satisfies policy `φ`

And:

```text
τ ⊭ φ
```

means:

> trace `τ` does not satisfy policy `φ`

This is the core formal distinction:

- the **trace specification** defines valid `τ`
- the **policy specification** defines valid `φ`
- the **satisfaction relation** defines when `τ` satisfies `φ`

## 4.2 What evaluation depends on

Evaluating whether `τ ⊨ φ` may depend on:

- action order
- trace positions
- artifact existence
- lineage and ancestry relations
- field values
- review / approval state
- reproducibility metadata
- any other semantics defined by the trace specification

## 4.3 Examples

### Temporal example
A policy like:

```text
G(GitCommit → P(RunTests ∧ completed))
```

is satisfied if, at every commit action in the trace, there exists an earlier test action satisfying the required condition.

### Structural example
A policy like:

```text
G(GeneratedTests → ancestor_of(StateSpaceAnalysisResult, GeneratedTests))
```

is satisfied if every generated-tests artifact has the required upstream state-space analysis evidence in its lineage.

### Review / approval example
A policy like:

```text
G(high_stakes_edit(a) → F approval_action_for(a))
```

is satisfied if every high-stakes edit is eventually followed by the required approval action.

---

# 5. Best Architectural Rule

The architectural rule is:

> **Traces define the execution semantics; policies define the governance logic evaluated over those traces.**

This implies:

- trace meaning is primary
- policy meaning is secondary and interpretive
- policy formulas should never redefine trace semantics
- policy formulas should instead be evaluated against the semantics already established by the trace specification

---

# 6. Recommended Specification Structure

To make this distinction explicit, the system should be documented as three linked pieces:

## 6.1 Trace Semantics Specification
Defines:
- trace object model
- action semantics
- artifact semantics
- lineage semantics
- workflow semantics
- review / approval / audit semantics
- reproducibility semantics

## 6.2 Policy Semantics and DSL Specification
Defines:
- policy object model
- DSL syntax
- temporal operators
- first-order predicates
- semantic vocabulary
- policy evaluation semantics

## 6.3 Policy-to-Trace Binding Specification
Defines:
- how policy predicates map to concrete trace fields
- how lineage predicates map to artifact derivation
- how action-role predicates map to action categories / types
- how artifact-role predicates map to artifact types / roles / metadata
- how workflow predicates map to review-case semantics where relevant

This third document or section is the bridge that turns the two specifications into one coherent system.

---

# 7. Immediate Next Steps

The next recommended steps are:

## 7.1 Define trace semantics explicitly
Add a formal semantic preamble to the trace specification stating:
- what a trace is
- what objects and relations it defines
- what execution and lineage mean
- what is considered semantically authoritative

## 7.2 Define policy semantics explicitly
Add a formal semantic preamble to the policy specification stating:
- what a policy formula is
- what kinds of operators and predicates it may use
- what kinds of trace properties it may constrain

## 7.3 Define policy satisfaction over traces
Add a section defining:
- the satisfaction relation `τ ⊨ φ`
- what trace context is available during evaluation
- how temporal, structural, and field predicates are interpreted

## 7.4 Add a binding section
Add an explicit section such as:

**Binding the Policy DSL to the Trace Specification**

This should map semantic predicates to concrete trace-schema fields and relations.

Examples:
- `reasoning_action(a)` → action category/type mapping
- `inputs(a)` → action input artifact references
- `ancestor_of(x, y)` → transitive closure over `derived_from`
- `approved_reference_artifact(x)` → artifact role / metadata mapping

## 7.5 Separate semantic roles from implementation details
Where possible:
- keep the **trace schema concrete**
- keep the **policy vocabulary semantic**
- define mappings between them once

This is especially important if the framework is intended to be reasoner-agnostic.

---

# 8. Summary

The clean conceptual distinction is:

- a **trace** is a typed execution structure with formal semantics
- a **policy** is a formula interpreted over that structure
- **policy satisfaction** determines whether a trace obeys the declared governance constraints

Or, in one sentence:

> **Traces define the execution world; policies define the rules evaluated over that world.**

# Ponens Policy Language

**Version:** 0.2 · companion to [`POLICY_SPEC_v0_2`](./POLICY_SPEC_v0_2.md)

A *policy* is a machine-checkable rule over a trace. Each policy carries a
**formula** written in this language and is evaluated over a trace as a
**conformance check** — the trace either satisfies the formula (`pass`),
violates it (`fail`), or contains nothing the policy applies to (`not_applicable`).

The language is **LTLf** — linear temporal logic over finite traces — extended
with *scoped-past* operators and *first-order structural predicates* over the
typed artifact graph. Formulas that use only standard temporal operators and
action-type propositions are plain propositional LTLf; formulas that use
quantifiers, set comprehensions, or lineage predicates require a richer
evaluation engine. Every policy declares which fragment it uses in its
`language_level` field (see §3).

> **This is the reader-friendly operator reference.** The *canonical*, typed
> definition of the language lives in [`POLICY_SPEC_v0_2`](./POLICY_SPEC_v0_2.md)
> §9–13 (the OCaml / IML form); this companion presents the same operators as
> tables and worked examples — the two are kept in lock-step at the same version.
>
> **Notation.** Policy `formula` fields in the
> [gallery](https://ponens.dev/gallery) use the **unicode surface** shown here
> (`→`, `∧`, `∨`, `¬`, `P_target`); POLICY_SPEC §10 gives the equivalent
> **ASCII / OCaml form** (`->`, `/\`, `\/`, `not`, typed constructors like
> `PTarget`). They denote the same language.

---

## 1. Design rationale

### Why LTL as the foundation

A bespoke JSON DSL (`must_have_prior_action`, `must_derive_from_artifact_type`, …)
encodes temporal meaning implicitly. Every rule type becomes a one-off encoding
of a temporal pattern, which leads to:

- a growing vocabulary of rule types as new patterns appear;
- ambiguous semantics (what exactly does "prior" mean — anywhere? in the dependency chain?);
- no composition model (how do you negate or combine rules?);
- no connection to existing verification tooling.

LTL supplies the temporal foundation instead:

- a small set of operators covers all temporal patterns;
- the semantics are mathematically precise;
- formulas compose naturally with `∧`, `∨`, `¬`;
- established model checkers and runtime monitors can evaluate traces against LTL properties.

### Beyond plain LTL

Not every trace policy is a purely propositional temporal property. Some need:

- **scoped temporality** — "previously *on the same file*" vs "previously *anywhere in the trace*";
- **quantification** over artifacts or inputs — `∀ input ∈ inputs(a)`;
- **graph reachability** over the artifact DAG — `ancestors(derived_from)`;
- **data-aware checks** — `target_artifact_id ∈ {a.id | a.type = IMLModel}`.

The policy language is therefore **LTL extended with scoped operators and
first-order predicates over traces**.

### Specification-level notation

The `formula` field holds a **specification-level formula** with precise
semantics — it is not the concrete input syntax of any one tool. Compilation to
a model checker's language or to a runtime monitor is a separate implementation
step. ponens ships a reference evaluator that runs the check offline.

---

## 2. Operators

### 2.1 Future-time operators

| Operator | Name | Meaning |
|---|---|---|
| `G φ` | Globally | `φ` holds at every position in the trace |
| `F φ` | Finally | `φ` holds at some future position |
| `X φ` | Next | `φ` holds at the next position |
| `φ U ψ` | Until | `φ` holds at every position until `ψ` holds |

### 2.2 Past-time operators

Past-time LTL (PLTL) is especially natural for trace policies, since most rules
look *backwards* from a triggering event.

| Operator | Name | Meaning |
|---|---|---|
| `P φ` | Previously | `φ` held at some earlier position |
| `H φ` | Historically | `φ` held at every earlier position |
| `φ S ψ` | Since | `φ` has held at every position since `ψ` last held |
| `φ S_last ψ` | Since last | `φ` held at some point since the most recent `ψ` (or trace start if no `ψ`) |

### 2.3 Scoped past-time operators

Plain `P φ` means "at *some* earlier position." That is often too weak. For
policies that require *relevant* prior work — not just any prior work — scoped
operators restrict the search:

| Operator | Name | Meaning |
|---|---|---|
| `P_target φ` | Previously (same target) | `φ` held at some earlier position targeting the same file, module, or artifact |
| `P_chain φ` | Previously (dependency chain) | `φ` held at some earlier position in the artifact lineage of the current action |
| `H_target φ` | Historically (same target) | `φ` held at every earlier same-target position |
| `H_chain φ` | Historically (dependency chain) | `φ` held at every earlier position in the dependency chain |

**Choosing the right scope:**

- `P` (global) — any prior match suffices. Use for coarse workflow checks like `tests_before_commit`.
- `P_target` — the prior match must concern the same file or artifact. Use for `research_before_edit`.
- `P_chain` — the prior match must lie in the artifact dependency chain. Use for `reasoning_required_for_high_stakes`.

### 2.4 Boolean connectives

| Operator | Name |
|---|---|
| `¬φ` | Negation |
| `φ ∧ ψ` | Conjunction |
| `φ ∨ ψ` | Disjunction |
| `φ → ψ` | Implication |

### 2.5 Atomic propositions

Atomic propositions are evaluated at each position (action) in the trace:

- **Action types** — `EditFile`, `ReadFile`, `GitCommit`, `RunTests`, `DeleteFile`, `CreateFile`, `SearchCode`, `AnalyzeCode`, `ReadDocumentation`, `Formalize`, `Verify`, `DefineVG`, `Decompose`, `GenerateTests`, …
- **Action categories** — `gateway`, `reasoning`, `activity`
- **Status predicates** — `completed`, `failed`
- **Field predicates** — `rationale ≠ ∅`
- **Path predicates** — `high_stakes_path` (matches configured path patterns)
- **Trace-level predicates** — `start_event`, `end_event`

### 2.6 Structural predicates

These go beyond propositional LTL — they read the typed artifact graph and
require a richer evaluation engine.

- **Artifact types** — `VerificationGoal`, `VerificationResult`, `IMLModel`, `Decomposition`, `GeneratedTests`, `UserApproval`
- **Result status** — `proved`, `refuted`, `sat`, `unknown`
- **Lineage** — `ancestors(derived_from)`, the transitive closure of `derived_from` over the artifact DAG
- **Reference integrity** — `target_artifact_id ∈ {a.id | a.type = T}`
- **Set operations** — `inputs(a)`, `outputs(b)`, `target(a)`, and set comprehensions `{… | …}`

### 2.7 Quantifiers

Used in structural policies that reason over collections:

- `∀ x ∈ S` — for all elements in set `S`
- `∃ x ∈ S` — there exists an element in set `S`
- `∃! x ∈ S` — there exists exactly one element in set `S`

### 2.8 Interpretation over traces

A trace `τ = a₀, a₁, …, aₙ` is a finite sequence of actions over an artifact
graph. A formula `φ` is evaluated at position `i`:

- `(τ, i) ⊨ G φ`  iff for all `j ≥ i`, `(τ, j) ⊨ φ`
- `(τ, i) ⊨ F φ`  iff there exists `j ≥ i` such that `(τ, j) ⊨ φ`
- `(τ, i) ⊨ P φ`  iff there exists `j < i` such that `(τ, j) ⊨ φ`
- `(τ, i) ⊨ H φ`  iff for all `j < i`, `(τ, j) ⊨ φ`
- `(τ, i) ⊨ φ S ψ`  iff there exists `j < i` with `(τ, j) ⊨ ψ` and for all `k`, `j < k < i`, `(τ, k) ⊨ φ`

Scoped operators restrict the witnessing position `j` to those sharing the
current action's target (`P_target`, `H_target`) or lying in its `derived_from`
lineage (`P_chain`, `H_chain`).

---

## 3. Language levels

Every policy declares the fragment it uses in its `language_level` field. This
tells the evaluator (and the reviewer) how much machinery a check needs.

| `language_level` | Uses | Example |
|---|---|---|
| `pure_temporal` | future/past operators + atomic propositions only | `tests_before_commit` |
| `scoped_temporal` | adds scoped-past operators (`P_target`, `P_chain`, …) | `research_before_edit` |
| `structural` | adds quantifiers, set comprehensions, and lineage predicates | `data_flow_integrity` |

---

## 4. Standard encodings

Real policies from the [gallery](https://ponens.dev/gallery), with their
`language_level`:

**`tests_before_commit`** — *pure temporal*

```
G(GitCommit → P(RunTests ∧ completed))
```
Every commit is preceded by a test run that completed.

**`research_before_edit`** — *scoped temporal*

```
G(EditFile → P_target(ReadFile ∨ ReadDocumentation ∨ SearchCode ∨ AnalyzeCode))
```
No edit without first reading or searching the relevant code (same target).

**`reasoning_required_for_high_stakes`** — *scoped temporal*

```
G(EditFile ∧ high_stakes_path → P_chain(VerificationResult(proved ∨ sat) ∨ Decomposition))
```
On a high-stakes path, an edit must be backed — somewhere in its lineage — by a
proof, a SAT result, or a decomposition.

**`data_flow_integrity`** — *structural*

```
G(∀ input ∈ inputs(a) → ∃! b . b < a ∧ input ∈ outputs(b))
```
Every input an action consumes was produced by exactly one earlier action — the
lineage DAG has no dangling or ambiguous edges.

**`no_open_critical_residuals`** — *structural*

```
¬∃ r ∈ residuals . r.severity = Critical ∧ r.status = Open
```
The trace cannot ship with an unresolved critical gap on its residual surface.

---

## 5. Evaluation semantics

Evaluating a policy against a trace yields one of three results:

- **`pass`** — the formula holds over the trace.
- **`fail`** — the formula is violated; the evaluator reports the witnessing position(s).
- **`not_applicable`** — the policy's trigger never occurs (e.g. a commit policy on a trace with no commit). N/A results are excluded when a grade renormalizes compliance.

Evaluation may occur:

- once for the whole trace, after completion;
- incrementally as actions are appended (runtime monitoring);
- at specific checkpoints (e.g. before a commit action is permitted).

For runtime monitoring, past-time formulas are evaluated incrementally: each new
action requires only local computation against the current state and a finite
set of accumulated obligations. This makes PLTL well suited to online policy
enforcement during agent execution — blocking an action *before* it violates a
policy.

---

## 6. Relationship to other work

Conformance checking of finite execution traces against temporal-logic
constraints is the foundation of **DECLARE** / declarative process mining and of
**runtime verification**. The Ponens Policy Language applies that established
machinery to the traces produced by AI coding agents, and extends it with the
scoped-past and structural operators needed to talk about a *typed artifact
graph* (files, models, verification results, lineage) rather than a flat event
log.

See also the [Policy Specification](./POLICY_SPEC_v0_2.md) (the policy object,
selectors, and evaluation records) and the
[Trace Specification](./TRACE_SPEC_v1_6.md) (the actions and artifacts these
formulas range over).

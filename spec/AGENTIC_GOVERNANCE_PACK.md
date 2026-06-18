# Agentic AI Runtime Governance — ponens Policy Pack

This pack maps the **FIX AI Working Group's proposed runtime-governance scheme**
onto computable ponens policies. It turns the proposal's traffic-light
(Green / Amber / Red) testing scheme into a set of formulas that
`ponens trace check` evaluates **deterministically over an agent's execution
trace** — which is exactly the property the proposal requires of any binding
control.

**Sources**
- FIX AI Working Group, *Proposal on Agentic AI Runtime Governance under FIX
  Protocol Extensions* (R. Healey & K. Houston, 12 Jun 2026).
- L. Szpruch, A. Sudjianto, T. Bhatti, G. Ang (2026), *Scalable Runtime
  Governance for Agentic AI in Financial Services* (SSRN 6567199) — the
  capability-centric framework and four-tier risk model the scheme is built on.
- *June 2026 Update on Agentic AI in Secondary Markets* (FIX AI WG / IMWG).

## Why this maps onto ponens

The proposal states the design requirement directly (§10.3):

> "a governance decision that cannot be expressed as a **deterministic function
> over the governed state** and measurable signals, executing in bounded time and
> independently of the language model, is advisory guidance, not binding
> enforcement."

A ponens policy *is* a deterministic function over a trace that returns a
verdict. So the correspondence is structural, not analogical:

| FIX proposal | ponens |
| --- | --- |
| Agent execution record (identity, intent, tool calls, approvals, telemetry) | the **trace** |
| Traffic-light condition (per domain) | a **policy** (temporal / structural formula) |
| **GREEN / AMBER / RED** | verdict **pass** / **warning-fail** / **error-fail** |
| `GovernanceState` field | the **aggregate** of the pack over a trace |
| Decision priority ordering (§6.3) | severity + exit-code aggregation |
| Four governance tiers (Assistive → Critical Autonomous) | pack **tier profiles** |
| Szpruch capability failure modes (C1–C4) | individual safety policies |

`ponens trace check` already produces the aggregation: `PASS` = Green,
`WARN` (a `warning`-severity fail) = Amber, `FAIL` (an `error`-severity fail) =
Red, and a non-zero exit code = "this trace is not Green" — i.e. the
`GovernanceState` the proposal wants carried in a new FIX field.

## Trace model

Governance facts appear in the trace as:

- **Action types** (the agentic vocabulary added for this pack): `ToolCall`,
  `Retrieve`, `Compute`, `Draft`, `Release` (alongside existing `UserApproval`,
  `Deploy`, `GitCommit`, …).
- **Per-action predicates** — governance attributes the runtime emits per action,
  matched against the action text: `agent_id_resolved`, `kya_valid`,
  `vlei_present`, `dce_current`, `intent_resolved`, `within_constraint_scope`,
  `policy_current`, `in_allowlist`, `authenticated`, `approval_scope_covers`,
  `approver_1`, `approver_2`, `default_deny_confirmed`, `provenance_checked`,
  `recency_checked`, `deterministic_recompute`, `template_compliant`,
  `decision_path_present`, `guard_violation`, `prohibited_transition`,
  `credential_expiring`.
- **`telemetry`** — a trace-level list of governance-semantic spans
  (`{name, status}`), quantified over by the telemetry-completeness policy.
- **`trigger` / `outcome`** — trace-level lifecycle (start/end events).

Worked traces: [`examples/agentic_governance/governed.json`](../examples/agentic_governance/governed.json)
(all 21 Green) and [`violating.json`](../examples/agentic_governance/violating.json)
(8 Red + 2 Amber). Run `ponens trace check <file>`.

## The pack

`error` severity ⇒ **Red** (halt / containment); `warning` severity ⇒ **Amber**
(flag / refer). Bounds (`Lmax`, tool budget) are shown at illustrative values and
are set per deployment / DCE.

### 1. Identity & Authorisation (`security`)
| Policy | Formula | RAG | Tier |
| --- | --- | --- | --- |
| `agent_identity_resolved` | `G(action → agent_id_resolved ∧ kya_valid)` | R | 1–4 |
| `legal_entity_vlei_present` | `G(action → vlei_present)` | R | 1–4 |
| `dce_current_for_consequential` | `G(ToolCall ∨ Release ∨ Deploy → dce_current)` | R | 2–4 |
| `credential_not_expiring` | `G(action → ¬credential_expiring)` | A | 1–4 |

### 2. Intent & Constraint (`conformance`)
| Policy | Formula | RAG | Tier |
| --- | --- | --- | --- |
| `execution_linked_to_intent` | `G(ToolCall ∨ Release ∨ Deploy → intent_resolved)` | R | 1–4 |
| `within_constraint_scope` | `G(action → within_constraint_scope)` | R | 2–4 |
| `policy_reference_current` | `G(action → policy_current)` | R | 2–4 |

### 3. Capability & DCE (`safety`)
| Policy | Formula | RAG | Tier |
| --- | --- | --- | --- |
| `tool_calls_allowlisted` | `G(ToolCall → in_allowlist)` | R | 2–4 |
| `consequential_action_approved` | `G(Release ∨ Deploy → P(UserApproval ∧ authenticated))` | R | 2–4 |
| `dual_approval_critical` | `G(Release → P(UserApproval ∧ approver_1) ∧ P(UserApproval ∧ approver_2))` | R | 4 |
| `default_deny_confirmed` | `G(ToolCall → P(default_deny_confirmed))` | R | 4 |

### 4. Runtime Telemetry & Trajectory (`auditability`)
| Policy | Formula | RAG | Tier |
| --- | --- | --- | --- |
| `telemetry_spans_complete` | `∀ s ∈ telemetry . s.status = recorded` | R | 2–4 |
| `no_guard_violation` | `G(¬guard_violation)` | R | 2–4 |
| `trajectory_within_bound` | `count(action) ≤ 50` | R | 2–4 |
| `tool_call_budget` | `count(ToolCall) ≤ 20` | A | 2–4 |
| `no_prohibited_transition` | `G(¬prohibited_transition)` | R | 3–4 |

### 5. Approval & Release Gating (`workflow`)
| Policy | Formula | RAG | Tier |
| --- | --- | --- | --- |
| `no_release_without_authenticated_approval` | `G(Release ∨ Deploy → P(UserApproval ∧ authenticated ∧ approval_scope_covers))` | R | 2–4 |
| `decision_path_reconstructable` | `G(Release ∨ Deploy → decision_path_present)` | A | 2–4 |

### Capability failure modes — Szpruch C1–C3 (`reasoning`)
| Policy | Capability | Formula | RAG |
| --- | --- | --- | --- |
| `retrieved_data_attributed` | C1 Retrieval & Attribution | `G(Retrieve → provenance_checked ∧ recency_checked)` | R |
| `numeric_recomputed_deterministically` | C2 Deterministic Numeric Computation | `G(Compute → deterministic_recompute)` | R |
| `outputs_policy_constrained` | C3 Policy-Constrained Drafting | `G(Draft → template_compliant)` | R |

(C4 Gated Release & Dispatch is `no_release_without_authenticated_approval`.)

## GovernanceState aggregation

The proposal's decision priority ordering (§6.3) collapses to severity +
first-match over the pack:

- **RED** — any `error`-severity policy fails (hard identity/transition/guard/
  approval/constraint failure). `ponens trace check` exits non-zero.
- **AMBER** — no Red, but one or more `warning`-severity policies fail
  (near-miss, credential expiry approaching, decision path not yet attributed).
- **GREEN** — every policy passes.

RED and AMBER are never collapsed: an Amber trace still carries a complete pass
set for human resolution; a Red trace names the failed `error` policies (the
`GovernanceFlags` the FIX field would carry).

## Tier profiles

Each policy is tagged `tier-<range>`. A deployment selects the subset for its
governance tier (Szpruch four-tier model):

| Tier | Profile |
| --- | --- |
| 1 Assistive | identity + intent + C1/C3 (Amber-tolerant) |
| 2 Bounded Workflow | + capability allowlist, approval gate, telemetry, release gating |
| 3 High-Impact Governed | + prohibited-transition, policy-as-code |
| 4 Critical Autonomous | full set incl. `dual_approval_critical`, `default_deny_confirmed` (Red enforced as a hard block) |

## Language extension

This pack motivated one new operator in the ponens policy language, the
**aggregate** `count(φ) <op> N` — the number of trace positions at which `φ`
holds — used by `trajectory_within_bound` (Lmax guard) and `tool_call_budget`.
It is implemented in both evaluators (CLI + browser playground) and covered by
the cross-evaluator parity harness.

## Out of scope (proposal Gap 5)

Per-trace policies cannot characterise **population-level / emergent** behaviour.
The proposal itself flags these as Gap 5 / future work, and they are deliberately
excluded here:

- **Orchestration drift** — a trajectory-population pattern, not a per-run
  violation.
- **End-to-end market-disorder contribution testing** for compound agentic
  workflows — cross-workflow, requires the AlgoReferenceData compound-algo
  extension and methodology beyond field/policy definitions.

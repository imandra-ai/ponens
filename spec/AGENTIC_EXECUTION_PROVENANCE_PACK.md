# Agentic Execution Provenance — ponens Policy Pack

This pack answers the FIX AI Working Group's **six discussion points** — the process
failures that are *invisible in the execution record*. Where the
[Agentic AI Runtime Governance pack](AGENTIC_GOVERNANCE_PACK.md) governs whether an
action is **authorised** (identity, approval, allowlist, constraint), this pack
governs whether the **decision path is reconstructable**: the *why*, the *what-else*
(rejected alternatives), and the *what-if* (what a later change invalidated).

**FIX records the execution (the "what"); a ponens trace records the decision path.**
Attach/reference the trace from the FIX message and you carry the reasoning provenance
FIX structurally cannot.

**Sources**
- FIX AI Working Group, *Six Points for Discussion — Agentic AI Runtime Governance*
  (R. Healey & K. Houston, 2026) — the six process-failure modes.
- Companion: [`AGENTIC_GOVERNANCE_PACK.md`](AGENTIC_GOVERNANCE_PACK.md) (the runtime
  traffic-light governance this pack sits alongside).

## Two ways a trace establishes a fact

A ponens policy returns a deterministic verdict, but *how strongly* a fact is
established depends on what the trace carries:

- **Attestation** — a per-action predicate the runtime *emits* and the policy checks
  is present (`recency_checked`, `intent_resolved`, `agent_id_resolved`, …). It proves
  *the agent declared it did X* — enforceable and gate-able at runtime, but only as
  trustworthy as the emitter.
- **Structural** — a property *derived from the trace itself*: lineage
  (`data_flow_integrity` — every input has a producer), append-only goal changes,
  the actions DAG, timestamps. It proves *the trace itself exhibits X*, independent of
  any declaration.

Both are first-class and both gate. The honest engineering statement is: **most of the
six are attestation today; three become structural with small, additive schema
extensions** (§ Extensions). This pack marks each point accordingly.

## The six points

`error` ⇒ **Red** (halt / containment); `warning` ⇒ **Amber** (flag / refer). Worked
pass/fail traces are in [`examples/fix_ai_wg/`](../examples/fix_ai_wg/) — run
`ponens trace check <file> --json`.

| # | Process failure | Governing policy | RAG | Established by |
| --- | --- | --- | --- | --- |
| 1 | Latency-induced stale decisions | `retrieved_data_attributed` | R | attestation → **structural** † |
| 2 | Tool failures during execution | `tool_calls_allowlisted` (+ failure/fallback as actions) | R | attestation + structural lineage |
| 3 | Memory contamination | `data_flow_integrity` | R | **structural** (extendable) † |
| 4 | Dynamic objective changes | `execution_linked_to_intent` (+ goals / meta-actions) | R | attestation + structural goal-change |
| 5 | Multi-agent responsibility | `agent_identity_resolved` (+ `consequential_action_approved`) | R | attestation → **structural** † |
| 6 | Missing reasoning provenance | `decision_path_reconstructable` (+ actions DAG / residuals) | A | **structural** (DAG) + attestation anchor |

† needs an additive extension to become fully structural — see below.

### 1 · Latency-induced stale decisions
The market snapshot a decision consumed is a typed artifact with a timestamp; the
decision and order-emission actions carry their own. The latency Δ is then visible
directly from lineage (`order derived_from → snapshot`). **Today:**
`retrieved_data_attributed` — `G(Retrieve → provenance_checked ∧ recency_checked)` —
attests recency. **Structural (extension):** with a timestamp convention (§E3), "the
data was already stale at execution" becomes a *computed* stale-evidence residual — a
decision whose input artifact was superseded before it acted — plus a policy "no order
on a snapshot older than N ms." (Same shape as the stale-evidence machinery already in
the trace model.)
Traces: `case1_stale_decisions_{pass,fail}.json`.

### 2 · Tool failures during execution
A failed tool call is still an **action**: ponens records the invocation and its outcome
(`result_summary: error/timeout`), because atomic actions are the ground-truth record —
successes and failures alike. The fallback is the next action, joined by rationale and
lineage; the unverified fallback is a `limitation`/`unverified` residual. `tool_calls_allowlisted`
gates the invocation. This is **substantially structural already** (the failure→fallback
edge is lineage); the allowlist membership is a runtime fact.
Traces: `case2_tool_failures_{pass,fail}.json`.

### 3 · Memory contamination
`data_flow_integrity` is **already structural** — every input an action relies on must
have a producer in this trace, so a dangling/foreign input is caught. **Extension (§E2):**
a first-class **Memory/Context artifact type** carrying `origin_workflow` upgrades this
from "no producer" to "producer's origin ≠ current goal" — catching *stale/biased reuse
across workflows*, not just missing lineage. Staleness/bias of the memory itself remains
a declared `assumption` residual.
Traces: `case3_memory_contamination_{pass,fail}.json`.

### 4 · Dynamic objective changes
This is the **goals + meta-actions** model. The objective (VWAP) is a goal / top-level
meta-action; switching to Implementation Shortfall is an **append-only** objective change —
both objectives *and* the transition are recorded, never overwritten. The *why*
("volatility increased") is the rationale on the switch action plus the volatility
evidence artifact it consumed. The old acceptance items go superseded (a residual); the
new goal takes over. `execution_linked_to_intent` attests each execution resolves to the
*current* IntentID. **Structural already** via append-only goal-change; intent linkage is
the attestation anchor.
Traces: `case4_objective_change_{pass,fail}.json`.

### 5 · Multi-agent responsibility
The goal → steps → tool-calls hierarchy is **meta-actions** (`parent_id` nesting);
delegation is a delegate-action producing a sub-task the sub-agent's actions reference;
supervisor sign-off is an approval action + `consequential_action_approved`. `agent_identity_resolved`
attests each step is credentialed. **Extension (§E1):** ponens is single-assistant per
trace *today* — a per-action **actor/role** field makes "agent A retrieved, B evaluated
risk, supervisor C approved" *structurally* attributable, upgrading the attestation to a
verifiable delegation DAG.
Traces: `case5_multi_agent_{pass,fail}.json`.

### 6 · Missing reasoning provenance
ponens's home turf. The decision path **is** the actions DAG; intermediate evidence is
the artifacts consumed/produced; the *why* is each action's rationale. Rejected
alternatives are first-class: candidate plans/venue analyses are artifacts, the rejection
is an action with rationale, and "dropped on an assumption" is a residual. `decision_path_reconstructable`
attests a DecisionPathID anchor. **Structural** — the branch structure, including paths
not taken, is the trace.
Traces: `case6_reasoning_provenance_{pass,fail}.json`.

## Extensions (attestation → structural)

Three small, **additive** schema conventions upgrade the marked points from "the agent
declared it" to "the trace proves it." None is a redesign; each rides the existing
lineage/goal machinery.

- **E1 · Per-action actor/role.** Add `actor` (and optional `role`) to the action record.
  Turns `agent_identity_resolved` and the multi-agent hierarchy from attested to
  attributable, and lets `consequential_action_approved` check *the approver differs from
  the executor*. (Point 5.)
- **E2 · Memory/Context artifact type + provenance.** A `Memory`/`Context` artifact with
  `origin_workflow` / `produced_by` fields. Turns `data_flow_integrity` into a
  cross-workflow-contamination check (`origin ≠ current goal`). (Point 3.)
- **E3 · Timestamp convention + staleness policy.** Distinguish **data-time**
  (artifact timestamp), **decision-time** (action timestamp), **execution-time** (order
  emission). Enables a *computed* staleness residual and a "no order on data older than
  N ms" policy. (Point 1; also sharpens 4's superseded-evidence handling.)

## Relationship to the runtime-governance pack

| | Agentic Runtime Governance | Agentic Execution Provenance (this pack) |
| --- | --- | --- |
| Question | *Is this action authorised right now?* | *Can we reconstruct why / what-else / what-if?* |
| Focus | identity, approval, allowlist, constraint, telemetry | latency, tool-failure, memory, objective, actor, decision path |
| Placement | runtime gate (pre-dispatch, Red = block) | audit + gate; several points enforce inline too |

Run both: governance answers *may it act*, provenance answers *and can we account for it*.

## Out of scope

Same population-level boundary as the runtime pack (FIX AI WG Gap 5): per-trace policies
cannot characterise emergent, cross-workflow / market-wide behaviour (orchestration drift,
compound market-disorder contribution). Those need the population/reference-data extensions,
not a per-trace formula.

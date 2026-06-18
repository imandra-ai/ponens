# IOSCO Supervisory Recordkeeping & Disclosure — ponens Policy Pack

This pack maps the **IOSCO Supervisory Toolkit for AI Use in Capital Markets**
(FR/02/2026, May 2026) onto computable ponens policies. Where the
[FIX Agentic AI Runtime Governance pack](./AGENTIC_GOVERNANCE_PACK) is
**preventive** — a runtime traffic-light that gates execution — this pack is
**evidentiary**: it checks that an AI system's decisions and outputs leave the
audit trail and disclosures a supervisor expects to review.

**Source:** IOSCO FR/02/2026, *Supervisory Toolkit for AI Use in Capital
Markets*, Chapter 3 — Tables 5 (Disclosure) and 6 (Recordkeeping & reporting).

## Why this maps onto ponens

The IOSCO toolkit is supervisor-facing: for each area it lists *potential
concerns*, *example questions*, and **"Supporting Evidence for Review"**. That
evidence column — "auditable recordkeeping for AI-driven decisions",
"traceability between AI outputs and final actions taken", "evidence of human
oversight or intervention", "incident logs with root-cause and remediation",
"records evidencing how clients are informed when AI is used" — *is exactly what
a ponens trace plus this pack produces.* ponens makes the evidence **computable**
rather than a manual document review.

| IOSCO toolkit | ponens |
| --- | --- |
| The records / logs / disclosures a firm must evidence | the **trace** |
| A "Supporting Evidence for Review" item | a **policy** (temporal formula) |
| Supervisor's pass/concern judgement | verdict **pass** / **warning-fail** / **error-fail** |
| Risk-based, proportionate expectations | pack **tier** tags |

### Relationship to the FIX pack

The two are designed to be used together:

| | FIX AI WG pack | IOSCO pack (this) |
| --- | --- | --- |
| Nature | **Preventive** runtime governance | **Evidentiary** recordkeeping & disclosure |
| Output | Green/Amber/Red `GovernanceState` | the audit trail a supervisor inspects |
| Emphasis | identity, intent, capability gating | logging, traceability, explainability, disclosure |

## Trace model

Governance facts appear in the trace as:

- **Action types** (added for this pack): `Decision`, `Output`, `Incident`
  (alongside existing `Release`, `Deploy`, `Draft`, …).
- **Per-action predicates** the firm's recordkeeping layer emits, matched against
  the action text: `logged`, `model_version_recorded`, `inventory_recorded`,
  `explainability_recorded`, `material_impact`, `human_reviewed`,
  `root_cause_recorded`, `remediation_recorded`, `reportable`,
  `supervisor_notified`, `client_facing`, `ai_disclosed`, `marked_ai_generated`,
  `ai_claim`, `claim_substantiated`, `ai_affects_client_rights`, `client_consent`.

Worked traces: [`examples/iosco_recordkeeping/governed.json`](../examples/iosco_recordkeeping/governed.json)
(all 11 Green) and [`violating.json`](../examples/iosco_recordkeeping/violating.json)
(8 Red + 2 Amber). Run `ponens trace check <file>`.

## The pack

`error` severity ⇒ **Red**; `warning` severity ⇒ **Amber**.

### Recordkeeping & Audit Trail (`auditability`) — IOSCO Table 6
| Policy | Formula | RAG |
| --- | --- | --- |
| `ai_outcomes_logged` | `G((Decision ∨ Output) → logged ∧ model_version_recorded)` | R |
| `output_action_traceable` | `G((Release ∨ Deploy) → P(Output ∧ logged))` | R |
| `decision_logic_recorded` | `G(Output → explainability_recorded)` | R |
| `human_oversight_evidenced` | `G(material_impact → human_reviewed)` | R |
| `incidents_root_caused` | `G(Incident → root_cause_recorded ∧ remediation_recorded)` | R |
| `reportable_incident_notified` | `G(Incident ∧ reportable → F(supervisor_notified))` | R |
| `ai_inventory_recorded` | `G((Decision ∨ Output) → inventory_recorded)` | A |

### Disclosure & Transparency (`communication`) — IOSCO Table 5
| Policy | Formula | RAG |
| --- | --- | --- |
| `ai_use_disclosed` | `G(Output ∧ client_facing → ai_disclosed)` | R |
| `ai_content_marked` | `G(Output ∧ client_facing → marked_ai_generated)` | A |
| `no_ai_washing` | `G(ai_claim → claim_substantiated)` | R |
| `consent_for_ai_decisions` | `G(ai_affects_client_rights → P(client_consent))` | A |

## Aggregation

`ponens trace check` aggregates the pack: any `error` fail ⇒ **Red** (non-zero
exit); else any `warning` fail ⇒ **Amber**; else **Green**. On the worked
violating trace this yields Red with 8 error and 2 warning findings — the precise
set of records/disclosures a supervisor would flag as missing.

## Out of scope

The toolkit's supervisor-side layers — Monitoring indicators (Table 7),
third-party/outsourcing concentration, and firm-level governance structures
(board oversight, training) — are organisational/population-level and not
per-trace checks, so they are not expressed here.

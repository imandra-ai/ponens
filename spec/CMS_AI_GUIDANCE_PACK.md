# CMS AI Guidance (TRA) — ponens Policy Pack

This pack maps the **CMS Technical Reference Architecture AI Guidance** onto
computable ponens policies. Where the [NIST AI RMF](./NIST_AI_RMF_PACK) is the
generic risk lifecycle, CMS is the **operational enforcement layer** — concrete
business rules and operational-security practices for using AI responsibly with
sensitive federal healthcare data.

**Source:** CMS TRA, *Artificial Intelligence Guidance* (business rules
BR-AI-1..6; references OMB M-25-21/M-25-22, NIST AI RMF, HHS AI policy).
<https://www.cms.gov/tra/Foundation/FD_0080_Foundation_AI_Guidance.htm>

## Why this maps onto ponens

CMS publishes six enforceable **business rules** plus operational practices that
map directly to policies over an AI system's operation record. It is notably
self-describing for ponens: CMS mandates tracking **"traces, EVALs, prompt
management/versioning, and key metrics"** — exactly the governance-semantic
telemetry ponens evaluates, so this pack is close to a literal implementation of
the guidance.

It is distinct from the lifecycle frameworks by being *operational and
enforceable*: high-impact use-case tiering (the OMB M-25-21 definition),
PHI/sensitive-data gating, **data residency / foreign-AI on-prem only**, AI
supply-chain provenance, zero-trust for AI, and records retention.

| CMS AI Guidance | ponens |
| --- | --- |
| The AI system's operation record | the **trace** |
| A business rule (BR-AI-n) / practice | a **policy** (temporal formula) |
| Mandatory rule vs recommended practice | `error` (Red) / `warning` (Amber) |

## Trace model

Reuses existing vocabulary — `Plan`, `Decision`, `Deploy`, `Output`, `EditFile`
(no new action types). Predicates include `high_impact_ai`,
`high_impact_decision`, `risk_assessment_done`, `human_final_decision`,
`documented_oversight`, `human_oversight`, `ai_written_policy`, `human_review`,
`sensitive_data_use`, `approved_tool`, `foreign_ai`, `on_cms_infrastructure`,
`no_internet_egress`, `external_ai`, `data_use_agreement`, `nonprod_data`,
`synthetic_or_deidentified`, `ai_component`, `provenance_verified`,
`ai_outbound_capable`, `data_minimization`, `network_segmented`, `production_ai`,
`prompts_versioned`, `observability_enabled`, `ai_supported_action`,
`records_retained`.

Worked traces: [`examples/cms/governed.json`](../examples/cms/governed.json)
(13/13 Green) and [`violating.json`](../examples/cms/violating.json) (8 Red +
2 Amber). Run `ponens trace check <file>`.

## The pack

`error` ⇒ **Red**; `warning` ⇒ **Amber**.

### Use-Case Governance & Oversight — BR-AI-2/4/5 (`conformance`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `cms_high_impact_risk_assessed` | `G(high_impact_ai → P(risk_assessment_done))` | R |
| `cms_high_impact_human_final_decision` | `G(high_impact_decision → human_final_decision ∧ documented_oversight)` | R |
| `cms_ai_policy_human_review` | `G(ai_written_policy → human_review)` | A |
| `cms_continuous_human_oversight` | `G((Deploy ∨ Output) → P(human_oversight))` | R |

### Data Protection & Residency — BR-AI-1/3 (`security`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `cms_sensitive_data_compliant_tool` | `G(sensitive_data_use → approved_tool)` | R |
| `cms_data_residency` | `G(foreign_ai → on_cms_infrastructure ∧ no_internet_egress)` | R |
| `cms_external_ai_data_agreement` | `G(external_ai → P(data_use_agreement))` | A |
| `cms_privacy_preserving_nonprod` | `G(nonprod_data → synthetic_or_deidentified)` | A |

### Supply-Chain & Zero-Trust (`security`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `cms_ai_provenance_verified` | `G(ai_component → provenance_verified)` | R |
| `cms_zero_trust_for_ai` | `G(ai_outbound_capable → data_minimization ∧ network_segmented)` | R |

### Observability & Records — BR-AI-6 (`auditability`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `cms_production_observability` | `G((Deploy ∨ Output) → P(observability_enabled))` | A |
| `cms_prompts_versioned` | `G(production_ai → prompts_versioned)` | A |
| `cms_records_retention` | `G(ai_supported_action → records_retained)` | R |

## Aggregation

`ponens trace check` aggregates the pack: any `error` fail ⇒ **Red** (an
unassessed high-impact use case, AI making a high-impact final decision, sensitive
data on a non-compliant tool, foreign AI egressing data, unverified provenance, or
unretained AI-supported actions); else any `warning` fail ⇒ **Amber** (policy
review, external-AI agreement, privacy-preserving data, observability, prompt
versioning); else **Green**.

## Notes

CMS AI Guidance sits on top of the NIST AI RMF (which it references) and OMB
M-25-21/22 — it is the agency-level operational instantiation. It pairs with the
NIST AI RMF (lifecycle), SSDF (secure build), and FIX (runtime) packs: govern the
risk, build securely, operate under the agency rules, gate at runtime.

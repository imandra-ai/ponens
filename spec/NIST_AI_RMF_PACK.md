# NIST AI Risk Management Framework — ponens Policy Pack

This pack maps the **NIST AI Risk Management Framework (AI RMF 1.0)** — the
foundational, voluntary US framework for managing AI risk — onto computable
ponens policies. It is squarely on-mission for ponens (AI governance) and brings
a shape distinct from the financial-regulator packs: a **lifecycle risk-management
framework** rather than a runtime or conduct regime.

**Source:** NIST AI 100-1, *AI Risk Management Framework 1.0* (26 Jan 2023).
<https://www.nist.gov/itl/ai-risk-management-framework>

## Why this maps onto ponens

The AI RMF is organised around four functions, which become the pack's groups,
and seven trustworthiness characteristics, which land under MEASURE:

- **GOVERN** — risk-management policies, accountability, culture (cross-cutting).
- **MAP** — establish context, categorize the system, characterize impacts.
- **MEASURE** — evaluate the trustworthiness characteristics; track risks.
- **MANAGE** — prioritize, treat, respond to and recover from risks; third-party.

**Trustworthiness characteristics** (under MEASURE): valid & reliable · safe ·
secure & resilient · accountable & transparent · explainable & interpretable ·
privacy-enhanced · fair (harmful bias managed).

ponens turns the subcategories into policies over an AI system's lifecycle record
— making *voluntary* AI-RMF adoption **auditable rather than aspirational**.

| AI RMF | ponens |
| --- | --- |
| The AI system's lifecycle / governance record | the **trace** |
| A function's subcategory | a **policy** (temporal formula) |
| Core requirement vs supporting practice | `error` (Red) / `warning` (Amber) |

## Trace model

Reuses existing vocabulary — `Deploy`, `Decision`, `Output`, `Incident`,
`Plan`, `EditFile` (no new action types). Per-action predicates include
`risk_policy_in_place`, `accountable_role`, `legal_requirements_mapped`,
`context_established`, `system_categorized`, `impacts_characterized`,
`validity_reliability_measured`, `safety_measured`, `security_resilience_measured`,
`privacy_measured`, `transparency_measured`, `explainability_measured`,
`fairness_measured`, `bias_managed`, `tracked`, `risks_prioritized`,
`identified_risk`, `risk_treated`, `responded`, `recovered`, `third_party_ai`,
`thirdparty_risk_managed`.

Worked traces: [`examples/nist_ai_rmf/governed.json`](../examples/nist_ai_rmf/governed.json)
(15/15 Green) and [`violating.json`](../examples/nist_ai_rmf/violating.json)
(7 Red + 4 Amber — GOVERN satisfied, MAP/MEASURE/MANAGE largely missing). Run
`ponens trace check <file>`.

## The pack

`error` ⇒ **Red**; `warning` ⇒ **Amber**.

### GOVERN (`conformance`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `rmf_govern_policies_in_place` | `G((Deploy ∨ Decision) → P(risk_policy_in_place))` | R |
| `rmf_govern_accountability_assigned` | `G((Deploy ∨ Decision) → accountable_role)` | R |
| `rmf_govern_legal_requirements_mapped` | `G(Deploy → P(legal_requirements_mapped))` | A |

### MAP (`conformance`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `rmf_map_context_established` | `G(Deploy → P(context_established))` | R |
| `rmf_map_system_categorized` | `G(Deploy → P(system_categorized))` | R |
| `rmf_map_impacts_characterized` | `G(Deploy → P(impacts_characterized))` | R |

### MEASURE — Trustworthiness (`safety` / `security` / `auditability`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `rmf_measure_validity_safety` | `G(Deploy → P(validity_reliability_measured ∧ safety_measured))` | R |
| `rmf_measure_security_privacy` | `G(Deploy → P(security_resilience_measured ∧ privacy_measured))` | R |
| `rmf_measure_transparency_explainability` | `G(Deploy → P(transparency_measured ∧ explainability_measured))` | A |
| `rmf_measure_fairness_bias` | `G(Deploy → P(fairness_measured ∧ bias_managed))` | R |
| `rmf_measure_ongoing_tracking` | `G(Output → tracked)` | A |

### MANAGE (`workflow` / `auditability`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `rmf_manage_risks_prioritized` | `G(Deploy → P(risks_prioritized))` | R |
| `rmf_manage_risk_treated` | `G(identified_risk → P(risk_treated))` | R |
| `rmf_manage_incident_response` | `G(Incident → F(responded ∧ recovered))` | R |
| `rmf_manage_thirdparty_risks` | `G(third_party_ai → P(thirdparty_risk_managed))` | A |

## Aggregation

`ponens trace check` aggregates the pack: any `error` fail ⇒ **Red** (no risk
policies/accountability, unmapped impacts, unmeasured safety/fairness, an
unhandled incident); else any `warning` fail ⇒ **Amber** (legal mapping,
transparency/explainability measurement, ongoing tracking, third-party risk);
else **Green**.

## Notes

The AI RMF Playbook provides finer-grained subcategory actions, and the
Generative AI Profile (NIST AI 600-1) adds GenAI-specific risks; both could
extend this pack as further policies. This pack covers the AI RMF 1.0 core. It
pairs naturally with the agentic-runtime (FIX) and supervisory (IOSCO/ESMA) packs
— GOVERN/MAP/MEASURE/MANAGE is the lifecycle frame within which those operate.

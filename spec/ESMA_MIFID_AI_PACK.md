# MiFID II AI in Investment Services — ponens Policy Pack

This pack maps the **ESMA Public Statement on the use of Artificial Intelligence
(AI) in the provision of retail investment services** (ESMA35-335435667-5924,
30 May 2024) onto computable ponens policies. It is the **EU conduct lens**:
ESMA reads AI use through firms' existing **MiFID II** obligations — best
interest, suitability, transparency, risk management, and recordkeeping —
complementary to the [IOSCO](./IOSCO_SUPERVISORY_PACK) (global supervisory
evidence) and [FIX](./AGENTIC_GOVERNANCE_PACK) (agentic runtime) packs.

**Source:** ESMA Public Statement ESMA35-335435667-5924 (30 May 2024).

## Why this maps onto ponens

ESMA's throughline is that **"firms' decisions remain the responsibility of
management bodies, irrespective of whether those decisions are taken by people or
AI-based tools,"** and that AI must always serve **clients' best interest**. The
Statement does not create new AI rules; it states what MiFID II already requires
when AI is in the loop. Several of those requirements — the recordkeeping clause
(¶24) and the ex-ante / ex-post accuracy controls (¶16) in particular — read
almost directly as trace policies, so the mapping is tight rather than
interpretive.

| ESMA / MiFID II obligation | ponens |
| --- | --- |
| What a firm must do / record when AI assists a service | the **trace** |
| A specific MiFID II expectation | a **policy** (temporal formula) |
| Conduct breach vs. soft expectation | verdict **error-fail** (Red) / **warning-fail** (Amber) |

## Trace model

- **Action types** (added for this pack): `Recommendation`, `Distribution`
  (alongside `Decision`, `Output`, `Deploy`, …).
- **Per-action predicates** the firm's controls emit, matched against the action
  text: `client_interaction`, `client_facing`, `ai_disclosed`,
  `clear_fair_not_misleading`, `best_interest_assessed`, `suitability_assessed`,
  `target_market_aligned`, `accuracy_checked`, `ai_driven_information`,
  `post_review`, `tested`, `validated`, `data_representative`, `stress_tested`,
  `third_party_ai`, `due_diligence_done`, `client_information`, `staff_competent`,
  `logged`, `data_sources_recorded`, `algorithm_recorded`, `complaint`,
  `recorded`.

Worked traces: [`examples/esma_mifid_ai/governed.json`](../examples/esma_mifid_ai/governed.json)
(all 14 Green) and [`violating.json`](../examples/esma_mifid_ai/violating.json)
(9 Red + 4 Amber). Run `ponens trace check <file>`.

## The pack

`error` ⇒ **Red**; `warning` ⇒ **Amber**.

### Best Interest & Transparency (`communication` / `conformance`) — ¶7–9
| Policy | Formula | RAG |
| --- | --- | --- |
| `ai_use_disclosed_to_client` | `G(client_interaction → ai_disclosed)` | R |
| `ai_information_clear_fair` | `G(client_facing → clear_fair_not_misleading)` | A |
| `acts_in_client_best_interest` | `G(Recommendation → best_interest_assessed)` | R |

### Suitability & Conduct (`conformance`) — ¶20
| Policy | Formula | RAG |
| --- | --- | --- |
| `recommendation_suitable` | `G(Recommendation → suitability_assessed)` | R |
| `product_governance_aligned` | `G(Distribution → target_market_aligned)` | R |

### Accuracy Controls (`safety`) — ¶16
| Policy | Formula | RAG |
| --- | --- | --- |
| `ai_output_accuracy_controlled` (ex-ante) | `G(client_facing → P(accuracy_checked))` | R |
| `ai_information_monitored` (ex-post) | `G(ai_driven_information → post_review)` | A |

### Risk Management & Testing (`safety`) — ¶11–13, 21
| Policy | Formula | RAG |
| --- | --- | --- |
| `ai_tested_before_deployment` | `G(Deploy → P(tested ∧ validated))` | R |
| `training_data_representative` | `G(Deploy → data_representative)` | R |
| `ai_stress_tested` | `G(Deploy → stress_tested)` | A |

### Outsourcing & Competence (`workflow`) — ¶14–17
| Policy | Formula | RAG |
| --- | --- | --- |
| `outsourced_ai_due_diligence` | `G(third_party_ai → due_diligence_done)` | R |
| `staff_competent_for_ai` | `G(client_information → staff_competent)` | A |

### Record Keeping (`auditability`) — ¶23–24
| Policy | Formula | RAG |
| --- | --- | --- |
| `ai_records_maintained` | `G((Decision ∨ Output) → logged ∧ data_sources_recorded ∧ algorithm_recorded)` | R |
| `ai_complaints_recorded` | `G(complaint → recorded)` | A |

## Aggregation

`ponens trace check` aggregates the pack: any `error` fail ⇒ **Red** (non-zero
exit); else any `warning` fail ⇒ **Amber**; else **Green**. On the worked
violating trace this yields Red with 9 error findings (e.g. an undisclosed AI
interaction, an unsuitable recommendation, an untested deployment, missing AI
records) and 4 Amber.

## Out of scope

The firm-level MiFID II machinery the Statement also invokes — management-body
oversight and governance structures (¶10), and the broader EU digital framework
(AI Act, DORA) — is organisational rather than per-trace and is not expressed
here.

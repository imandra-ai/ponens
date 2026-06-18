# CERT C/C++ Secure Coding — ponens Policy Pack

This pack maps the **SEI CERT Coding Standards** (CERT C and CERT C++, from
Carnegie Mellon's Software Engineering Institute) onto computable ponens
policies. Unlike the category-based MISRA/JSF packs, CERT is built on a
**risk model**, and that risk-prioritized remediation process is what this pack
governs.

**Source:** SEI CERT C and CERT C++ Secure Coding Standards —
<https://wiki.sei.cmu.edu/confluence/display/seccode>

## Why this maps onto ponens (and why it's *not* a MISRA clone)

CERT's individual rules are checked by static analysis, so — as with MISRA and
JSF — ponens does not re-encode them. What is **distinctive** about CERT, and what
ponens governs here, is its **risk assessment and prioritized remediation**:

- Every guideline/finding is scored on three factors: **Severity** (low/medium/
  high), **Likelihood** (unlikely/probable/likely), and **Remediation Cost**
  (high/medium/low).
- These multiply to a **Priority** (1–27), which maps to a **Level**:
  **L1** (Priority 12–27), **L2** (6–9), **L3** (1–4).
- Remediation is **prioritized**: L1 first, and L1 must not ship open.
- CERT also splits normative **Rules** (a violation is a defect — fix or deviate)
  from advisory **Recommendations** (departures recorded).

This is a risk-*prioritized* process, not a category process — genuinely
different from MISRA's Mandatory/Required/Advisory and JSF's Shall/Will/Should.
The same methodology covers CERT C and CERT C++, so this is **one pack**, not two.

| CERT | ponens |
| --- | --- |
| The coding/security-analysis activity record | the **trace** |
| A risk/remediation obligation | a **policy** (temporal formula) |
| Rule violation / open L1 vs advisory departure | `error` (Red) / `warning` (Amber) |

## Trace model

- **Action types**: `Finding` (added), plus `StaticAnalysis`, `Deviation`,
  `GitCommit`, `Release`.
- **Per-action predicates**: `cert_rule_violation`,
  `cert_recommendation_departure`, `severity_assessed`, `likelihood_assessed`,
  `remediation_assessed`, `priority_assigned`, `level_l1`, `level_l2`, `open_l1`,
  `remediated`, `reviewed`, `recorded`, `deviation_approved`,
  `rationale_recorded`, `cert_ruleset`, `undecidable_violation`, `manual_review`,
  `conformance_summary`.

Worked traces: [`examples/cert/governed.json`](../examples/cert/governed.json)
(11/11 Green) and [`violating.json`](../examples/cert/violating.json) (6 Red +
3 Amber — including an assessed-but-unremediated L1 finding shipped at release).
Run `ponens trace check <file>`.

## The pack

`error` ⇒ **Red**; `warning` ⇒ **Amber**.

### Rules vs Recommendations (`security`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `cert_rule_violation_remediated` | `G(Finding ∧ cert_rule_violation → remediated ∨ deviation_approved)` | R |
| `cert_recommendation_departure_recorded` | `G(Finding ∧ cert_recommendation_departure → recorded)` | A |

### Risk Assessment (`security`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `cert_risk_assessed` | `G(Finding → severity_assessed ∧ likelihood_assessed ∧ remediation_assessed)` | R |
| `cert_priority_assigned` | `G(Finding → priority_assigned)` | R |

### Prioritized Remediation — L1/L2/L3 (`security`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `cert_l1_remediated` | `G(level_l1 → remediated)` | R |
| `cert_no_open_l1_at_release` | `G(Release → ¬open_l1)` | R |
| `cert_l2_reviewed` | `G(level_l2 → reviewed)` | A |

### Verification & Enforcement (`workflow`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `cert_static_analysis_before_commit` | `G(GitCommit → P(StaticAnalysis ∧ cert_ruleset))` | R |
| `cert_undecidable_manual_review` | `G(undecidable_violation → manual_review)` | A |

### Deviations & Records (`auditability`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `cert_deviation_documented` | `G(Deviation → rationale_recorded ∧ deviation_approved)` | R |
| `cert_conformance_recorded` | `G(Release → P(conformance_summary))` | R |

## Aggregation

`ponens trace check` aggregates the pack: any `error` fail ⇒ **Red** (an open L1
at release, an unremediated rule violation, a missing risk assessment, or no
conformance record); else any `warning` fail ⇒ **Amber** (recommendation
departures, L2 review, undecidable-rule review); else **Green**.

## Scope note

This is the one new standard from the Polyspace coding-rule catalogue that adds a
genuinely different model (risk-prioritized remediation). The other entries on
that page — ISO/IEC TS 17961, AUTOSAR C++14 (now folded into MISRA C++:2023), and
the MISRA version variants — are rulesets the existing MISRA/JSF compliance-process
packs already parameterize over, so they are intentionally not separate packs.
The 221+ individual CERT rules themselves are enforced by a CERT-checking static
analyzer; this pack governs the risk/remediation process around its results.

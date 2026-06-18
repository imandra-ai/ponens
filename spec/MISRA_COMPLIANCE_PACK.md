# MISRA C / C++ Compliance — ponens Policy Packs

These two packs (**MISRA C** and **MISRA C++**) map the **MISRA Compliance:2020**
framework onto computable ponens policies. They cover the *compliance process*,
not the individual coding rules.

**Source:** MISRA Compliance:2020 — *Achieving compliance with MISRA Coding
Guidelines* — applied to MISRA C:2012 and MISRA C++:2023.
<https://misra.org.uk/>

## Why this maps onto ponens (and what it deliberately doesn't)

MISRA's value is its 143+ **coding rules and directives** — but those are checked
by **static analysis of source code**, not by a trace, so ponens does **not**
re-encode them. What ponens governs is the **process** that MISRA Compliance:2020
requires *around* those checks. That process is well-defined and is exactly the
shape ponens evaluates:

- **Guideline categories** — *Mandatory* (no deviation), *Required* (deviation
  allowed via the formal procedure), *Advisory* (recorded), plus *Disapplied*
  via re-categorization.
- **Deviations** — a documented violation with approved rationale.
- **Four compliance artifacts** — Guidelines **Enforcement** Plan (GEP),
  Guidelines **Re-categorization** Plan (GRP), Guidelines **Compliance Summary**
  (GCS), and deviation records.

This is the natural division of labour for an AI coding agent: the **analyzer
finds rule violations**, and **ponens checks the agent followed the compliance
process** around them — turning the analyzer's output from advisory into
auditable.

| MISRA Compliance:2020 | ponens |
| --- | --- |
| The coding/CI activity record | the **trace** |
| A compliance-process obligation | a **policy** (temporal formula) |
| Mandatory / Required / Advisory handling | `error` (Red) / `warning` (Amber) verdicts |

## The two packs

`misra-c` (MISRA C:2012) and `misra-cpp` (MISRA C++:2023) share the *same*
compliance-process policies; they differ only in the ruleset they enforce
(`misra_c_ruleset` vs `misra_cpp_ruleset`) and the guidelines referenced. Both
C:2012 and C++:2023 use the Mandatory / Required / Advisory categorisation.

## Trace model

- **Action types** (added for these packs): `StaticAnalysis`, `Deviation`,
  `ComplianceSummary`, `Directive` (alongside `EditFile`, `GitCommit`).
- **Per-action predicates**: `misra_c_ruleset` / `misra_cpp_ruleset`,
  `enforcement_plan`, `mandatory_violation`, `required_violation`,
  `advisory_violation`, `deviation_approved`, `rationale_recorded`, `recorded`,
  `targets_mandatory`, `grp_documented`, `weakens_mandatory`,
  `undecidable_violation`, `manual_review`, `addressed_with_evidence`,
  `recategorization`.

Worked traces (per pack): `examples/misra/misra_c_{governed,violating}.json` and
`examples/misra/misra_cpp_{governed,violating}.json` — governed 12/12 Green,
violating 4 Red + 1 Amber. Run `ponens trace check <file>`.

## The policies (shared by both packs)

`error` ⇒ **Red**; `warning` ⇒ **Amber**.

### Analysis & Enforcement — GEP (`workflow`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `…_static_analysis_before_commit` | `G(GitCommit → P(StaticAnalysis ∧ {ruleset}))` | R |
| `…_enforcement_plan_defined` | `G(StaticAnalysis → enforcement_plan)` | A |

### Guideline Categories (`conformance`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `…_no_mandatory_violation` | `G(¬mandatory_violation)` | R |
| `…_required_violation_deviated` | `G(required_violation → P(deviation_approved))` | R |
| `…_advisory_violation_recorded` | `G(advisory_violation → recorded)` | A |

### Deviations (`auditability` / `conformance`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `…_deviation_documented` | `G(Deviation → rationale_recorded ∧ deviation_approved)` | R |
| `…_no_mandatory_deviation` | `G(Deviation → ¬targets_mandatory)` | R |

### Re-categorization — GRP (`conformance`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `…_recategorization_in_grp` | `G(recategorization → P(grp_documented))` | R |
| `…_mandatory_not_weakened` | `G(recategorization → ¬weakens_mandatory)` | R |

### Compliance Summary — GCS (`auditability`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `…_compliance_summary_produced` | `F(ComplianceSummary)` | R |
| `…_undecidable_manually_reviewed` | `G(undecidable_violation → manual_review)` | A |

### Directives (`conformance`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `…_directives_addressed` | `G(Directive → addressed_with_evidence)` | R |

(`…` is `misra_c` or `misra_cpp`.)

## Aggregation

`ponens trace check` aggregates a pack: any `error` fail ⇒ **Red** (a Mandatory
violation, an undeviated Required violation, a commit with no MISRA analysis, or
a missing Compliance Summary); else any `warning` fail ⇒ **Amber** (advisory
records, enforcement-plan coverage, undecidable-rule review); else **Green**.

## Out of scope

The 143+ individual MISRA rules and directives themselves — they are enforced by
a MISRA-checking static analyzer; this pack governs the compliance *process*
around that analyzer's results.

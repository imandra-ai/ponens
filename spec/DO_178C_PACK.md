# DO-178C Software Assurance — ponens Policy Pack

This pack maps the **RTCA DO-178C / EUROCAE ED-12C** airborne-software
certification objectives onto computable ponens policies. It is a different
domain from the financial-regulator packs, but an unusually good fit: DO-178C's
defining requirement is **bidirectional traceability** (system → high-level
requirements → low-level requirements → source code → tests), which ponens
expresses directly with its **`P_chain` lineage operator** over the software
life-cycle record treated as a trace.

**Source:** RTCA DO-178C / EUROCAE ED-12C — *Software Considerations in Airborne
Systems and Equipment Certification*, objectives per Annex A tables A-1 to A-10.

## Why this maps onto ponens

DO-178C assures software by **objectives**, organised in Annex A tables and
scaled by **Design Assurance Level** (A–E, by failure-condition severity: A=71
objectives, B=69, C=62, D=26, E=0). Two shapes of objective dominate, and both
are native ponens:

- **Traceability** (requirements → design → code → test, and back) → `P_chain`
  over the artifact `derived_from` lineage, e.g. `G(SourceCode → P_chain(LLR))`.
- **Process ordering / presence** (plans before development, PSAC agreed first,
  reviews done, coverage achieved, items baselined) → temporal `G`/`P`/`F`.

| DO-178C | ponens |
| --- | --- |
| The software life-cycle data + activities | the **trace** (actions + artifacts with lineage) |
| An Annex A objective | a **policy** (temporal / lineage formula) |
| Design Assurance Level (A–E) | a policy's **tier** |
| "with independence" objective | an **Amber** escalation |

## Trace model

- **Action types** (added for this pack): `Plan`, `SystemRequirement`, `HLR`,
  `LLR`, `SourceCode`, `Test`, `Change`, `ProblemReport`, `DerivedRequirement`,
  `CoverageAnalysis`, `AccomplishmentSummary`.
- **Artifacts** carry `derived_from` lineage (system → HLR → LLR → code/test),
  which is what `P_chain` walks for traceability.
- **Per-action predicates**: `plans_approved`, `standards_defined`,
  `psac_agreed`, `safety_assessed`, `reviewed`, `requirements_accurate`,
  `analyzed`, `independent_review`, `dal_a`, `requirements_based`,
  `coverage_achieved`, `baselined`, `change_approved`, `resolved`,
  `deferred_with_rationale`, `sqa_reviewed`.

Worked traces: [`examples/do178c/governed.json`](../examples/do178c/governed.json)
(all 19 Green; built with a real system→HLR→LLR→code→test artifact DAG) and
[`violating.json`](../examples/do178c/violating.json) (14 Red + 1 Amber; lineage
links removed). Run `ponens trace check <file>`.

## The pack (by Annex A process area)

`error` ⇒ **Red**; `warning` ⇒ **Amber**. `tier` = applicable DAL range.

### Planning — A-1 (`conformance`)
| Policy | Formula | DAL |
| --- | --- | --- |
| `plans_before_development` | `G((HLR ∨ LLR ∨ SourceCode) → P(plans_approved))` | A-D |
| `standards_defined` | `G(SourceCode → P(standards_defined))` | A-C |

### Development & Traceability — A-2 (`structural` / `safety`)
| Policy | Formula | DAL |
| --- | --- | --- |
| `hlr_trace_to_system` | `G(HLR → P_chain(SystemRequirement))` | A-D |
| `llr_trace_to_hlr` | `G(LLR → P_chain(HLR))` | A-D |
| `code_trace_to_llr` | `G(SourceCode → P_chain(LLR))` | A-D |
| `derived_requirements_to_safety` | `G(DerivedRequirement → P(safety_assessed))` | A-D |

### Verification — A-3/4/5 (`safety`)
| Policy | Formula | DAL |
| --- | --- | --- |
| `hlr_verified` | `G(HLR → reviewed ∧ requirements_accurate)` | A-D |
| `llr_verified` | `G(LLR → reviewed)` | A-C |
| `code_verified` | `G(SourceCode → reviewed ∨ analyzed)` | A-C |
| `verification_independent` | `G((HLR ∨ LLR ∨ SourceCode) ∧ dal_a → independent_review)` | A-B (Amber) |

### Testing & Coverage — A-6/7 (`safety` / `structural`)
| Policy | Formula | DAL |
| --- | --- | --- |
| `tests_requirements_based` | `G(Test → requirements_based)` | A-D |
| `test_traces_to_requirement` | `G(Test → P_chain(HLR))` | A-D |
| `structural_coverage_achieved` | `G(CoverageAnalysis → coverage_achieved)` | A-C |

### Configuration Management — A-8 (`auditability`)
| Policy | Formula | DAL |
| --- | --- | --- |
| `artifacts_baselined` | `G((HLR ∨ LLR ∨ SourceCode ∨ Test) → baselined)` | A-D |
| `changes_controlled` | `G(Change → P(change_approved))` | A-D |
| `problem_reports_closed` | `G(ProblemReport → F(resolved ∨ deferred_with_rationale))` | A-D (Amber) |

### Quality Assurance — A-9 (`auditability`)
| Policy | Formula | DAL |
| --- | --- | --- |
| `sqa_conformity` | `G((HLR ∨ LLR ∨ SourceCode) → sqa_reviewed)` | A-D |

### Certification Liaison — A-10 (`conformance`)
| Policy | Formula | DAL |
| --- | --- | --- |
| `psac_agreed` | `G((HLR ∨ LLR ∨ SourceCode) → P(psac_agreed))` | A-D |
| `accomplishment_summary` | `F(AccomplishmentSummary)` | A-D |

## Aggregation

`ponens trace check` aggregates the pack: any `error` fail ⇒ **Red** (a
certification gap — e.g. a missing traceability link, an unverified requirement,
an unbaselined item, or an absent Accomplishment Summary); else any `warning`
fail ⇒ **Amber** (independence, problem-report closure); else **Green**.

## Notes & out of scope

- The `P_chain` traceability policies are evaluated by the CLI over the artifact
  lineage; the browser playground abstains on lineage operators (its contract is
  "agree or abstain"), so they show as *needs the CLI* there.
- Structural coverage is shown as a single objective; the DAL-specific criterion
  (MC/DC at A, decision at B, statement at C) is the policy's intent, set per
  deployment.
- Objectives that are not evidenced per life-cycle artifact — tool qualification
  (DO-330) and the model/object-oriented/formal-methods supplements
  (DO-331/332/333) — sit outside this pack.

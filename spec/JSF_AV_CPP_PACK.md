# JSF Air Vehicle C++ (JSF++) — ponens Policy Pack

This pack maps the **JSF Air Vehicle C++ Coding Standards** ("JSF++") — developed
for the Lockheed Martin **F-35 Joint Strike Fighter**, with input from Bjarne
Stroustrup — onto computable ponens policies. Like the [MISRA packs](./MISRA_COMPLIANCE_PACK)
it governs the *compliance process*, not the individual coding rules; but JSF++
has a distinctive three-tier category scheme and a tiered deviation-approval
chain that make it a separate pack.

**Source:** JSF Air Vehicle C++ Coding Standards (Lockheed Martin, Doc.
2RDU00001 Rev C, Dec 2005) — <https://www.stroustrup.com/JSF-AV-rules.pdf>

## Why this maps onto ponens

JSF++'s 221 numbered rules (AV Rule 1…) are checked by static analysis of source,
so ponens does not re-encode them. What ponens governs is JSF++'s compliance
process, which is well-defined and distinctive:

**Rule categories (§4.2.1):**
- **Shall** — mandatory *and requires verification* (automatic or manual).
- **Will** — mandatory, no verification (e.g. naming conventions).
- **Should** — advisory recommendation; deviation allowed.

**Deviation-approval chain (AV Rules 4-7):**
- Break a **should** → approval of the **software engineering lead**.
- Break a **shall** or **will** → approval of the **engineering lead AND the
  software product manager** (dual approval).
- Each **shall** deviation → **documented in the file** that contains it.

**Safety-critical (SEAL 1) obligations:** run-time checking / defensive
programming (AV Rule 15); only DO-178B Level A certifiable libraries (AV Rule 16
— a direct link to the [DO-178C pack](./DO_178C_PACK)); no dead code (code not
traceable to a requirement).

| JSF++ | ponens |
| --- | --- |
| The coding/CI activity record | the **trace** |
| A compliance-process obligation | a **policy** (temporal formula) |
| Shall / Will (mandatory) vs Should (advisory) | `error` (Red) / `warning` (Amber) |

## Trace model

This pack reuses existing vocabulary (`StaticAnalysis`, `Deviation`, `GitCommit`,
`EditFile`) — no new action types. Per-action predicates: `should_deviation`,
`shall_deviation`, `will_deviation`, `eng_lead_approved`,
`product_manager_approved`, `documented_in_file`, `shall_violation`,
`will_violation`, `should_violation`, `deviation_approved`, `recorded`,
`shall_verified`, `jsf_ruleset`, `safety_critical`, `runtime_checking`,
`library_use`, `certified_library`, `dead_code`, `rationale_recorded`,
`approval_recorded`.

Worked traces: [`examples/jsf/governed.json`](../examples/jsf/governed.json)
(12/12 Green) and [`violating.json`](../examples/jsf/violating.json)
(9 Red + 2 Amber). Run `ponens trace check <file>`.

## The pack

`error` ⇒ **Red**; `warning` ⇒ **Amber**.

### Deviation Approval — AV 4-7 (`conformance` / `auditability`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `jsf_should_deviation_approved` | `G(should_deviation → eng_lead_approved)` | A |
| `jsf_shall_will_deviation_dual_approved` | `G((shall_deviation ∨ will_deviation) → eng_lead_approved ∧ product_manager_approved)` | R |
| `jsf_shall_deviation_documented` | `G(shall_deviation → documented_in_file)` | R |

### Shall / Will / Should (`conformance`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `jsf_shall_violation_deviated` | `G(shall_violation → P(deviation_approved))` | R |
| `jsf_will_violation_deviated` | `G(will_violation → P(deviation_approved))` | R |
| `jsf_should_violation_recorded` | `G(should_violation → recorded)` | A |

### Verification & Enforcement (`safety` / `workflow`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `jsf_shall_rules_verified` | `G(GitCommit → P(shall_verified))` | R |
| `jsf_static_analysis_before_commit` | `G(GitCommit → P(StaticAnalysis ∧ jsf_ruleset))` | R |

### Safety-Critical — SEAL 1 (`safety`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `jsf_runtime_checking_provided` | `G(safety_critical → runtime_checking)` | R |
| `jsf_certified_libraries_only` | `G(safety_critical ∧ library_use → certified_library)` | R |
| `jsf_no_dead_code` | `G(¬dead_code)` | R |

### Deviation Records (`auditability`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `jsf_deviation_record_maintained` | `G(Deviation → rationale_recorded ∧ approval_recorded)` | R |

## Aggregation

`ponens trace check` aggregates the pack: any `error` fail ⇒ **Red** (an
undeviated shall/will violation, a singly-approved shall deviation, uncertified
safety-critical libraries, or dead code); else any `warning` fail ⇒ **Amber**
(should-rule deviations and records); else **Green**.

## Relationship to other packs

JSF++ sits alongside the MISRA C/C++ packs (it even cross-references many MISRA
rules in its text) and links to DO-178C via AV Rule 16's certifiable-library
requirement — the same way a real F-35 software programme stacks these standards.
The 221 individual rules themselves are out of scope; they are enforced by a
JSF++-checking static analyzer, and this pack governs the compliance process
around that analyzer's results.

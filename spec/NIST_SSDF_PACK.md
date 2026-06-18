# NIST SSDF (Secure Software Development) — ponens Policy Pack

This pack maps the **NIST Secure Software Development Framework** (SSDF, SP
800-218) onto computable ponens policies. It is the **second NIST pack** (the
first being the [AI RMF](./NIST_AI_RMF_PACK)) and brings a distinct shape: a
**secure-SDLC practice framework** with a strong supply-chain-integrity emphasis.

**Source:** NIST SP 800-218, *Secure Software Development Framework (SSDF) v1.1*.
<https://csrc.nist.gov/Projects/ssdf>

## Why this maps onto ponens

The SSDF organises secure development into four practice groups, which become the
pack's groups:

- **PO — Prepare the Organization** — security requirements, roles, secure
  toolchains.
- **PS — Protect the Software** — release integrity (signing), provenance/SBOM,
  archival. *(The supply-chain-integrity piece no other pack covers.)*
- **PW — Produce Well-Secured Software** — threat modeling, security review/
  analysis/testing, secure defaults, no open vulnerabilities at release.
- **RV — Respond to Vulnerabilities** — ongoing analysis, assessment &
  remediation, root-cause analysis.

ponens turns the practices into policies over a development/release trace, making
SSDF adoption auditable. Distinct from CERT (a per-finding risk model) and MISRA/
JSF (coding-rule compliance): SSDF is the **SDLC-level** secure-development
process, including build/release integrity and vulnerability response.

| SSDF | ponens |
| --- | --- |
| The development / release activity record | the **trace** |
| An SSDF practice (PO/PS/PW/RV) | a **policy** (temporal formula) |
| Core practice vs supporting practice | `error` (Red) / `warning` (Amber) |

## Trace model

Reuses existing vocabulary — `Plan`, `GitCommit`, `Release`, `Finding`,
`EditFile` (no new action types). Per-action predicates:
`security_requirements_defined`, `security_roles_defined`, `secure_toolchain`,
`artifact_signed`, `provenance_recorded`, `release_archived`, `threat_modeled`,
`security_review`, `static_analysis`, `security_tested`, `secure_defaults`,
`open_vulnerability`, `vuln_analysis`, `assessed`, `remediated`, `mitigated`,
`root_cause_recorded`.

Worked traces: [`examples/ssdf/governed.json`](../examples/ssdf/governed.json)
(14/14 Green) and [`violating.json`](../examples/ssdf/violating.json) (4 Red +
6 Amber — ships an open vulnerability with no provenance or security testing).
Run `ponens trace check <file>`.

## The pack

`error` ⇒ **Red**; `warning` ⇒ **Amber**.

### PO — Prepare the Organization (`conformance`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `ssdf_po_security_requirements_defined` | `G(GitCommit → P(security_requirements_defined))` | R |
| `ssdf_po_roles_defined` | `G(Release → P(security_roles_defined))` | A |
| `ssdf_po_toolchain_secured` | `G(GitCommit → P(secure_toolchain))` | A |

### PS — Protect the Software (`security`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `ssdf_ps_release_signed` | `G(Release → P(artifact_signed))` | R |
| `ssdf_ps_provenance_recorded` | `G(Release → P(provenance_recorded))` | R |
| `ssdf_ps_release_archived` | `G(Release → P(release_archived))` | A |

### PW — Produce Well-Secured Software (`security`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `ssdf_pw_threat_modeled` | `G(GitCommit → P(threat_modeled))` | R |
| `ssdf_pw_security_review` | `G(GitCommit → P(security_review ∨ static_analysis))` | R |
| `ssdf_pw_security_tested` | `G(Release → P(security_tested))` | R |
| `ssdf_pw_secure_defaults` | `G(Release → secure_defaults)` | A |
| `ssdf_pw_no_open_vuln_at_release` | `G(Release → ¬open_vulnerability)` | R |

### RV — Respond to Vulnerabilities (`security` / `auditability`)
| Policy | Formula | RAG |
| --- | --- | --- |
| `ssdf_rv_vulnerability_analysis` | `G(Release → P(vuln_analysis))` | A |
| `ssdf_rv_vulnerability_remediated` | `G(Finding → assessed ∧ (remediated ∨ mitigated))` | R |
| `ssdf_rv_root_cause_analysis` | `G(Finding → F(root_cause_recorded))` | A |

## Aggregation

`ponens trace check` aggregates the pack: any `error` fail ⇒ **Red** (an
unsigned/unprovenanced release, untested code, a shipped open vulnerability, or an
unremediated finding); else any `warning` fail ⇒ **Amber** (roles, toolchain,
archival, secure defaults, ongoing analysis, root cause); else **Green**.

## Notes

SSDF SP 800-218A extends these practices to generative-AI and dual-use foundation
models; it could be a companion profile in this pack. SSDF pairs with the CERT
pack (per-finding risk) and the agentic-runtime pack — together they cover an AI
coding agent's secure-development lifecycle from organization prep to vulnerability
response.

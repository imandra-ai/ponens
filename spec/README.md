# Ponens Specifications

The open standards behind ponens. Each spec is versioned **independently** — the trace format is
the stable contract that emitters and consumers depend on, so it carries a mature `1.x` version;
the companion specifications are still-evolving drafts (`0.x`) maturing toward `1.0`. This index
pins the current set.

## The specs

| Spec | Version | Status | What it defines |
|---|---|---|---|
| [`TRACE_SPEC_v1_6.md`](TRACE_SPEC_v1_6.md) | **1.6** | Draft | **The core.** The typed reasoning-trace format — actions, **meta-actions** (§8.4), artifacts & lineage (§7), the **residual surface** (§13), reproducibility (§12). Everything else is a companion over this. |
| [`POLICY_SPEC_v0_2.md`](POLICY_SPEC_v0_2.md) | 0.2 | Draft | **Computable Governance.** The policy object model and the temporal/structural DSL (LTL over finite traces + lineage/residual/field predicates) evaluated over a trace. |
| [`POLICY_LANGUAGE_v0_2.md`](POLICY_LANGUAGE_v0_2.md) | 0.2 | Draft | **Operator reference** (reader-friendly companion to `POLICY_SPEC` §9–13). The full operator set — future/past/scoped-past LTLf, boolean connectives, atomic propositions, structural predicates, quantifiers — trace semantics, and the `language_level` fragments. |
| [`REVIEW_CASE_SPEC_v0_2.md`](REVIEW_CASE_SPEC_v0_2.md) | 0.2 | Draft | The reviewer-side object — comments, review items, dispositions, and the verdict over a trace (or a chain). |
| [`TRACE_POLICY_REVIEWCASE_SEMANTICS_v0_2.md`](TRACE_POLICY_REVIEWCASE_SEMANTICS_v0_2.md) | 0.2 | Draft | The semantics tying the three together — how policy satisfaction is interpreted over a trace and its review-case context. |
| [`REVIEW_HANDOFF_v0_1.md`](REVIEW_HANDOFF_v0_1.md) | 0.1 | Draft | The protocol by which a reviewing agent (or human) consumes a trace — triage the residual surface, re-verify claims, hunt undeclared gaps. |
| [`CLI_SYNC_MODEL_v0_1.md`](CLI_SYNC_MODEL_v0_1.md) | 0.1 | Draft | How the CLI syncs a trace: local file ↔ git commit (1:1 binding, git notes) ↔ a hub backend. |
| [`POLICY_SOURCES_v0_1.md`](POLICY_SOURCES_v0_1.md) | 0.1 | Draft | The multi-source policy registry — the community gallery, local sources, and corporate/hub packs, with qualified ids and provenance. |

Also here: [`schema/`](schema/) — JSON Schemas derived from the trace spec (§16, "Interchange
Projection"); [`iml-model/`](iml-model/) — the IML / ImandraX formal model.

## How they relate

```
                 TRACE_SPEC  (the foundation — the typed record)
                   │
     ┌─────────────┼──────────────┐
     ▼             ▼              ▼
 POLICY_SPEC   REVIEW_CASE   (companions over the trace)
     └──────┬──────┘
            ▼
   …_REVIEWCASE_SEMANTICS  (how policy satisfaction reads over the three)

 REVIEW_HANDOFF      — the protocol for consuming a trace in review
 CLI_SYNC_MODEL      — how traces move (file ↔ git ↔ hub)
 POLICY_SOURCES      — where policies come from
```

## Conventions

Every spec opens with a header block:

- **Typed specifications** (Trace, Policy, Review-Case): `Version` · `Status` · `Format` · `Positioning`.
- **Semantics / explainer notes**: `Version` · `Status` · `Purpose`.

Versions are bumped per spec; **changes are additive and backward-compatible** unless a major
version says otherwise (e.g. Trace 1.5 → 1.6 added meta-actions; 1.x traces stay valid).

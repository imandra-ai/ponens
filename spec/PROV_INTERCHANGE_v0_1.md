# PROV Interchange Profile

## Header

**Version:** 0.1
**Status:** Draft
**Purpose:** Define how a ponens trace projects onto **W3C PROV** so it interoperates with the
provenance-tooling ecosystem. This is a lossy *interchange* view — the trace ([`TRACE_SPEC_v1_12.md`](TRACE_SPEC_v1_12.md))
remains the semantic source of truth; PROV is an export target. Implemented by `ponens trace export
--to prov` (PROV-JSON) and `ponens/prov.py`.

---

## 1. Why PROV

PROV is the W3C standard for provenance: `prov:Entity` / `prov:Activity` / `prov:Agent` plus a fixed
set of relations (`wasGeneratedBy`, `used`, `wasDerivedFrom`, …). A ponens trace's typed-artifact
lineage maps onto it almost 1:1, so exporting to PROV lets auditors and provenance tools consume a
trace in a vocabulary they already understand — chain-of-custody, derivation, attribution — without
learning the ponens format. See [`PRIOR_ART_ALIGNMENT_v0_1.md`](PRIOR_ART_ALIGNMENT_v0_1.md) §4 for
the fuller comparison.

The mapping is **faithful for lineage and attribution** and **lossy for everything PROV has no
vocabulary for** — residual kinds, defeaters, verification verdicts, freshness. Those ride as
`ponens:` attributes so a PROV consumer at least *sees* them, but their **semantics stay in ponens**
(§4). Do not round-trip through PROV expecting to recover the trace; export is one-way.

Namespaces: `prov: http://www.w3.org/ns/prov#`, `ponens: https://ponens.dev/ns#`.

---

## 2. Core mapping

| ponens | PROV | Notes |
|---|---|---|
| `artifact` | **`prov:Entity`** id `ponens:<artifact_id>` | `prov:type = ponens:<ArtifactType>`; `name`/`summary` → `prov:label`; `revision` → `ponens:revision` |
| `action` | **`prov:Activity`** id `ponens:act-<id>` | `prov:type = ponens:<category>/<type>` (e.g. `ponens:reasoning/Verify`); `label` → `prov:label` |
| `assistant` (+ `model`) | **`prov:Agent`** id `ponens:agent-<assistant>` | `prov:type = prov:SoftwareAgent`; `model` → `ponens:model` |
| the trace | **`prov:Entity`** `prov:type = prov:Bundle`, id `ponens:trace-<trace_id>` | provenance-of-provenance; `timestamp` → `prov:generatedAtTime`, `spec_version` → `ponens:spec_version` |

Relations:

| ponens edge | PROV relation |
|---|---|
| `artifact.producer_action_id` | **`wasGeneratedBy`** (`prov:entity` ← `prov:activity`) |
| `action.inputs[i]` | **`used`** (`prov:activity` → `prov:entity`) |
| `artifact.derived_from[i]` | **`wasDerivedFrom`** (`prov:generatedEntity` ← `prov:usedEntity`) |
| `artifact.supersedes` | **`wasDerivedFrom`** with `prov:type = prov:Revision` (i.e. `wasRevisionOf`) |
| every artifact | **`wasAttributedTo`** the agent |
| every action | **`wasAssociatedWith`** the agent |
| the trace bundle | **`wasAttributedTo`** the agent |

Edges whose endpoints aren't present in the trace (a dangling `derived_from`, an input that isn't a
declared artifact) are **dropped**, not emitted — the export is a well-formed PROV instance over the
artifacts/actions the trace actually contains.

---

## 3. Serialization

The current target is **PROV-JSON** (W3C Member Submission, 2013) — a JSON object with a `prefix` map
and one member per statement type (`entity`, `activity`, `agent`, `wasGeneratedBy`, `used`,
`wasDerivedFrom`, `wasAttributedTo`, `wasAssociatedWith`). Relation entries use synthetic `_:…` keys.
PROV-JSON is widely supported and round-trips through the reference PROV toolkits.

Future targets (same mapping, different encoding): **PROV-JSONLD** (2024 submission) and **PROV-O**
(RDF/Turtle) for the semantic-web ecosystem. Because §2 already speaks the PROV-O vocabulary, these
are re-encodings, not re-mappings.

---

## 4. What is NOT expressible in PROV (kept ponens-native)

PROV models *what was derived from what, by whom*. It has **no** vocabulary for:

- **Residuals / defeaters** — the residual `kind` (`assumption`/`unverified`/…/`defeater`),
  `defeater_kind`, `severity`, `status`, `source`. A `Residual` is exported as a `prov:Entity`
  (`prov:type = ponens:Residual`) with these carried as `ponens:` attributes and `wasDerivedFrom`
  edges to the artifact(s) it qualifies — but PROV assigns them no meaning. Counter-evidence blocking
  a claim (§18.2) is a ponens-side computation, invisible to PROV.
- **Verification verdicts** — proved / refuted / sat / unknown ride as `ponens:verdict` on the
  `VerificationResult` entity; to PROV it's an opaque entity.
- **Freshness** — `Fresh`/`Stale`/`Detached`/`Unknown` (TRACE §18.3, for any oracle's evidence) is derived by ponens; PROV's
  `wasInvalidatedBy` records an invalidation *event* someone asserts, not a computed staleness, so we
  do not emit it.
- **Policies / temporal-logic invariants** — PROV-CONSTRAINTS is a fixed consistency checker, not a
  policy language; policy evaluation stays entirely ponens-side.

The rule of thumb: **lineage and attribution round-trip; judgement does not.** Consumers that need the
judgement read the ponens trace.

---

## 5. CLI

```bash
ponens trace export <trace.json> --to prov [-o out.prov.json]
```

Emits the PROV-JSON document described above (default target `prov`). Pure projection — it never
mutates the trace.

---

## 6. References

- PROV-DM: `https://www.w3.org/TR/prov-dm/` · PROV-O: `https://www.w3.org/TR/prov-o/`
- PROV-JSON (2013 submission): `https://www.w3.org/Submission/2013/SUBM-prov-json-20130424/`
- PROV-JSONLD (2024 submission): `https://www.w3.org/submissions/2024/SUBM-prov-jsonld-20240825/`
- Alignment rationale: [`PRIOR_ART_ALIGNMENT_v0_1.md`](PRIOR_ART_ALIGNMENT_v0_1.md) §4 + Appendix A.

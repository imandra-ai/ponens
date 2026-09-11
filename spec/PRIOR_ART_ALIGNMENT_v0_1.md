# Prior-Art Alignment

## Header

**Version:** 0.1
**Status:** Draft
**Purpose:** Locate the ponens trace model against the closest existing systems — Why3 proof
sessions, W3C PROV, GSN/SACM assurance cases, and Lean Blueprint — dimension by dimension, so we
know what to borrow (vocabulary, mechanisms), what is genuinely novel here, and where terminology
should align with established standards.

---

## 1. Purpose

ponens maintains a **tree/DAG of typed artifacts** (source, formal model, verification goal/result,
diff, region-decomposition) linked by derivation edges, plus first-class **residuals** (open
obligations/assumptions with a lifecycle), **goals & acceptance** resolved from evidence, **policies**
(temporal-logic invariants over the trace), and **freshness** (an artifact goes stale when the code it
depends on changes). See [`TRACE_SPEC_v1_12.md`](TRACE_SPEC_v1_12.md) §7 (artifacts/lineage), §13
(residual surface), §18 (goals & acceptance), and [`POLICY_SPEC_v0_2.md`](POLICY_SPEC_v0_2.md).

That combination doesn't exist off-the-shelf. But each *part* of it has strong prior art, and this
note maps ponens onto the four nearest systems so the design borrows deliberately rather than
reinvents. Four comparison dimensions are used throughout:

1. **Typed-artifact lineage** — a DAG of typed objects with derivation edges.
2. **Residuals / obligations** — first-class open items (assumptions, unverified claims, defeaters)
   with severity, status, justification.
3. **Staleness / obsolescence** — detecting when a prior result no longer applies after a change.
4. **Change/versioning + policy** — how revisions are modeled, and whether rules can be checked over
   the whole structure.

---

## 2. The four systems at a glance

`●` full analogue · `◐` partial · `○` absent — rated against the ponens model.

| Dimension | Why3 sessions | W3C PROV | GSN / SACM | Lean Blueprint |
|---|---|---|---|---|
| 1. Typed-artifact lineage | ○ fixed proof tree | ◐ untyped entities + rich edges | ◐ argument structure + `ArtifactPackage` | ○ LaTeX-env DAG |
| 2. Residuals / obligations | ○ binary proved | ○ none | ● **best in class** | ◐ `\notready` boolean |
| 3. Staleness / obsolescence | ● **best in class** | ◐ invalidation *event* | ○ human-consulted metadata | ○ honor-system |
| 4. Versioning + policy | ◐ re-pairing; no policy | ◐ revision; fixed consistency checker | ◐ versioning; well-formedness | ○ neither |

**Headline.** Each system nails one or two dimensions; **none combines all four** — that is the
space ponens occupies. The nearest single *system* is Why3 (staleness); the nearest *vocabulary* is
PROV (lineage); the nearest *obligations model* is SACM / SEI Eliminative Argumentation (residuals);
temporal-logic **policy over the trace** has no counterpart in any of them.

---

## 3. Why3 proof sessions — the staleness model to copy

**What it is.** Why3's persistent record of interactive+automated proving: a tree
`file → theory → goal → (proof-attempt | transformation → subgoals)`, serialized as
`why3session.xml` (tree) + `why3shapes[.gz]` (fingerprints).

**Data model (real XML attributes).** `<goal>` carries `name`, `expl`, `sum` (task checksum),
`shape` (structural fingerprint), `proved`. `<transf name="split_vc">` holds the subgoals it
generated. `<proof prover=… obsolete=…>` holds a `<result status="valid|invalid|unknown|timeout|…">`.
Lineage is **structural containment only** (a subgoal is an XML child of the `<transf>` that produced
it); there is no `derived_from` edge and the source `.mlw` is not a node.

**Staleness — the part worth mirroring.** Two per-goal fingerprints of the proof *task* (the VC, after
transformations): `sum` (strong checksum, exact-identity) and `shape` (weak structural hash, fuzzy).
On reload, current goals are re-paired against stored goals (`Termcode.Pairing.associate`), yielding a
**trichotomy**:

- **exact checksum match →** keep the proof (fresh);
- **shape-only (inexact) match →** carry the proof over but set `obsolete=true` (ponens "stale");
- **no match →** the old proof becomes a **`detached`** node — proof work whose target disappeared.

Prover **version** change also forces `obsolete`. `why3 replay --obsolete-only` re-runs just the stale
attempts and clears `obsolete` when results reproduce.

| ponens concept | Why3 | Gap |
|---|---|---|
| typed-artifact DAG | fixed 5-level tree; `<transf>` ≈ a region/decomposition node | no source/diff/result *nodes*; no general DAG |
| `derived_from` | XML containment | source→VC provenance not recorded |
| residuals (severity/status/waiver) | boolean `proved`; `unknown`/`timeout` | none |
| policies | — | none |
| **freshness on change** | **`sum` + `shape` pairing → keep / obsolete / detached; version obsoletes** | keyed on the **VC/task**, not raw source hash |

**Borrow:** (a) fingerprint the **VC/task**, not the raw source function — robust to no-op edits
(comments/format) that change a source hash but not the goal; (b) the **keep/obsolete/detached
trichotomy**, including a **detached** residual state ponens lacks (a proof whose symbol was *deleted*,
not just edited); (c) **engine/model-version** as an obsolescence trigger; (d) a `replay
--obsolete-only` operation.

**Sources.** `src/session/termcode.mli` (the `Pairing.associate` contract — the staleness model in
one screen); `src/session/session_itp.ml` (`merge_proof`: `obsolete = goal_obsolete || old_pa.proof_obsolete`;
detached nodes); `share/why3session.dtd`; Why3 manual §5; Bobot et al., *Lightweight Interactive
Proving inside an Automatic Program Verifier* (arXiv 1811.10814).

---

## 4. W3C PROV — the lineage vocabulary to export to

**What it is.** The W3C standard for provenance: `prov:Entity` / `prov:Activity` / `prov:Agent` and a
fixed set of relations. Serializations: PROV-N (text), PROV-O (OWL/RDF), PROV-JSON / PROV-JSONLD.

**Mapping — near 1:1 with ponens lineage:**

| ponens | PROV (PROV-DM → PROV-O) |
|---|---|
| artifact | `prov:Entity` (typed via `prov:type`; PROV entities are otherwise untyped) |
| action (`producer_action_id`) | `prov:Activity`, reached by `prov:wasGeneratedBy` (artifact→action) + `prov:used` (action→inputs); reify as `prov:qualifiedGeneration`/`prov:Generation` to carry the action id, `prov:hadRole`, `prov:atTime` |
| `derived_from` | **`prov:wasDerivedFrom`** (direct) |
| `supersedes` / `revision` | **`prov:wasRevisionOf`** (a `wasDerivedFrom` subtype; carries no diff payload) |
| agent / tool | `prov:wasAttributedTo` (entity→agent), `prov:wasAssociatedWith` (activity→agent), `prov:actedOnBehalfOf` (sub-agent delegation) |
| the trace itself | **`prov:Bundle`** (itself an Entity → provenance-of-provenance: who ran the session, when) |
| action→action dependency | `prov:wasInformedBy` |
| freshness event | `prov:wasInvalidatedBy` (see below) |

**Staleness (partial).** `prov:wasInvalidatedBy` records an entity ceasing to be valid — one of its
four causes is *attribute change*. But it is a **recorded historical event tied to an activity/time**,
not a derived/propagated condition: PROV neither computes nor propagates staleness from a hash change,
and has no fresh→stale→refreshed status flip (re-freshening is a *new* entity). ponens's freshness
rule lives **outside** PROV; PROV can only record the resulting invalidation event.

**Residuals / policy — absent.** PROV has **no** obligation/assumption vocabulary (no severity,
status, justification). PROV-CONSTRAINTS is a **closed consistency checker** (event ordering, typing
disjointness) — explicitly *not* a policy language and with *no* temporal-logic-over-the-trace. ponens
policies have no PROV counterpart; you'd layer SHACL/SPARQL on the RDF and still not get temporal
semantics.

**Borrow:** publish a **PROV-O interchange profile** (Appendix A) so ponens traces export into the
provenance-tooling ecosystem — while keeping the typed model, residuals, freshness, and policies as
ponens-native semantics that ride as PROV attributes/types.

**Sources.** PROV-DM (`/TR/prov-dm/` §2 overview, §5 component definitions), PROV-O (`/TR/prov-o/` §3
qualified-relation pattern), PROV-CONSTRAINTS (`/TR/prov-constraints/` §5), PROV-JSONLD submission
(2024).

---

## 5. GSN / SACM assurance cases — the obligations model to learn from

**What it is.** Structured safety/assurance arguments. **GSN** (Goal Structuring Notation, SCSC-141C
Community Standard v3): `Goal`, `Strategy`, `Solution` (evidence), `Context`, `Assumption`,
`Justification`, linked by `SupportedBy` / `InContextOf`. **SACM** (OMG Structured Assurance Case
Metamodel): the formal MOF/XMI metamodel — `ArgumentPackage` (`Claim`, `ArgumentReasoning`,
`AssertedInference`, `AssertedEvidence`) + `ArtifactPackage` (`Artifact`, `ArtifactAsset`).

**Where it is ahead of ponens — two things:**

1. **Defeaters / counter-evidence.** SACM's `isCounter` flag and GSN v3's **Dialectic** extension
   model *arguments against* a claim (Pollock's taxonomy: **rebutting** — the claim may be false;
   **undermining** — the evidence is invalid; **undercutting** — the inference rule is deficient).
   ponens residuals are all *missing positive space*; there is no first-class "here is evidence this
   claim is **wrong**." SACM `assertionDeclaration` — `asserted / needsSupport / assumed / axiomatic /
   defeated / asCited` — is the closest typed analogue to `residual_status`, and adds `assumed`,
   `axiomatic`, `defeated` as states worth folding in.
2. **A completeness measure + terminology.** SEI **Eliminative Argumentation**: confidence = doubts
   eliminated, written **`m|n`** (m of n eliminated → `n−m` **residual doubts**) — the literature's
   name for ponens negative space, alongside **"assurance deficit."** **Assurance Claim Points**
   (ACPs, "a named black rectangle on the relevant link") attach confidence to a *specific* edge.

| ponens | GSN / SACM | Gap |
|---|---|---|
| artifact lineage | SACM `ArtifactPackage` + traceability | lineage is *argument structure*, not artifact derivation |
| residual kind/status | GSN `Assumption`/`Justification`, `Undeveloped`/`Uninstantiated`; SACM `assertionDeclaration`, `isCounter`; EA residual doubts | no automated freshness; no lifecycle beyond dialectic |
| verification verdict | — | no first-class verifier verdict (needed a bespoke *Isabelle/SACM* extension) |
| freshness | `Artifact.version`/`date` + `Event` log | **human-consulted only**; machine freshness only in research prototypes (Dynamic/Living Assurance Cases, AdvoCATE, OntoGSN) |
| policy | argument well-formedness / SACM validation | no temporal-logic-over-trace |

**Borrow:** (a) add **counter-evidence / defeaters** to the residual model (a `Defeater` variant or an
`isCounter` flag with rebut/undermine/undercut kinds) — a genuine expressive gap; (b) align
terminology ("assurance deficit," "residual doubt," the `assertionDeclaration` states) so ponens is
legible to the assurance-case and audit audience.

**Sources.** GSN Community Standard v3 (SCSC-141C); OMG SACM spec; Hawkins & Kelly, *Assured Safety
Arguments* (SSS 2011 — "confidence argument," "assurance deficit"); CMU/SEI-2015-TR-005 (Eliminative
Argumentation); *Isabelle/SACM* (arXiv 2009.12154).

---

## 6. Lean Blueprint — the readiness-propagation analogue

**What it is.** Patrick Massot's `leanblueprint` (a plasTeX plugin): LaTeX statements/proofs annotated
with a few macros, compiled to an HTML "web" + a color-coded **dependency graph**.

**Model.** Nodes are math environments (definition/lemma/theorem). Macros: `\lean{decl}` (names the
Lean declaration — annotation only, unverified), `\leanok` (statement *or* proof formalized,
context-sensitive), `\uses{labels}` (**the only edge-builder**), `\proves{label}` (attach a detached
proof), `\notready` (blocked). Two dependency *layers*: statement-level vs proof-level `\uses`.

**Readiness propagation — the ponens goal-gap analogue.** Computed over the `\uses` DAG:
`can_state = all(dep.leanok for dep in used) and not notready` (ready to formalize the *statement*);
`can_prove` = same but including the proof's own `\uses` (ready to formalize the *proof*);
`fully_proved = all(n.proved or n is definition for n in ancestors(node) ∪ {node})` (the **transitive**
"everything below is done"). Rendered as border-color (statement track) + fill-color (proof track).

| ponens | Blueprint | Gap |
|---|---|---|
| goal resolution / relevance cone | `can_state`/`can_prove` propagation over `\uses` | derived from **honor-system** flags, not verdicts |
| residuals | `\notready` boolean | lossy: no status/severity/justification/waiver |
| verification verdict | `\leanok` (binary) | no verdict spectrum; `sorry`/`admit` invisible |
| freshness | external `checkdecls` (name existence) | no semantic drift/staleness; no timestamps |
| typed lineage | `\lean` name annotation | no typed artifacts |

**Borrow:** (a) the **statement-track vs proof-track** split (a claim can be *stated* but not *proved*,
and readiness differs) — a useful refinement of acceptance resolution; (b) **transitive `fully_proved`**
(a goal is done iff its whole ancestor closure is) as a rollup over the relevance cone; (c) the
**color-coded dependency-graph** as the UX pattern for rendering the relevance-cone / open-gap view.

**Sources.** `leanblueprint/Packages/blueprint.py` (the status logic); `plastexdepgraph`; live graphs
(PFR, sphere-eversion); Tao's PFR blueprint tour (2023).

---

## 7. Per-dimension synthesis

- **Lineage → PROV** for vocabulary/interop; ponens's *typed* variants are strictly richer than PROV's
  untyped entities. Why3/Blueprint/GSN model structure, not artifact derivation.
- **Residuals → SACM + SEI EA.** ponens's lifecycle (open→acknowledged→addressed→waived, shrinking
  across a `Supersedes` chain) is more operational than any of them, but **defeaters/counter-evidence**
  is a real gap to close, and the terminology should align.
- **Staleness → Why3.** The mature model; ponens should adopt VC-fingerprinting + the
  keep/obsolete/detached trichotomy + version-triggered obsolescence. PROV's `wasInvalidatedBy` is only
  an event record; GSN/Blueprint have effectively nothing.
- **Policy → nobody.** Temporal-logic invariants over the trace are unique to ponens. Do not look for
  prior art; treat it as the differentiator.

---

## 8. Where ponens is uniquely ahead

- **Typed formal-engine verdicts** as first-class artifacts (proved/refuted/sat/unknown +
  counterexample) — PROV sees an opaque entity; SACM needed a bespoke extension to get this at all.
- **Residual lifecycle** shrinking across an append-only successor chain — more operational than
  SACM's static `metaClaim` or EA's manual `m|n`.
- **Grounded goal resolution** — acceptance items resolve *deterministically from evidence* with a
  derived relevance cone; Blueprint derives readiness but from honor-system flags.
- **The combination.** No existing system unifies typed lineage + residual lifecycle + automated
  freshness + temporal policy. That is the moat.

---

## 9. Recommendations (ranked)

1. **Adopt Why3-style staleness.** Fingerprint the **VC/task** (checksum + structural shape), not the
   raw source hash; implement the **keep / obsolete / detached** trichotomy, add a **`detached`**
   residual state for orphaned proofs, and treat **engine/model-version** change as an obsolescence
   trigger. Highest value, directly implementable against TRACE §18.3 (stale evidence).
2. **Add counter-evidence / defeaters** to the residual model (SACM `isCounter`; EA
   rebut/undermine/undercut) — a first-class "evidence *against* a claim," distinct from a missing-gap
   residual. Cheap: a new `residual_kind` or a `Defeater` variant in TRACE §13.
3. **Publish a PROV-O interchange profile** (Appendix A) — export/round-trip without changing the core.
4. **Align terminology** with the assurance-case literature ("assurance deficit," "residual doubt,"
   `assertionDeclaration` states) so ponens is legible to auditors and the safety-case community.
5. **UX:** render the relevance cone / open gaps as a Blueprint-style color-coded dependency graph;
   consider the statement-vs-proof track split for acceptance resolution.

---

## Appendix A — PROV-O interchange mapping (draft)

The trace exports as a `prov:Bundle`. Per element:

| ponens field / object | PROV-O |
|---|---|
| `artifact` | `prov:Entity`, `prov:type = "<artifact_type>"` |
| `artifact.derived_from[i]` | `prov:wasDerivedFrom` |
| `artifact.supersedes` | `prov:wasRevisionOf` |
| `artifact.producer_action_id` | `prov:wasGeneratedBy` → the `prov:Activity`; reified `prov:qualifiedGeneration` carries id/role/time |
| `action` | `prov:Activity` (`prov:startedAtTime`/`endedAtTime` from execution metadata) |
| `action.inputs[i]` | `prov:used` |
| `assistant` / `model` / tool | `prov:Agent`; `prov:wasAssociatedWith` (action), `prov:wasAttributedTo` (artifact), `prov:actedOnBehalfOf` (sub-agent → orchestrator/user) |
| stale event (freshness) | `prov:wasInvalidatedBy` + ponens-native attrs (`reason`, `old_hash`, `new_hash`) — semantics remain in the ponens engine |
| `Residual` artifact | `prov:Entity`, `prov:type = "Residual"`; `derived_from` → what it qualifies. All residual semantics (kind/severity/status/defeater) are ponens attributes, opaque to PROV |
| trace record | `prov:Bundle` (provenance-of-provenance: who/when produced the trace) |

Not expressible in PROV (kept ponens-native): residual lifecycle & defeaters, verification verdicts,
reactive/propagated freshness, temporal-logic policies.

---

## References

- **Why3:** manual §5; `termcode.mli`, `session_itp.ml`, `why3session.dtd`; Bobot et al., arXiv 1811.10814.
- **W3C PROV:** PROV-DM `https://www.w3.org/TR/prov-dm/`; PROV-O `https://www.w3.org/TR/prov-o/`;
  PROV-CONSTRAINTS `https://www.w3.org/TR/prov-constraints/`; PROV-JSONLD (2024 submission).
- **GSN/SACM:** GSN Community Standard v3 (SCSC-141C); OMG SACM; Hawkins & Kelly, *Assured Safety
  Arguments* (SSS 2011); CMU/SEI-2015-TR-005 (Eliminative Argumentation); Isabelle/SACM (arXiv 2009.12154).
- **Lean Blueprint:** `github.com/PatrickMassot/leanblueprint` (`Packages/blueprint.py`),
  `plastexdepgraph`; PFR / sphere-eversion blueprints.

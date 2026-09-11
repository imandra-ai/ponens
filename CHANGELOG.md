# Changelog

All notable changes to the `ponens` CLI. The format is based on
[Keep a Changelog](https://keepachangelog.com/); the project uses semantic versioning.

This file is the single source for release news: the matching section becomes the GitHub release
notes, and the website's **/whats-new** page renders this file directly. Keep a
`## [x.y.z]` heading per version, with `### Added` / `### Changed` / `### Fixed` subsections.

## [1.12.0] — 2026-09-11

The package moves `1.11.0` → `1.12.0` to track the trace spec, which advances to **1.12**; the oracle
spec advances to **0.2** (`TRACE_SPEC_v1_11.md` is now `TRACE_SPEC_v1_12.md`; `ORACLE_SPEC_v0_1.md` is
now `ORACLE_SPEC_v0_2.md`). Every change is additive: 1.4–1.11 traces stay valid and unchanged. The
reference implementation implements both specs — `ORACLE_SPEC_v0_2.md` §11 is the conformance table.

### Added
- **Oracles are a generic type (`ORACLE_SPEC_v0_2`, Trace Spec 1.12).** An oracle is fixed by its
  contract, not its mechanism: a formal reasoner, a test runner, a static analyzer, **a database or
  reference-data store**, an LLM judge and a human sign-off are all oracles on equal footing. The
  `oracle_type` set is declared **open** (standard names are a classification; consumers warn on, never
  reject, an unknown name) and `monitor` joins the standard set. Every evidence payload MAY carry an
  **attribution block** `payload.oracle` (id, type, version, and the honest strength of *this* result).
  The reasoner-only `reasoning_fingerprint` is generalized to an **evidence fingerprint**
  (`subject_checksum` / `subject_ref` / `valid_until`), so derived freshness is defined for any
  oracle's evidence and gains an **`Unknown`** outcome; an optional **`probe`** operation re-reads a
  subject's fingerprint without re-running the oracle. A new **`Observation`** artifact (§10.11) is the
  typed landing place for a monitor's evidence. Policies gain `strength_at_least` / `oracle_type` /
  `produced_by`; goal resolution reports the weakest-link strength; merge prefers the stronger result.
- **Reference oracles across the spectrum.** `ReferenceDataOracle` — **a database as an oracle**: a
  mapping or a SQLite store (`from_sqlite`; `PONENS_REFERENCE_DB` registers one as `reference-data`)
  answering a query with an `Observation`, graded `attested`, fingerprinted on (source, query, value,
  as-of) and probe-able so it goes stale when the source republishes and detached when the subject is
  gone. Plus `SubprocessTesterOracle` (exit status is the verdict → `tests`), `CallableJudgeOracle`
  (`attested`) and `AttestorOracle` (a `UserApproval`). `ponens oracle list --type`, `ponens oracle probe`.
- **Graded, fresh-or-not resolution.** `ponens trace enrich` stamps each resolved item with its
  `evidence_strength` and `freshness` (`fresh` | `stale` | `detached` | `unknown`) and each goal with
  `min_strength` (the weakest link); any-oracle evidence with a fingerprint is checked by probing its
  oracle or by `valid_until`, and surfaces the same derived stale-/detached-evidence residuals a proof
  does. `ponens trace validate` warns on a non-standard `oracle_type`, errors on an invalid strength
  or an `Observation` graded above `attested`, and flags a strength on an unestablished result.
- **SDK.** `Session.verify` records the action by the oracle's mechanism (`Verify` / `Observe` / `Test`
  / `Analyze` / `Judge` / `Attest`), with `observe` / `test` / `judge` / `attest` aliases; `Session.probe`
  and `Session.freshness` re-read an artifact's subject via the oracle that produced it.

### Changed
- **The policy `reasoner` / `oracle` field is now enforced.** Previously declarative (nothing read it
  at check time), it desugars into the checked formula: `G(atom -> (produced_by(X) || oracle_type(X)))`
  over every evidence-bearing atom the formula mentions (the formal-reasoning result types when it
  mentions none). A policy declaring `reasoner: codelogician` therefore **fails** on a trace whose
  proofs came from another engine or carry no attribution — a verdict that was `passed` before. To keep
  the old behaviour, remove the field; to name the engine precisely, write `produced_by(...)` in the
  formula. `produced_by` matches the oracle id or the engine it drives (the catalog's
  `codelogician.engine = imandrax`), so the gallery's `codelogician` / `imandrax` policies both match a
  CodeLogician-over-ImandraX trace, including pre-1.12 payloads that carry only `engine`.
- **`ponens trace validate` checks oracle attribution.** An invalid `evidence_strength`, or an
  `Observation` graded above `attested`, is an error; a non-standard `oracle_type` (without
  `specializes`) and a strength stamped on an unestablished (`unknown` / `error`) result are warnings.
  Traces without attribution blocks are unaffected.
- Policy formulas: an identifier may now contain `-` when followed by an identifier character
  (`produced_by(calendar-db)`); `->` is still the arrow.

## [1.11.0] — 2026-08-26

The package jumps `1.9.1` → `1.11.0` to track the trace spec, which advanced two minor versions
(**1.10** trace composition, **1.11** signatures + composable acceptance) — there was no `1.10.0`
package release. `TRACE_SPEC_v1_9.md` is now `TRACE_SPEC_v1_11.md`; every change below is additive,
so existing 1.4–1.9 traces stay valid and unchanged.

### Added
- **Composable acceptance — the goal property language (`GOAL_CONTRACT_v0_2` §9, Trace Spec 1.11
  §18.1).** An `acceptance_item` MAY now carry a `formula` instead of a single criterion: `and` / `or` /
  `not` / `implies` over atoms, plus **`forall`** / **`exists`** quantified over *component selectors*
  (glob, module, scope, tag) — so "every handler in `payments/` is proved, and at least one has a
  conformance check" is one criterion, not a hand-maintained list. Each atom carries its own **`met`** /
  **`governed`** role, and resolution runs over a **4-valued status lattice** rather than a boolean. A
  legacy single-criterion goal is exactly the atomic case and desugars unchanged.
- **Trace composition — `ponens trace merge` (Trace Spec 1.10 §15.3).** Combines an *ours* and a
  *theirs* trace (optionally against a `--base` ancestor) and sorts every standing reasoning result into
  exactly one bucket, under a **totality** invariant: a **`CarriedForward`** artifact when the result is
  *provably unaffected* — its dependency closure is disjoint from the merge's change set, or every
  touched dependency was assumed `uninterpreted` — or a **`NeedsRereasoning`** residual when its closure
  or an assumed contract was disturbed. A **`CoverageRegression`** residual records a goal whose scope
  gained an unproven member. The merged trace records two-parent `merge_event` provenance; `--combine`
  emits that trace, the default emits a report projection and mutates neither input. The implementation
  is the sound-but-conservative realization of the proved IML model in `formal/` — anything not provably
  safe collapses onto re-reasoning, so a stale result is never reported fresh.
- **Durable component identity — `component_id` (Trace Spec 1.10 §7.1).** A code component keeps its
  identity across a rename or a move, so evidence-to-code binding — rooting, freshness, and the merge
  change set — survives refactoring instead of silently detaching. The resolver is tiered
  (producer-declared lineage → unique exact fingerprint → confident unique similarity) and **never
  guesses**: an ambiguous or weak signal mints a new id, because conflating two distinct components is
  the unsound error.
- **Oracles — `ponens oracle list` / `ponens oracle show` (`ORACLE_SPEC_v0_1`).** Generalizes *reasoner*
  to **oracle**: anything that produces evidence about a target and returns it as trace artifacts — a
  formal reasoner, a test runner, a static analyzer, an LLM-judge, or a human attestor. Two orthogonal
  classifiers travel with the evidence: `oracle_type` (the *mechanism* — reasoner | tester | analyzer |
  judge | attestor) and `evidence_strength` (the *guarantee* — proof > sat > tests > static_analysis >
  attested), so a reviewer can see **which oracle produced a claim and how strong that makes it**. A
  *reasoner* is now simply the formal, proof-producing subtype.
- **`ponens.sdk` — instrument an agent instead of reconstructing it (`SDK_SPEC_v0_1`).** A thin runtime
  SDK for agents that speak ponens natively: open a `Session`, record actions and artifacts as the work
  happens, invoke oracles for evidence, and on exit get a validated trace that passes `ponens trace
  check` — no transcript reconstruction step. It builds the same JSON-native trace the rest of the
  toolchain uses, so there is exactly one trace model and one code path for artifacts and lineage.
- **Integrity fields are now specified in the trace spec (1.11 §12.4, §5).** `content_hash` and
  `signatures` — shipped in 1.9.0 and previously defined only in `CLI_SYNC_MODEL` / `AUDIT_READINESS` —
  are now normative in the core spec, including the `HASH_EXCLUDE` set, the per-signature `role` /
  `disposition` / RFC-3161 `timestamp` fields, and the uniform `valid` | `untrusted` | `invalid` |
  `tampered` verdict.

### Changed
- **The package version jumps `1.9.1` → `1.11.0`** to track the trace spec, which advanced two minor
  versions in one go — **1.10** (trace composition) and **1.11** (signatures + composable acceptance).
  There is no `1.10.0` package release; everything from both spec versions ships here.
  `TRACE_SPEC_v1_9.md` is now `TRACE_SPEC_v1_11.md`.
- **`GOAL_CONTRACT` is now v0.2** (`GOAL_CONTRACT_v0_1.md` → `GOAL_CONTRACT_v0_2.md`), and
  `GOAL_FAITHFULNESS_v0_1` re-points at it. **If you link to the spec, update the URL** — the v0.1 path
  no longer resolves.
- **The IML / ImandraX formal models moved** from `spec/iml-model/` to **`formal/`** — the framework's
  invariant models plus the layered trace+policy model in `formal/trace-policy-model/`. The merge and
  component-identity models there are the conformance spec the Python implementations realize.

### Fixed
- **`verified_claims_are_fidelity_checked` no longer fires on spec-first sessions.** The formula is now
  guarded — `(F SourceCode) → G(Verify → F(ConformanceResult(passed)))` — so it applies only when there
  *is* source code to conform to. An authored-IML session, where the model is the artifact rather than a
  translation of something, passes vacuously instead of being flagged for a missing fidelity check.
- **Trace viewer:** the Steps / Actions pills now count within the **active scope**, so the numbers match
  the cards actually on screen, and each scope option's count is the actions it will really show. A
  detail panel can be closed (returning the flow to full width), a live same-session refresh keeps your
  zoom, pan, and manual DAG drags instead of resetting the layout, and the noise-only `completed` result
  line is no longer rendered on every action.

## [1.9.1] — 2026-08-09

### Fixed
- **Typed acceptance criteria now honor open defeaters (`goals.py::_resolve_typed`).** A typed criterion
  (`component` + `evidence: {artifact}`) previously resolved `done` as soon as a matching artifact
  existed, ignoring counter-evidence — so a criterion whose evidence (or the provenance it derives from)
  is contested by an OPEN `Defeater` still read as met. It now resolves `blocked`, matching the legacy
  property path (§13 / §18.2). In particular a **failing conformance** — whose `ConformanceResult`
  carries an undermines-defeater — correctly leaves a `conformance` criterion unmet instead of silently
  `done`.

## [1.9.0] — 2026-08-07

### Added
- **Cryptographic sign-off (`ponens trace sign` / `ponens trace verify`)** — non-repudiable,
  tamper-evident audit sign-off over a trace's `content_hash`, with pluggable backends: **SSH**
  (`ssh-keygen`, trusted via an allowed-signers roster), **GPG** (detached signatures, trusted via an
  allowed-fingerprints roster, with the public key inlined so verification is offline), and **keyless
  sigstore** (a short-lived Fulcio certificate binds the signature to an *OIDC identity*, and the proof
  is recorded in the **Rekor** public transparency log — no long-lived key to manage). An audit sign-off
  carries `--role`/`--disposition`; `verify` dispatches per signature and reports **valid** / **untrusted**
  / **invalid** / **tampered**, gating on failure (`--require-trusted`). Signatures live in `signatures[]`,
  excluded from `content_hash`, so parties co-sign the *same* content with whatever backend they trust.
- **RFC-3161 trusted timestamps.** `trace sign --tsa <url>` attaches a Time-Stamping Authority signature
  over the signature (a TSA-attested "existed by <time>"); `trace verify --tsa-ca <cert>` checks it
  **offline** against the TSA certificate — so *when* is attested, not machine-clock-asserted.
- **PROV interchange (`ponens trace export --to prov`).** Export a trace to **W3C PROV-JSON** (Entity /
  Activity / Agent + `wasGeneratedBy` / `used` / `wasDerivedFrom` / `wasAttributedTo`), so the record
  speaks a standard provenance vocabulary auditors and tools already read (`PROV_INTERCHANGE_v0_1.md`).
- **Evidence freshness — `Fresh` / `Stale` / `Detached` (Trace Spec §18.3).** A formal-reasoning result
  (a proof, a state-space decomposition, conformance, co-simulation) is only as current as the model it
  ran on. `enrich` / `residuals --derived` now derive a stale- or detached-evidence residual from a
  dependency-**closure** fingerprint of the target symbol — a change to anything the target transitively
  uses invalidates it, and removing the symbol detaches it — and a goal **never resolves `done` over
  non-fresh evidence**. Generic across result kinds, not verification-only.
- **First-class counter-evidence — `Defeater` residuals (Trace Spec §13 / §18.2).** `ponens trace
  residual add --kind defeater --defeater-kind rebuts|undermines|undercuts --target-id <result>` records
  evidence *against* a claim (a counterexample, a model that doesn't match the code, evidence that
  doesn't support it). An open defeater **blocks** the claim it targets — a contested `Property` reads
  `blocked`, not `done` — which is stronger than a mere declared gap.

### Changed
- **Freshness reasons per-symbol from the model's inline source.** The check reads the model the producer
  already inlines (`iml_code`, or the spec's canonical `formal_code`) and selects the current model **per
  target symbol**, so a multi-file session (one focused model per formalization run) no longer
  false-flags an earlier symbol's proof as `detached`. An explicit producer
  `reasoning_fingerprint.task_checksum` on a result is honored directly; absent it, the closure checksum
  is reconstructed from the model current at proof time.

## [1.8.0] — 2026-08-04

### Added
- **Content-addressed object store (`ponens objects`)** — an immutable, sha256-keyed blob store so a
  trace can reference large content (source, formal model, tests) by `content_ref` instead of inlining
  it: identical content is stored once (dedup) and a trace plus its reachable objects is a portable,
  self-contained bundle. Layout is a stable spec (`<dir>/sha256/<ab>/<rest>`, overridable via
  `$PONENS_OBJECTS_DIR`) so any producer that can hash may write blobs directly. New CLI:
  `ponens objects put | get | externalize | inline | gc | stat`. `ponens bind --externalize` moves
  inline blobs into the store at the share boundary; `objects inline` rehydrates a received bundle.
- **`ponens trace replay` — re-run a ReproductionBundle.** Materializes the content-addressed model
  from the object store and re-executes it through a pluggable **engine adapter** (`engines.py`, with an
  ImandraX adapter), flagging where the fresh verdict **diverges** from the recorded one. Dry by default
  (reports the plan + self-containment); `--run` executes the safe-allowlisted replay command and
  preflights the engine (binary on PATH, credentials present).
- **Revision-aware lineage (`supersedes` / `revision`).** Helpers for append-only revision chains:
  `current_artifacts` (fold history to the latest revision), `superseded_ids`, and `revision_chain`
  (walk a revision newest→oldest, cycle-safe). `trace validate` now warns on a dangling `supersedes`.

### Changed
- **`normalize_trace` surfaces failed/aborted attempts and resolves externalized blobs.** A
  `CommandResult` (carrying an `outcome`/`exit_code`) is mapped onto its action so policies can
  distinguish *attempted-and-failed* from *never-attempted*; externalized `content_ref` blobs are
  resolved back to inline content for policy evaluation on a bound trace.
- **Residual payload preserves `summary` / `property` / `counterexample`.** The plain-language lead, the
  formal property that was checked, and a counterexample input now survive residual processing
  (Trace Spec v1.8 §13), instead of being dropped by the residual-surface filter.

## [1.7.1] — 2026-07-29

### Added
- **`ponens policies lint` — validate policies without a trace** — lint a policy file locally
  (`ponens policies lint policies.json [--json]`): required fields, the severity/scope vocabularies,
  and formula syntax, using exactly the oracle `trace check` applies before evaluating — a policy that
  lints `valid` can never come back syntax-invalid at check time. Errors are structured
  (`{message, path}`, the path into the formula's operator tree), so authoring tools can surface them
  in place. With `--json` the exit code is 0 whenever linting ran and the per-policy verdicts are in
  the records (machine mode, mirroring `trace check --json`); without it, a human-readable report that
  exits 1 if anything is invalid. Accepts the same file shapes as `trace check --policy-file` (a JSON
  array, or `{"policies": [...]}`).

### Fixed
- **Stale-proof detection keys on the *latest* proof** — a symbol's proof is stale iff its latest
  proof predates the latest change to that symbol, so a property re-proved after an edit heals its
  stale-evidence residual instead of the superseded proof staying reported stale forever. A refutation
  surfaces as the live `blocked` issue it is, never as staleness. The at-risk guard now reads two
  independent signals: a change recorded on the trace (structural), and `artifact_freshness`
  re-hashing that catches an on-disk edit the trace has no Diff for.

## [1.7.0] — 2026-07-27

### Added
- **Residuals are first-class artifacts (Trace Spec v1.8)** — a residual (an assumption relied on, a
  claim left unverified, an out-of-scope item, a known limitation) is now an `artifact_type: "Residual"`
  anchored into the lineage DAG via `derived_from` / `target`, so the trace's *negative space* hangs off
  exactly the artifact it qualifies instead of floating in a separate list. The legacy top-level
  `residuals[]` is still read - and `migrate_residuals` folds an old trace forward - so existing traces
  keep working. See the new `TRACE_SPEC_v1_8` spec.
- **Residual-surface policies** — a policy can now quantify over the residual surface (e.g.
  `no_open_critical_residuals`): `enrich` evaluates it and reports its witnesses - the concrete residuals
  that satisfy or violate it - so a governed goal can require its gaps be *closed*, not merely that its
  evidence exists.

### Changed
- **Policy failures point at *where* they fail** — a structural policy evaluation now returns a witness
  record (`ev_actions` / `vi_actions` / `ev_artifacts` / `vi_artifacts`): the concrete action and
  artifact ids that support or violate it, instead of a bare pass/fail. A failed policy can name the
  exact steps or artifacts at fault.

### Fixed
- **`Decomposition` criteria now resolve against a real decomposition** — a goal criterion asking for
  `Decomposition` evidence matched nothing, because a region decomposition is recorded on the trace as
  `StateSpaceAnalysisResult`. Resolution now canonicalizes artifact-type spellings
  (Decomposition ≡ StateSpaceAnalysisResult ≡ Decomp), so a decomposition criterion ticks when the
  decomposition exists.
- **Criteria bind when the engine renamed the symbol** — a criterion's `component` may now carry both a
  source `function` (the author's name, for display) and a formal `symbol` (the name the engine gave the
  formalization, e.g. source `clamp` formalized as `clamp_decomp`), and resolves on *either*. A goal no
  longer stays *todo* just because the proof was recorded under the engine's symbol rather than the
  source name.

## [1.6.0] — 2026-07-25

### Added
- **Goal contracts** — an acceptance criterion is now *a required evidence artifact over a code
  component*: it names the `component` and the `evidence` artifact that must exist in its lineage
  (`{ "artifact": "VerificationResult" | "Decomp" | "Tests" | "Diff" | … }`). A goal also carries its
  own **policy bar**. State the goal as a contract - *accomplish these things, subject to these
  policies* - and `ponens trace enrich` returns three independent verdicts: **met** (each component has
  its evidence artifact), **governed** (the goal's policies held), and **certified** (a non-doer
  confirmed the criteria were the right ones). Author the whole contract in one shot with
  `ponens trace goal set --json`. See the new `GOAL_CONTRACT_v0_1` spec.
- **Met and governed are cleanly separated** — a criterion is *met* the moment its evidence artifact
  exists; **whether that evidence was derived correctly** (proved, autoformalized, tests pass, a proof
  required on a high-stakes path) is decided entirely by **policies**, the governed axis. One mechanism
  for rigor, no overlap. New pack policy `refuted_results_must_be_reproved` enforces that a verification
  result offered as evidence is actually proved, not left refuted.
- **Goal-scoped policies — the governed axis** — a goal can name policy `packs` and `policies`; they
  **block by default** unless explicitly `disabled` (recorded on the trace, never silent). Pack names
  resolve against the registry, and `enrich` attaches the governance result per goal.
- **Artifact lineage / provenance API** — a new dependency-free `ponens.lineage` module answers what a
  specific artifact was derived from: `ancestor_ids`, `lineage_types`, `source_symbols`, `autoformalized`,
  `decomposition_backed`, and a one-call `provenance` summary.

### Changed
- **`ponens agent`** now teaches the goal-contract workflow — evidence-artifact criteria, the goal's
  policy bar, and the three axes (met / governed / certified), including the rule that the agent
  *proposes* the rigor bar while a human *selects* it, and never self-certifies.
- **`ponens trace enrich`** now reports the **governed** axis alongside met and certified, and its
  summary counts `goals_governed`.
- **Evidence rigor moved from faithfulness grading to policy.** `faithfulness_of` no longer emits
  `weakly_specified` (and `certified` no longer depends on it) — "is a diff enough, or do you need a
  proof?" is now a policy question on the governed axis. `GOAL_FAITHFULNESS_v0_1` §6 is superseded.

### Fixed
- **Goals now reach *met* when the work is real** — a criterion resolves by artifact **lineage** (does
  an artifact of the required type root in this component?) instead of matching the verification goal's
  description text. This fixes goals that never ticked even though the evidence existed.
- **Lineage is component-precise** — an artifact that declares its own `target_symbol` (a VG, a Decomp,
  a targeted Diff) is about *that* component, so a decomposition of one function no longer looks like it
  roots in every symbol the shared model formalized.

## [1.5.0] — 2026-07-22

### Added
- **Goal authoring from the CLI** — a new `ponens trace goal` command group brings the desktop's goal
  workflow to the CLI, so every trace operation can be done from the command line: `set` (declare the
  intent + definition of done, or load one via `--json`), `accept` (add an acceptance item bound to
  evidence), `certify` (record a non-doer's sign-off — the *certified* axis), `drop` / `rm` (remove an
  item or a goal), and `ls` (show each goal's resolved status + met/certified/weakly-specified). Goals
  are written in the spec's snake_case shape.

### Fixed
- **PyPI project page** — the package now ships a README (`readme` in `pyproject.toml`), so the PyPI
  project page renders a description instead of "The author has not provided a project description."

## [1.4.1] — 2026-07-22

### Added
- **Faithfulness grading in `enrich`** — `ponens trace enrich` now grades each goal's *definition* of
  done (`GOAL_FAITHFULNESS_v0_1`), not just its progress: **met** (required criteria resolved from the
  trace's own evidence) vs **certified** (a reviewer other than the doer approved the criteria, every
  intent clause is covered, and the definition is not weakly specified), plus `weakly_specified` and
  `uncovered_clauses` per goal. The trace `summary` gains `goals_met` / `goals_certified` /
  `goals_weakly_specified` counts.
- **Faithfulness gate in `trace check`** — the checker reports each goal's met/certified status and,
  under `--strict`, fails on the deficiencies the agent controls: a weakly-specified definition
  (nothing proved or policy-checked backs "done") or an uncovered intent clause. "Met but not
  certified" is surfaced as a warning — certification needs a human, so it is never a hard failure.

## [1.4.0] — 2026-07-22

### Added
- **Goal faithfulness — met vs certified** — a goal's "done" is now graded on two orthogonal
  axes: *met* (its acceptance criteria resolved from the trace's own evidence) and *certified* (a
  reviewer other than the agent confirmed those were the *right* criteria). The new
  `GOAL_FAITHFULNESS_v0_1` spec (under `/spec`) refines Trace Spec §18 with authorship
  (`intent_author`, per-item `author`), clause coverage (`intent_clauses` + `covers`), and a
  `criteria_review`. It guards the principal–agent seam where the agent both *authors* and *meets* its
  own definition of done — an honest resolution can still "succeed" against a bar set too low.
- **Goals view in the visualizer** — `ponens trace view` now shows a trace's declared goals with their
  acceptance criteria and renders the faithfulness signals inline: *Met* / *Certified* badges, a
  weakly-specified warning (a goal backed only by code edits, with nothing proved or policy-checked),
  uncovered-intent-clause warnings, and the intent→criteria authorship seam. Each acceptance
  criterion's evidence chip is a link — click it to jump to the backing artifact in the lineage graph
  (or, for a policy obligation, the Policies view).

### Changed
- **Richer flagship demo** — the Stripe payment-flow trace is now the default demo: a declared goal
  with a certified definition of done, a seven-step meta-action narrative (formalize → catch the amount
  bug with a counterexample → fix → prove both new controls individually *and* together → conformance →
  ship), full lineage, and three honestly-declared residuals. The bundled `sample_payment_idempotency`
  trace also gained a declared goal, so the Goals view is populated out of the box.
- **Goal-oriented framing on the site** — the "not another tracing tool" comparison is reframed as
  *descriptive* (OpenTelemetry / Langfuse record what happened) vs *evaluative* (ponens judges each
  trace against its declared **goal** and its **policies**), and the header version badge now links to
  **/whats-new**.

### Fixed
- **Switching demos refreshes every view** — picking a different trace in the viewer's dropdown now
  re-renders the active tab against the new trace and hides tabs the new trace doesn't populate.
  Previously a pane could keep stale content from the previously-selected trace — e.g. the Goals tab
  still showing the last trace's goal.

## [1.3.0] — 2026-07-22

### Added
- **OpenTelemetry bridge** — `ponens otel import <otlp.json>` converts an OTLP-JSON span export into a
  ponens trace: spans → actions, parent-span tree → meta-actions, span start/end → action timestamps,
  and the `ponens.inputs/outputs` attribute convention → artifact lineage.
- **Langfuse bridge** — `ponens langfuse import <trace.json>` does the same for a Langfuse trace export
  (nested `SPAN` / `GENERATION` / `EVENT` observations).
- **`ponens demos`** — `list` and `get` bundled, checkable sample traces that ship with the CLI.
- **Machine-readable checks** — `ponens trace check --json` emits the `policy_evaluations` array;
  `--write` stamps it back into the trace file (self-describing traces).
- **Policy evidence** — evaluations now carry `evidence_action_ids` / `violating_action_ids` (plus the
  matching artifact ids); the visualizer renders these on each policy card.
- **Data-driven high-stakes surface** — the `high_stakes_path` predicate reads `trace.high_stakes_paths`
  (falling back to the demo defaults), so "where formal methods make sense" is decided by evidence.
- **Policy packs** — "Apply Formal Methods Where It Makes Sense", and the "Agentic Execution Provenance"
  spec mapping the FIX AI Working Group's six discussion points onto the trace model (with worked
  pass/fail example traces under `examples/fix_ai_wg/`).

### Fixed
- `make release` reads the version from `pyproject.toml` (no longer depends on `uv version --short`).
- `pyproject.toml` uses an SPDX `license = "MIT"` expression, removing the setuptools ≥77 deprecation
  warning on upload.

## [1.2.x] — 2026-07-21

### Added
- Artifact-DAG **node isolation** in the visualizer — click a node to isolate its connected lineage
  (upstreamed to `viewer/core`, so the CLI `ponens trace view` and the VS Code plugin both get it).

### Changed
- Packaging, license, and author-metadata fixes; version alignment across the desktop wrapper.

_Earlier releases predate this changelog — see the
[GitHub releases](https://github.com/imandra-ai/ponens/releases) for full history._

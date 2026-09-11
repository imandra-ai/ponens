# ORACLE_SPEC v0.2 - Oracles: the generic evidence producer

**Status:** draft · additive over TRACE_SPEC v1.12 · **Version:** 0.2 (supersedes 0.1)

> **Changes in 0.2.** Makes the oracle a **generic type**, fixed by its *contract* rather than its
> mechanism, and closes the gaps that kept it reasoner-shaped in practice:
> (1) the `oracle_type` set is declared **open** - the standard names are a classification, not an
> enumeration, and `monitor` (observational evidence: a **database or reference-data store**, a feed,
> telemetry) joins the standard set; (2) every evidence artifact carries an **attribution block**
> (`payload.oracle`) naming the oracle, its type, its version and the strength of *this* result;
> (3) the reasoner-only `reasoning_fingerprint` is generalized to an **evidence fingerprint** with a
> `subject_checksum`, so freshness is defined for *any* oracle's evidence - a proof goes stale when
> its dependency closure changes, a calendar lookup when the calendar is republished; (4) an optional
> `probe` operation lets a consumer re-check freshness without re-running the oracle; (5) a new
> **`Observation`** artifact type (TRACE_SPEC §10.11) is the typed landing place for a monitor's
> evidence; (6) policies gain strength / type / producer predicates and merge prefers the stronger
> result. All additive: 0.1 oracles and traces remain valid.

An **oracle** is an invocable producer of evidence about a target, returning that evidence as trace
artifacts. An oracle is **any** producer of evidence - emphatically not just a formal tool. A prover is
one kind of oracle. So is a test run, a static analysis, a **database queried for a fact**, a market-data
feed, a runtime monitor, an LLM's judgment, and a human sign-off. What unifies them is not the mechanism
but the contract: each answers a question about a target with evidence that lands in the trace as typed
artifacts, tagged with an **honest strength**, attributed to the oracle that produced it, and anchored by
a fingerprint of the subject it answered about. A *reasoner* is simply the formal, proof-producing
**subtype**.

This breadth is the point. It is what lets ponens govern the *full spectrum of how work actually gets
checked* - proof, tests, observation, judgment, attestation - under one trace, and what makes the
substrate tool- and prover-agnostic. Nothing in the trace, the SDK, a policy, or a goal is hard-wired to
one engine, or to formal engines at all.

---

## 1. Classification

Two orthogonal classifiers travel with every oracle and with every artifact it produces.

### 1.1 `oracle_type` - the mechanism

| `oracle_type` | What it is | Examples |
|---|---|---|
| `reasoner` | Formal engines - proof / decision procedures | ImandraX, Lean, Z3, a model checker |
| `tester`   | Dynamic execution - run it and observe | test runners, property-based testing, fuzzers, simulators, backtests |
| `analyzer` | Static inspection without execution | type checkers, SAST, linters, schema / contract checks; a database engine validating a constraint |
| `monitor`  | Observational evidence from a live system or external source | **a database or reference-data store queried for a fact**, production telemetry, runtime assertions, canaries; rate-fixing / calendar / rulebook-version / configuration lookups |
| `judge`    | Heuristic / probabilistic assessment | LLM-as-judge, rubric evaluators, model-graded eval |
| `attestor` | Human or external sign-off | a reviewer, a domain expert, an external certification, a regulator |

**The set is open.** The names above are the *standard classification* - what registries filter by,
what policies name, what a reviewer recognizes. They are **not a closed enumeration**:

- a consumer (`ponens trace check`, `validate`, `enrich`, a policy evaluator) **MUST accept** an
  `oracle_type` it does not recognize, treating it as an unclassified mechanism (it MAY warn; it MUST
  NOT reject the trace or discard the evidence);
- a producer SHOULD use a standard name when one fits and MAY register a finer one (`datasource`,
  `simulator`, `ledger`) when none does; the finer name SHOULD declare which standard name it
  specializes (`specializes: monitor`) so filters and policies that name the standard type still match;
- what is **not** open is the second classifier: whatever the mechanism is called, the evidence it emits
  is graded on the fixed strength order of §1.2. An unknown type with an honest strength is fine; a known
  type with an overstated strength is a violation.

**Classify by what the evidence is, not by what the tool is.** The same system can play several roles.
A database queried for the current settlement calendar is a `monitor` (its answer is an observation of
an external fact). A database engine enforcing a `CHECK` constraint over a schema is an `analyzer` (it
statically validates a structure). A database used as a fixture under a test run is part of a `tester`.
The oracle is the *evidence-producing role*, and one system may register as several oracles.

### 1.2 `evidence_strength` - the guarantee

A total order, strongest first. It is the *guarantee the output carries*, distinct from the mechanism
that produced it (a `reasoner` model checker may yield `sat`, not full `proof`; a `monitor` never yields
more than `attested`, however authoritative its source).

    proof  >  sat  >  tests  >  static_analysis  >  attested

- `proof` - a property holds over the entire (possibly unbounded) state space.
- `sat` - a model / witness was found, or a bounded check passed.
- `tests` - empirical evidence from executed cases (sampled, not exhaustive).
- `static_analysis` - sound-ish over-approximation without execution.
- `attested` - asserted by a source, a judge, or a human; not mechanically established. **An
  observation is `attested`**: its guarantee is that a named source stated it at a named time. There is
  deliberately no separate `observed` grade - the source's authority is *attribution* (§3), not strength.

`evidence_strength` is additive; evidence that omits it is unranked (sorts last). The order is
**locked** as of 0.2: it propagates into policies (§6), merge (§6), goal resolution and payloads.

### 1.3 Reasoner-agnostic, and oracle-agnostic

The `reasoner` subtype is deliberately plural: **ImandraX** (driven via `codelogician-lite`) is the
reference, shipped reasoner oracle, but **Lean**, **Z3**, and other provers / SMT / model checkers
register as `reasoner` oracles on equal footing. The same holds one level up: a reasoner is one
`oracle_type` among several, and a goal, a policy, or a merge treats a proof, a test run, an
observation and a sign-off uniformly - as evidence, attributed and graded.

- `verify(target, oracle=…)` selects any registered oracle by id; a policy may `require` a specific
  oracle (or a minimum `evidence_strength`, or an `oracle_type`); absent that, a configurable default
  applies.
- Every result records **which oracle** produced it (§3), so a claim is attributable and re-checkable by
  another party - potentially with a *different* oracle of the same type.

---

## 2. The oracle contract

An oracle exposes metadata and one required operation, plus one optional operation for freshness.

```
oracle := {
  id                : String,
  name              : String,
  oracle_type       : String,          # a standard name (§1.1) or a registered specialization
  specializes       : String?,         # the standard name a non-standard oracle_type refines
  evidence_strength : one of §1.2,     # the STRONGEST guarantee this oracle can produce
  produces          : [ArtifactType],  # the artifact types its evidence lands as
  version           : String?,         # the oracle's own version (engine build, schema version, model id)
  vendor            : String?,
  description       : String?,
}

invoke(target, context?) -> [artifact]           # REQUIRED - produce evidence about `target`
probe(subject_ref, context?) -> evidence_fingerprint?   # OPTIONAL - the CURRENT fingerprint of a subject,
                                                        # without producing new evidence (§4)
```

`invoke` returns zero or more artifact objects (TRACE_SPEC §7) **without** `artifact_id` or
`producer_action_id` - the caller (an SDK `Session`, a producer agent) assigns those, records the
invoking action, and wires `derived_from` lineage from the target. Each returned artifact MUST carry
the attribution block (§3) and SHOULD carry an evidence fingerprint (§4) in its payload.

`probe` answers *"what is the subject's fingerprint right now?"* for a subject the oracle previously
answered about - the current dependency-closure checksum of a symbol, the current row hash and as-of of
a calendar, the current version of a rulebook. It is cheap by design: it re-reads state, it does not
re-derive evidence. An oracle that cannot probe (a human attestor, a one-shot judge) omits it; freshness
for its evidence then falls back to time-boxing (`valid_until`) or is reported `unknown` (§4).

The action an oracle invocation is recorded under follows its type: `Verify` for a `reasoner`, `Test`
for a `tester`, `Analyze` for an `analyzer`, `Observe` for a `monitor`, `Judge` for a `judge`, `Attest`
for an `attestor` (all `category = reasoning`; TRACE_SPEC §8.1). A producer that cannot distinguish MAY
record `Verify` for all; consumers key on the artifact's attribution block, not the action name.

---

## 3. Attribution - every result names its oracle

Every evidence artifact an oracle returns carries an **attribution block** in its payload:

```
payload.oracle := {
  id                : String,          # the oracle id (registry key)
  oracle_type       : String,          # §1.1
  evidence_strength : one of §1.2,     # the strength of THIS result (honesty rule below), absent if none
  version           : String?,         # the oracle version that produced it
}
```

Attribution is what makes a claim **re-checkable**: a reviewer can see that a `VerificationResult` came
from `imandrax 1.4`, that an `Observation` came from `calendar-db` at schema version 7, that an
`AnalysisNote` was an LLM judge's opinion - and can re-ask the same oracle, or a different one of the
same type.

**Backward compatibility.** Reasoning-result payloads keep their `engine` / `engine_version` fields
(TRACE_SPEC §10.4, §10.4a); for a reasoner oracle they equal `oracle.id` / `oracle.version`, and a
consumer reading a 0.1 trace derives `oracle = {id: engine, oracle_type: "reasoner", version:
engine_version}` when the block is absent. A top-level `evidence_strength` on a payload (0.1) remains
valid and is read as `oracle.evidence_strength`.

**The honesty rule.** `oracle.evidence_strength` on a *result* reflects the **actual verdict**, never the
oracle's capability: `proved` / `refuted` → `proof`; a bounded or witnessed result → `sat`; a passing
run → `tests`; an observation or a sign-off → `attested`; an `unknown`, timed-out, or errored result
carries **no** strength. Evidence never masquerades as stronger than what was established. A consumer
that finds `oracle.evidence_strength` stronger than the oracle's declared capability, or present on an
`unknown` result, SHOULD raise a `Defeater` residual (`Undermines`) against the artifact.

---

## 4. The evidence fingerprint and freshness

A result is current only relative to the **subject** the oracle answered about. For a reasoner the
subject is the task - the target symbol plus its dependency closure in the model. For a monitor it is
the queried state - which source, which query, what it returned, as of when. For a tester it is the
code under test plus the inputs. TRACE_SPEC 1.9 anchored freshness on a reasoner-only
`reasoning_fingerprint` (§10.4a); 0.2 generalizes it (TRACE_SPEC 1.12 §10.4a):

```
evidence_fingerprint := {
  subject_checksum : String,       # strong hash of the SUBJECT the evidence is about - what must be
                                   # unchanged for the result to still apply
  subject_shape    : String?,      # weaker structural hash for fuzzy re-pairing (rename, reorder, moved row)
  subject_ref      : String?,      # what the subject IS: a symbol, a query + source id, a test id, a claim id;
                                   # its disappearance is what makes evidence `Detached`
  oracle_id        : String?,
  oracle_version   : String?,      # an advanced version obsoletes the result even on an exact checksum
  observed_at      : String?,      # ISO-8601 - when the subject was read
  valid_until      : String?,      # ISO-8601 - time-boxed validity, for subjects that expire by clock
                                   # (a fixing, a calendar year, a rate) rather than by change
}
```

`reasoning_fingerprint` is the **reasoner profile** of this record: `task_checksum ≡ subject_checksum`,
`task_shape ≡ subject_shape`, `target_symbol ≡ subject_ref`, `engine` / `engine_version` ≡
`oracle_id` / `oracle_version`. A payload's `fingerprint` field accepts either form; consumers read the
generic names and fall back to the reasoner names.

**How each oracle type computes `subject_checksum`** (normative for the standard types):

| type | subject | `subject_checksum` over | `subject_ref` |
|---|---|---|---|
| reasoner | the reasoning task | the target definition + its full dependency closure in the model (TRACE_SPEC §10.4a) | the target symbol |
| tester | code under test + inputs | the tested unit's closure + the test source / inputs | the test id |
| analyzer | the analyzed structure | the analyzed source or schema, canonicalized | the file / schema id |
| monitor | the queried state | canonical(source id, query, returned value / row set, as-of) | `<source id>:<query hash>` |
| judge | the judged artifact | the judged artifact's `content_ref` + the rubric | the artifact id |
| attestor | the attested claim | the attested artifact's `content_ref` (or the trace `content_hash`) | the claim / artifact id |

**The freshness rule (TRACE_SPEC §18.3, generalized).** For evidence `e` with fingerprint `f`, the
consumer obtains the *current* fingerprint `f'` for `f.subject_ref` - by recomputation when it holds the
subject (the model source is on the trace), by `probe` when the oracle is registered, or not at all -
and decides:

1. `f'` cannot be obtained and `f.valid_until` is absent → **`Unknown`** (neither fresh nor stale; a
   policy may refuse unknown-freshness evidence for a class of claims). *Exception:* a reasoner result
   without a fingerprint keeps the 1.7 action-ordering heuristic, for compatibility.
2. `f.subject_ref` no longer resolves (symbol gone, table dropped, source decommissioned) → **`Detached`**.
3. `now > f.valid_until` → **`Stale`**.
4. the current oracle version is advanced past `f.oracle_version` → **`Stale`**.
5. `f'.subject_checksum = f.subject_checksum` → **`Fresh`**; otherwise → **`Stale`**.

A `Stale` or `Detached` result cannot back an acceptance item's `done` and surfaces a derived
stale-/detached-evidence residual (`suggested_check` = re-invoke the oracle); `Unknown` freshness is
reported on the item and left to policy. This is what makes a **proof honestly rest on a premise**: a
proof of `settle` over a calendar table stays `Fresh` as a reasoner result, while the `Observation`
that the table matches the official calendar goes `Stale` when the calendar is republished - and the
goal that needs both shows exactly which leg moved.

---

## 5. The `Observation` artifact

A monitor's evidence lands as an **`Observation`** artifact (TRACE_SPEC 1.12 §10.11): a typed record of
*a source stated this value at this time in answer to this query*. It is the strict-typed home for
what 0.1 could only file under `CommandResult` or `AnalysisNote`.

```
Observation.payload := {
  statement        : String,          # the fact, in plain language ("2026-12-25 is not a business day in TARGET")
  source           : String,          # the source id (a database, a feed, a system) - the oracle's subject source
  query            : String?,         # the canonical query / lookup that produced it
  value            : json?,           # the returned value / row set (or a content_ref to it)
  observed_at      : String,          # ISO-8601
  valid_until      : String?,         # ISO-8601, when the source itself time-boxes the value
  confidence       : high | medium | low?,
  oracle           : attribution block (§3)   # evidence_strength = attested
  fingerprint      : evidence_fingerprint (§4)
}
```

`artifact_role` is `AuditEvidenceRole`. An `Observation` anchors by `derived_from` to what it was checked
*against* (the model, the config, the claim), so the DAG shows which established result rests on it. It
discharges an `Assumption` residual by being cited in that residual's `related_artifact_ids` and the
residual moving to `addressed`, and it is quantifiable in goals (`has(f, Observation)[fresh]`) and
policies (§6) like any other artifact.

---

## 6. Policies and merge over graded evidence

The policy language (POLICY_LANGUAGE §2.6, structural predicates) gains three predicates over
artifacts, all reading the attribution block:

```
strength_at_least(a, s)      # rank(a.oracle.evidence_strength) <= rank(s); false if a carries no strength
oracle_type(a, t)            # a.oracle.oracle_type = t, or a's declared specialization refines t
produced_by(a, id)           # a.oracle.id = id
```

Standard encodings:

- *high-stakes claims are proof-strength* -
  `G( ∀ a ∈ VerificationResult . high_stakes_path(a) ⇒ strength_at_least(a, proof) )`
- *no goal is met on judgment alone* -
  `∀ i ∈ goal.acceptance . i.status = done ⇒ ∃ a ∈ evidence(i) . ¬ oracle_type(a, judge)`
- *external premises are observed, not assumed* -
  `∀ r ∈ residuals . r.kind = assumption ∧ r.tags ∋ external ⇒ ∃ o ∈ Observation . o ∈ r.related_artifact_ids ∧ fresh(o)`

The policy object's `reasoner` field (POLICY_SPEC §1) generalizes to **`oracle`**: it names an oracle id
or an `oracle_type`; `reasoner: X` remains valid and is read as `oracle: X`. The field is **enforced by
desugaring**, never merely declarative: at compile time it becomes a conjunct on the evidence the formula
ranges over - for every evidence-bearing atom the formula mentions (an oracle action such as `Verify`,
`Decompose`, `Observe`, or a result artifact type such as `VerificationResult`), `G(atom → (produced_by(X)
∨ oracle_type(X)))`; a formula that names no evidence atom is scoped to the formal-reasoning result types.
So `reasoner: codelogician` on `G(Verify → P(Formalize))` checks as
`(G(Verify → P(Formalize))) ∧ G(Verify → (produced_by(codelogician) ∨ oracle_type(codelogician)))`, and
fails on a trace whose proofs came from another engine - or from nothing attributable. `produced_by(X)`
matches the attribution block's `id` or the `engine` it drives (the catalog's `codelogician.engine =
imandrax`), so either name works for a CodeLogician-over-ImandraX result.

**Goal resolution** reports, per resolved item, the strength of the evidence that resolved it, and per
goal the **weakest link** (`min_strength` over required items) - so "met" is never read without its
grade. **Merge composition** (TRACE_SPEC §15.3), when *ours* and *theirs* both carry a standing result
for the same subject and both are `CarriedForward`, prefers the stronger `evidence_strength`; at equal
strength, the later result.

---

## 7. Registry

Oracles are discoverable two ways, kept consistent:

- **Catalog** (reference metadata, remote / gallery) - the `reasoners` registry, whose `kind` maps to
  `oracle_type` (`formal_verification` / `smt` / `model_checking` → `reasoner`). It is expected to grow
  entries of every type; an entry's `kind` for a non-reasoner is its `oracle_type`.
- **Invocable registry** (runtime) - the in-process oracles an SDK can actually call
  (`ponens.oracles.register_oracle` / `get_oracle` / `list_oracles`; `ponens oracle list | show`).
  `list` filters by `--type`, accepting standard and registered names alike.

---

## 8. Reference instances

The registry is expected to hold **many** oracles across all types. The reference set, which together
demonstrates that the abstraction is generic and the evidence spectrum is honest:

| oracle | type | strength | produces | subject fingerprint | status |
|---|---|---|---|---|---|
| **ImandraX** via `codelogician-lite` (`codelogician`) | reasoner | proof / sat | VerificationResult, StateSpaceAnalysisResult | task closure checksum | **shipped** |
| Lean / Z3 | reasoner | proof / sat | VerificationResult | task closure checksum | planned |
| test runner (subprocess, exit status) | tester | tests | CommandResult (TestResult) | command + declared subject | **shipped** (`SubprocessTesterOracle`) |
| type checker / schema check | analyzer | static_analysis | AnalysisNote, CommandResult | canonical source / schema | planned |
| **reference-data store** (mapping / SQLite, `PONENS_REFERENCE_DB`) | monitor | attested | Observation | source id + query + value + as-of; `valid_until`; probe-able | **shipped** (`ReferenceDataOracle`) |
| judge (any callable; an LLM-as-judge plugs in) | judge | attested | AnalysisNote | judged content / `content_ref` + rubric | **shipped** (`CallableJudgeOracle`); LLM-backed reference judge planned |
| human sign-off | attestor | attested | UserApproval | attested claim / `content_ref` | **shipped** (`AttestorOracle`) |

The **reference-data monitor** is the instance that proves the point: it is a database, it produces
governed evidence in the same trace as a proof, it is graded `attested` and never higher, it carries a
fingerprint that goes stale on republication rather than on a code edit, and a goal can require it to be
`[fresh]` alongside a `proof`.

---

## 9. Worked example - a proof resting on an observation

`settle` is proved never to book on a non-business day *given* a calendar table in the model. The
reasoner cannot establish that the model's calendar is the official one, so the proof carries an
`Assumption` residual (tag `external`). A `calendar-db` monitor is invoked with *business days for 2026
as of today*:

```json
{ "artifact_type": "Observation", "artifact_role": "AuditEvidenceRole",
  "derived_from": ["a3-model-1"],
  "payload": {
    "statement": "TARGET business days for 2026 match the model's calendar table",
    "source": "calendar-db", "query": "SELECT day FROM holidays WHERE cal='TARGET' AND year=2026",
    "observed_at": "2026-09-11T09:00:00Z", "valid_until": "2026-12-31T23:59:59Z",
    "oracle": { "id": "calendar-db", "oracle_type": "monitor", "evidence_strength": "attested", "version": "schema-7" },
    "fingerprint": { "subject_checksum": "sha256:4f…", "subject_ref": "calendar-db:sha256:9a…",
                     "oracle_id": "calendar-db", "oracle_version": "schema-7",
                     "observed_at": "2026-09-11T09:00:00Z", "valid_until": "2026-12-31T23:59:59Z" } } }
```

The residual moves to `addressed` citing the observation. The goal item
`[met] has(settle, VerificationResult)[fresh] and [met] has(settle, Observation)[fresh]` resolves
`done` with `min_strength = attested` reported beside it. When the calendar is republished, `probe`
returns a different `subject_checksum`; the observation is `Stale`, the item is `at_risk`, and the
proof - still `Fresh` over the model - is visibly resting on a premise that moved.

---

## 10. Migration

- `reasoner` remains valid everywhere it is used today (the policy `reasoner` field; the `reasoners`
  catalog and `ponens reasoners`). New authoring SHOULD prefer the oracle vocabulary.
- 0.1 traces without `payload.oracle` are read with the derived block of §3; results with a top-level
  `evidence_strength` keep it.
- `reasoning_fingerprint` fields remain valid as the reasoner profile of the evidence fingerprint.
- Consumers that enumerated `oracle_type` MUST relax to warn-not-reject (§1.1).

## 11. Conformance status (reference implementation, `cli/ponens`)

| element | status |
|---|---|
| taxonomy constants, `strength_rank`, `Oracle` base, in-process registry, `ponens oracle list/show` | implemented (0.1) |
| CodeLogician reasoner oracle with honest strength | implemented (0.1) |
| `monitor` in the standard set; open `oracle_type` (warn-not-reject); `specializes` | implemented (0.2): `oracles.check_oracle_type`, `trace.validate_trace` |
| attribution block on results; derivation from `engine` for 0.1 traces | implemented (0.2): `oracles.attribution_of`, `Oracle.attribution` |
| evidence fingerprint (generic names); `probe`; `valid_until` / `Unknown` in freshness | implemented (0.2): `oracles.fingerprint_of` / `freshness_of` / `probe_evidence`; `goals.generic_evidence_freshness` |
| `Observation` artifact type in validate / policy vocab | implemented (0.2) |
| `strength_at_least` / `oracle_type` / `produced_by` predicates | implemented (0.2): `policy_compiler.EVIDENCE_PREDICATES`, evaluated over the action's output artifacts |
| `oracle` policy field (alias `reasoner`), enforced by desugaring into the checked formula | implemented (0.2): `policy_compiler.effective_formula` / `oracle_conjunct`, used by `compile_policy` and `trace.evaluate_policy_full` |
| weakest-link strength (`min_strength`, per-item `evidence_strength` / `freshness`) in `enrich`; strength-aware merge preference (`preferred`, `preferred_result_id`) | implemented (0.2) |
| reference-data monitor (`ReferenceDataOracle`: mapping / SQLite), tester (`SubprocessTesterOracle`), judge (`CallableJudgeOracle`), attestor (`AttestorOracle`) | implemented (0.2); `PONENS_REFERENCE_DB` registers a SQLite store as `reference-data` |
| typed actions per oracle type (`Observe`, `Test`, …) in the SDK; `Session.probe` / `Session.freshness` | implemented (0.2) |
| a second reasoner (Lean / Z3); `ponens verify` CLI verb; catalog entries for non-reasoner oracles | to implement |

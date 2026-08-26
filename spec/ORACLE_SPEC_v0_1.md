# ORACLE_SPEC v0.1 — Oracles and graded evidence

**Status:** draft · additive over TRACE_SPEC v1.11 · **Version:** 0.1

An **oracle** is an invocable producer of evidence about a target, returning that evidence as
trace artifacts. Crucially, an oracle is **ANY producer of evidence — emphatically not just a formal
tool.** A prover is one kind of oracle; a test run, a static analysis, a runtime monitor, an LLM's
judgment, a data-freshness check, and a human sign-off are *equally* oracles. What unifies them is not
the mechanism but the contract: each returns evidence about a target, tagged with an **honest
strength**. A *reasoner* is simply the formal, proof-producing **subtype**.

This breadth is the point. It is what lets ponens govern the *full spectrum of how work actually gets
checked* — proof, tests, observation, judgment, attestation — under one trace, and what makes the
substrate tool- and prover-agnostic (ImandraX, Lean, a fuzzer, an LLM judge, a reviewer are all
oracles). The trace model's own language reflects it: every claim records *which oracle produced it,
under what assumptions, and how strong the evidence is*.

## 1. Classification

Two orthogonal classifiers travel with every oracle and with the evidence it produces.

### 1.1 `oracle_type` — the mechanism

| `oracle_type` | What it is | Examples |
|---|---|---|
| `reasoner` | Formal engines — proof / decision procedures | ImandraX, Lean, Z3, a model checker |
| `tester`   | Dynamic execution — run it and observe | test runners, property-based testing, fuzzers, simulators, backtests |
| `analyzer` | Static inspection without execution | type checkers, SAST, linters, schema / contract checks |
| `monitor`  | Runtime / observational evidence from a live system or external source | production telemetry, runtime assertions, canaries; **data-freshness / rate-fixing / calendar / rulebook-version checks** |
| `judge`    | Heuristic / probabilistic assessment | LLM-as-judge, rubric evaluators, model-graded eval |
| `attestor` | Human or external sign-off | a reviewer, a domain expert, an external certification, a regulator |

Non-formal oracles are first-class, not an afterthought: a `monitor` that confirms a rate fixing is
today's official value, a `tester` backtest, an `analyzer` schema check, a `judge`'s rubric score, and
an `attestor`'s role-bearing sign-off all produce governed evidence in the same trace as a proof —
each honestly graded (§1.2), never dressed up as stronger than it is.

### 1.2 `evidence_strength` — the guarantee

A total order, strongest first. It is the *guarantee the output carries*, distinct from the
mechanism that produced it (a `reasoner` model checker may yield `sat`, not full `proof`).

    proof  >  sat  >  tests  >  static_analysis  >  attested

- `proof` — a property holds over the entire (possibly unbounded) state space.
- `sat` — a model/witness was found, or a bounded check passed.
- `tests` — empirical evidence from executed cases (sampled, not exhaustive).
- `static_analysis` — sound-ish over-approximation without execution.
- `attested` — asserted by a heuristic judge or a human; not mechanically established.

`evidence_strength` is a **new, additive field**; traces and oracles that omit it are treated as
unranked (sorts last). Policies and merge composition MAY require a minimum strength.

### 1.3 Reasoner-agnostic

The `reasoner` subtype is deliberately **plural**. The layer is reasoner-agnostic: **ImandraX**
(driven via `codelogician-lite`) is the reference, shipped reasoner oracle, but it is *one of several*
— **Lean**, **Z3**, and other provers / SMT / model checkers register as `reasoner` oracles on equal
footing. Nothing in the trace, the SDK, or a policy is hardwired to a single engine:

- `verify(target, oracle=…)` selects a reasoner by id; a policy may `require` a specific reasoner (or
  a minimum `evidence_strength`); absent that, a configurable default applies (ImandraX out of the box).
- Every result records **which reasoner** produced it, so a claim is attributable and re-checkable by
  another party — potentially with a *different* engine.

This neutrality is a moat, not a hedge: ponens becomes the governance layer *over the whole
formal-verification ecosystem* (and, via §1.1, over non-formal evidence too), rather than a front end
for one prover. Evidence from ImandraX, Lean, a fuzzer, an LLM judge, or a human reviewer all lands in
the same governed, re-checkable trace.

## 2. The oracle contract

An oracle exposes metadata and one operation:

```
oracle := {
  id                : String,
  name              : String,
  oracle_type       : one of §1.1,
  evidence_strength : one of §1.2,   # the strength it typically produces
  produces          : [ArtifactType],
  vendor            : String?,
  description       : String?,
}

invoke(target, context?) -> [artifact]
```

`invoke` returns zero or more artifact objects (TRACE_SPEC §7) **without** `artifact_id` or
`producer_action_id` — the caller (e.g. an SDK `Session`) assigns those, records the invoking
`Verify` action, and wires `derived_from` lineage from the target. Each returned artifact SHOULD
carry `evidence_strength` in its payload.

## 3. Evidence payloads

`VerificationResult` (and sibling result artifacts) gain an optional `evidence_strength`:

```
VerificationResult.payload := {
  status                : proved | sat | refuted | unknown,
  engine                : String,
  result                : String,
  reasoning_fingerprint : String?,
  evidence_strength     : one of §1.2,   # NEW
  target_symbol         : String?,
}
```

## 4. Registry

Oracles are discoverable two ways, kept consistent:
- **Catalog** (reference metadata, remote/gallery) — the `reasoners` registry, whose `kind` maps to
  `oracle_type` (`formal_verification`/`smt`/`model_checking` → `reasoner`).
- **Invocable registry** (runtime) — the in-process oracles an SDK can actually call
  (`ponens.oracles.register_oracle` / `get_oracle` / `list_oracles`; `ponens oracle list`).

The registry is expected to hold **many** oracles across all types (§1.1). Shipped today: the
**ImandraX** reasoner (id `codelogician`, via `codelogician-lite`) as the reference implementation.
Planned reference oracles to demonstrate the full spectrum — a second reasoner (e.g. **Lean**), a
`tester` (test runner → `tests`), a `judge` (LLM-as-judge → `attested`), a `monitor` (data-freshness
check), and an `attestor` (human sign-off) — so the registry is visibly reasoner-agnostic and evidence
spans proof → tests → attested, not formal-only.

## 5. Migration

`reasoner` remains valid everywhere it is used today (the policy `reasoner` field requires an
oracle whose `oracle_type = reasoner`). New authoring SHOULD prefer the oracle vocabulary. The
`ponens reasoners` catalog command is retained; `ponens oracle` lists the invocable oracles.

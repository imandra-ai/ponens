# SDK_SPEC v0.1 — the ponens developer SDK and oracle model

**Status:** draft · design frozen for handoff · **Version:** 0.1
**Companion specs:** `ORACLE_SPEC_v0_2.md` (graded evidence + oracle contract), `TRACE_SPEC_v1_12.md` (wire format), `POLICY_SPEC_v0_2.md`.
**Reference implementation:** branch `denis/ponens-sdk-oracle-slice` (`cli/ponens/sdk.py`, `cli/ponens/oracles.py`, tests `test_sdk.py` / `test_oracles.py`).

---

## 1. Purpose & scope

The SDK lets a developer build an agent that **speaks ponens natively** — it instruments itself as it
runs and, on exit, produces a validated trace that passes `ponens trace check`. This is the
runtime counterpart to `ponens emit` (which reconstructs a trace from a transcript *after* the fact).

Strategic role (context, not normative): the SDK is the **bottom-up adoption engine** for the ponens
trace format — "OpenTelemetry for agent reasoning." Ubiquity of the format is the moat for the
independent-verification/utility play; the SDK is the top of the funnel, monetized at the
enterprise/utility layer, not the SDK itself. Keep it open and free.

### Design principles

1. **One trace model.** The SDK builds the *same* JSON-native trace dict the rest of `ponens` uses
   (`trace.create_empty_trace`, `next_action_id`, `save_trace`, `validate_trace`, `objects.externalize`).
   No parallel model, no dialect fork. `emit` (post-hoc) and the SDK (native) share the artifact and
   lineage builders.
2. **Thin.** The SDK is a recording layer, not a framework. It appends to the dict; it does not own
   control flow.
3. **Singular spec.** The format the SDK emits is exactly the format COGITO's invariants/processes
   consume. Bottom-up and top-down converge on one wire format.
4. **Honest evidence.** Evidence carries a *graded* strength and the SDK never overstates it (see §4).

---

## 2. The `Session` API

A `Session` is a live trace under construction. Recommended use is as a context manager: on clean
exit it stamps an outcome if none was set, validates, externalizes blobs, and writes `path`; on an
exception it marks the run aborted, best-effort saves the partial trace, and never masks the error.

```python
from ponens.sdk import Session

with Session(model="claude-opus", assistant="my-agent", path="trace.json",
             intent="prove charge() is idempotent") as s:
    a = s.action("EditFile", label="edit pricing.py", rationale="route retries via an idempotency key",
                 evidence=[{"type": "FileRef", "ref": "pricing.py"}])
    m = s.artifact("IMLModel", name="pricing.iml", content=iml_src, format="iml",
                   producer_action_id=a)
    s.verify({"iml_code": iml_src, "goal": "idempotent charge", "target_symbol": "charge"},
             oracle="codelogician", derived_from=m)
    s.residual("assumption", "gateway is at-least-once", suggested_check="model duplicate delivery")
```

### Constructor

```
Session(model="example-model", assistant="ponens", path=None, intent=None, trigger=None)
```
- `path` — where `save()` / context-exit writes. If omitted, build in memory and `save(path)` explicitly.
- `intent` / `trigger` — sets `trigger = {type: "TaskReceived", text: …}`; `intent` also opens a goal.

### Recording primitives

| Method | Returns | Effect |
|---|---|---|
| `action(type, label=, rationale=, detail=, category="activity", inputs=, outputs=, evidence=)` | `int` (action id) | Appends an action; auto-assigns the id. |
| `artifact(artifact_type, name=, payload=, derived_from=, producer_action_id=, content=, format=, role=)` | `str` (artifact id) | Appends a typed artifact; `content` is content-addressed into the object store as `content_ref`; wires the producing action's `outputs`. |
| `goal(intent, scope=, acceptance=)` | `str` (goal id) | Declares a goal (intent + optional scope/acceptance). |
| `residual(kind, statement, severity="medium", status="open", suggested_check=, derived_from=)` | `str` | Declares negative space as a `Residual` artifact. |
| `verify(target, oracle, derived_from=, label=, rationale=)` | `list[str]` | Invokes an oracle and records an action typed by its mechanism (`Verify` / `Test` / `Analyze` / `Observe` / `Judge` / `Attest`) + the evidence artifact(s), wiring lineage. See §3. Aliases: `observe`, `test`, `judge`, `attest`. |
| `probe(artifact_id, context=)` | fingerprint / `{"detached": True}` / `None` | Re-reads the CURRENT fingerprint of an evidence artifact's subject via the oracle that produced it (ORACLE_SPEC v0.2 §4); records nothing. |
| `freshness(artifact_id, context=)` | `fresh` \| `stale` \| `detached` \| `unknown` | The derived freshness verdict of an evidence artifact, by probing. |
| `outcome(type="ProcessCompleted", summary=)` | — | Stamps the terminal event. |

### Lifecycle

| Method | Behavior |
|---|---|
| `validate()` | Returns `(errors, warnings)` from `trace.validate_trace`. |
| `save(path=None, strict=True)` | Externalizes blobs; with `strict`, structural errors raise; writes the trace. |
| `__enter__` / `__exit__` | On success: stamp `ProcessCompleted` if unset, `save()` if `path` given. On exception: stamp `ProcessAborted(summary=str(exc))`, best-effort `save(strict=False)`, **re-raise** (never swallow, never mask). |

---

## 3. Oracles and `verify()`

`verify(target, oracle, …)`:
1. Resolves `oracle` — an oracle id (from the registry, §4.4) or an `Oracle` instance.
2. Records a `Verify` action (`category="reasoning"`).
3. Calls `oracle.invoke(target)`, appends each returned artifact with `producer_action_id` = the
   Verify action and `derived_from` = the target lineage, and returns the new artifact ids.

`target` is oracle-specific; for the CodeLogician oracle it is `{iml_code, goal?, target_symbol?}`.

Unknown oracle id raises `ValueError`.

---

## 4. The oracle model (see ORACLE_SPEC v0.1)

An **oracle** is an invocable evidence producer. A **reasoner** is the formal, proof-producing
*subtype* of oracle. Two orthogonal classifiers travel with each oracle and its evidence:

### 4.1 `oracle_type` (mechanism)
`reasoner | tester | analyzer | judge | attestor` — provers, test runners, static analysis,
LLM-judges, human attestation.

### 4.2 `evidence_strength` (guarantee), strongest first
```
proof > sat > tests > static_analysis > attested
```
`strength_rank(s)` ranks a strength (0 = strongest; unknown sorts last), so a policy can require a
minimum and a merge can prefer stronger evidence.

### 4.3 The `Oracle` contract
```
class Oracle:
    id: str
    name: str
    oracle_type: str            # §4.1
    evidence_strength: str      # §4.2 — the strength it is capable of
    produces: tuple[str, ...]   # artifact types
    vendor: str; description: str
    def invoke(self, target, context=None) -> list[artifact_dict]: ...
    def as_dict(self) -> dict
```
`invoke` returns artifact dicts **without** `artifact_id` / `producer_action_id` (the SDK assigns
those). Each artifact's payload SHOULD carry the *actual* `evidence_strength` of the result.

### 4.4 Registries
- **Invocable (runtime):** in-process — `register_oracle`, `get_oracle`, `list_oracles`; surfaced by
  `ponens oracle list|show`. These are the oracles an SDK `Session` can actually call.
- **Catalog (reference):** the `reasoners` gallery (`reasoners.py`, `PONENS_REASONER_URL`), retained;
  its `kind` maps to `oracle_type` via `oracle_type_for_kind` (all current entries → `reasoner`).

### 4.5 Honesty rule
`evidence_strength` in a result reflects the **actual verdict**, not the oracle's capability:
`proved`/`refuted` → `proof`, bounded → `sat`, otherwise the result carries **no** strength (an
`unknown`/error result never masquerades as graded evidence).

---

## 5. The CodeLogician oracle (oracle #1)

`CodeLogicianOracle` (`id="codelogician"`, `oracle_type="reasoner"`, `evidence_strength="proof"`,
`vendor="Imandra"`) drives Imandra's **`codelogician-lite`** CLI (the LLM-friendly front end to the
ImandraX engine) — **not** the raw engine. The runner is dependency-injectable (tests / CLI-less
environments pass a fake).

### 5.1 Invocation
```
codelogician-lite check-vg <file>.iml --json
```
Binary resolution: env `CODELOGICIAN_CLI`, then `codelogician-lite` on `PATH`.

### 5.2 `check-vg --json` schema (ground truth)
```json
{
  "eval_res": "Success",                         // admit: "Success" | {success: bool, errors:[…]}
  "diags": [],
  "vg_res_list": [
    { "vg_req_index": 0, "kind": "verify", "src": "fun x -> f x > x",
      "vg_res": { "proved": {"proof_pp": "…"}, "refuted": null,
                  "verified_upto": null, "unknown": null, "err": null, "errors": [] } }
  ]
}
```

### 5.3 Verdict mapping
Per goal (`_verdict_of`): `refuted` (non-null) → refuted; else `proved` → proved; else
`verified_upto` → sat; else unknown. Counterexample extracted from `refuted.model_str|model|src`.
Aggregate (`_aggregate`): any `refuted` → refuted; all `proved` → proved; all `proved|sat` → sat;
else unknown. Admit failure (`eval_res` not success) → unknown.

### 5.4 Produced artifact
`VerificationResult` with payload `{status, engine:"imandrax", result, reasoning_fingerprint,
evidence_strength?, oracle: {id, oracle_type, evidence_strength?, version?}, fingerprint: {subject_checksum,
subject_ref?, task_checksum, target_symbol?, oracle_id, …}, counterexample?, target_symbol?}` (ORACLE_SPEC
v0.2 §3-§4); `artifact_role` = `CounterexampleRole` when refuted, else `ProofRole`.

---

## 6. CLI surface

- **Now:** `ponens oracle list|show` — the invocable oracles (id, name, oracle_type,
  evidence_strength, produces). `ponens reasoners …` (catalog) retained.
- **Planned:** `ponens verify <trace> --oracle <id> --target …` — surface `Session.verify` from the
  command line.

---

## 7. CodeLogician as the first consumer

The SDK should be **extracted from** the CodeLogician agent (imandra-pi-agent), not bolted on — that
agent already speaks ponens (records verify/decompose/testgen artifacts, policy eval, goals/trace).
CodeLogician is the dogfood *and* the strongest demo (its oracle is proof-strength).

**Language boundary:** CodeLogician is TypeScript/Node; the SDK is Python-first.
- **Near-term:** integrate via the `codelogician-lite` / `ponens` **CLI/subprocess** (already the
  pattern for policy checks).
- **Native:** requires a **TypeScript SDK** — CodeLogician is the forcing function that raises TS-SDK
  priority. Migrate incrementally (parallel path → parity → cut over); do not destabilize the shipping agent.

---

## 8. Roadmap (phased)

| Phase | Content | Status |
|---|---|---|
| **0** | Oracle contract + `evidence_strength` + `oracle_type` (ORACLE_SPEC v0.1); schema bump | **implemented** (spec) |
| **1** | Thin runtime SDK (`Session`) | **implemented** |
| **2** | Oracle interface + registry + CodeLogician oracle (proof); reference oracles across the spectrum (reference-data monitor, tester, judge, attestor); `probe` / freshness (ORACLE_SPEC v0.2) | **implemented** |
| 3 | `ponens init` scaffolding / codegen (instrumented agent template, `.ponens/`, CI gate) | planned |
| 4 | Framework adapters — MCP server, LangChain/CrewAI callback | planned |
| 4.5 | **TypeScript SDK** (bumped up — CodeLogician is TS) | planned |
| 5 | Hosting / PLG — hosted traces, org policy, grading service, public oracle marketplace | **deferred** (= COGITO/utility; don't split focus) |

### Recommended next increments
1. `ponens verify` CLI verb (surface `Session.verify`).
2. **Prove reasoner-agnosticism:** a second *reasoner* oracle (e.g. **Lean**) alongside ImandraX, so
   `verify` / policies can pick the engine and a claim records which one produced it (ORACLE_SPEC §1.3).
3. ~~Span the evidence spectrum~~ — done in ORACLE_SPEC v0.2: `ReferenceDataOracle` (monitor: a
   database / reference-data store), `SubprocessTesterOracle`, `CallableJudgeOracle`, `AttestorOracle`.
   Next: an LLM-backed judge and a catalog (gallery) entry per non-reasoner oracle.
4. CodeLogician integration via subprocess (the extract-from step).
5. Full `reasoners → oracles` rename with deprecation aliases (currently additive; both coexist).

---

## 9. Naming & migration

`reasoner` remains valid everywhere it is used today (the policy `reasoner` field requires an oracle
whose `oracle_type = reasoner`). New authoring prefers the oracle vocabulary. Full rename
(`reasoners.py` → `oracles.py`, `ponens reasoners` → `ponens oracle`, `PONENS_REASONER_URL` →
`PONENS_ORACLE_URL`, cache dir) should ship with deprecation aliases — do it **before** the SDK/registry
reach wide adoption. Currently the two coexist (additive).

---

## 10. Open decisions

- **Lock the `evidence_strength` taxonomy** (§4.2) — it propagates into policies, merge, and payloads.
- **Oracle trust/sandboxing** — fine for local dev; the *public* registry needs curation (a bad
  oracle = false assurance). The "curated trust layer" is a differentiator.
- **`oracle_type` vs `evidence_strength`** — kept as two fields (mechanism vs guarantee); could
  collapse to strength alone, but type is the browse/filter axis for the registry.
- **TS SDK timing** — gated by CodeLogician's native-integration need.

---

## 11. Test / run notes

- Run tests with a pytest-capable interpreter from `cli/` (e.g. `~/miniconda3/bin/python3 -m pytest
  tests/unit/`). The uv-tool `ponens` env lacks pytest; `ponens` imports resolve when run from `cli/`.
- The reference-implementation slice: full unit suite green (557 passed / 1 skipped at freeze), plus
  `test_sdk.py` + `test_oracles.py`. E2e: an SDK-built trace grades cleanly via `ponens trace grade`
  (Structure/Lineage 100%, proof evidence recorded).

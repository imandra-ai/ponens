# Record Overview Specification

## Version

**Version:** 0.1  
**Status:** Draft  
**Purpose:** How a reasoning trace is *read* - where a record stands, in five words (requirement · evidence · gap · record · gate) - as one JSON every renderer consumes, so that no renderer re-derives semantics. Companion to `TRACE_SPEC_v1_13.md` (§11.2-11.3 conformance against a reference, §18 goals). Implemented by `ponens trace requirements`, `ponens trace overview` and `ponens trace integrity` (ponens ≥ 1.13).

Everything a person reads about a record is said with five nouns and their states. The formal terms of
TRACE_SPEC (artifact, residual, policy, conformance, reference artifact, acceptance item) stay in the
record; this document fixes how they are *read* — one JSON every renderer (a terminal, an agent, a
desktop, a PR comment) consumes, so that no renderer re-derives semantics.

| Word | Absorbs | States |
|---|---|---|
| requirement | goal acceptance item, binding (a reference artifact + its conformance items), invariant | `met` · `open` · `failed` · `out_of_date` |
| evidence | VerificationResult, ConformanceResult, StateSpaceAnalysisResult, tests, attestation | grade `proved` · `witnessed` · `tested` · `checked` · `attested`; `fresh` · `out_of_date` · `unknown` |
| gap | residual (assumption, limitation, defeater, open_question, unverified, stale/detached evidence) | `missing` · `assumed` · `failed` · `out_of_date` |
| record | the trace | (health) |
| gate | policy evaluations | `pass` · `blocked` |

plus `model` for what a requirement points at (the reference artifact).

## Grades

`evidence_strength` → grade: `proof`→`proved`, `sat`→`witnessed`, `tests`→`tested`,
`static_analysis`→`checked`, `attested`→`attested`. Order is the ladder's: proved > witnessed > tested >
checked > attested. A requirement's `required_grade` is the weakest grade that meets it.

## `ponens trace requirements <trace> --file <requirements-file> [--cwd <dir>] [--json]`

The requirements file is the agent's `bindings.yaml` (YAML or JSON; schema below). Output:

```json
{
  "requirements": [
    {
      "id": "stripe-refunds",
      "model": {"entry": "gallery:stripe/refunds", "name": "Refunds and amounts", "version": "2024-06-20",
                "current_version": "2024-06-20", "status": "current"},
      "kind": "refinement",
      "required_grade": "tested",
      "state": "met",
      "reason": null,
      "evidence": {"artifact_id": "fr8-conformance", "grade": "tested", "status": "passed", "freshness": "fresh"},
      "symbols": [
        {"file": "payments.py", "symbol": "refundable_amount", "entry_symbol": "refundable_amount",
         "scope": "symbol", "bound": true, "declared": true, "state": "met", "reason": null,
         "evidence": {...}, "other_evidence": null}
      ],
      "reading": {"state": "recorded", "chosen": "...", "approved_by": "..."},
      "open_findings": [], "invariants": []
    }
  ],
  "summary": {"requirements": 6, "met": 6, "open": 0, "failed": 0, "out_of_date": 0,
              "gate": "pass", "blocked_by": []}
}
```

### Derivation (per symbol row, or one `scope: "project"` row when the requirement names no symbols)

Sources: the requirements file; the trace's `goals` (declared = an acceptance item with `id` ==
`<requirement id>:<symbol>` or `<requirement id>:project` exists), `reference_artifacts` (the model as
last seen: `version`, `payload.checksum`, `name`, `payload.findings`), `artifacts` (ConformanceResults),
`residuals` and the reasoner freshness (`stale_evidence` / `reference_freshness`); the source file on
disk under `--cwd` when present (bound = the symbol is defined there; unknown when unreadable).

Evidence for a row = the LATEST ConformanceResult (by `producer_action_id`) whose
`payload.reference_artifact_id` is the requirement's reference id (`ref:<entry>@<version>` or `ref:<entry>`)
and whose `entry_symbol` / `target_symbol` match when stamped. Its freshness: `out_of_date` when a
derived `stale-ref-`/`detached-ref-` residual targets it or the reasoner freshness marks it stale/gone;
`fresh` when the reasoner marks it fresh; else `unknown` (never assumed fresh).

Row state, first rule that applies:

1. `bound == false` → `open`, reason `symbol not found in <file>`
2. not declared → `open`, reason `not yet in the record`
3. no evidence → `open`, reason `no evidence yet`
4. evidence status `failed`/`refuted` → `failed`, reason the counterexample or the failure line
5. freshness `out_of_date` or `unknown` → `out_of_date`, reason `the code or the model changed since` / `freshness unknown`
6. grade below `required_grade` → `open`, reason `<grade>, needs <required_grade>`
7. → `met`

Requirement state = the worst of its rows (`failed` > `out_of_date` > `open` > `met`), except:
`model.status == "revised"` (file version ≠ `reference_artifacts[..].version`) → `out_of_date`, reason
`the model was revised: <old> → <new>`; `reading.state == "missing"` (open findings on the model and no
reading chosen) → `open`, reason `reading not chosen`. `model.status` is `unknown` when either version is
absent. `reading.state`: `recorded` when the file chooses one and the trace carries residual
`interpretation:<id>`; `chosen` when the file chooses one but the trace does not carry it yet;
`missing` when the model has open findings and nothing is chosen; `not_needed` otherwise.

`summary.gate` is `pass` when every requirement is `met`, else `blocked` with `blocked_by` = the ids
that are not. (The policy gate is `overview.gate`, separately.)

### Requirements that are not in the file

Every acceptance item of a goal in the trace whose id does not start with `binding:` is a requirement
too, listed after the file-derived ones: `id` = `<goal id>/<item id>`, `label` = the item's label,
`model` = null, `kind` = the item's kind, `required_grade` from the item's `min_strength` /
`evidence.strength` when present else null, `required` from the item, `symbols` = []. Its state comes
from the resolved item: done → `met` (`out_of_date` when its evidence is stale per `stale_evidence`),
blocked → `failed`, doing → `open` ("in progress"), todo → `open` ("no evidence yet"). Every
requirement carries a `label` (file-derived: the model's `name`, else the entry). `trace overview` lists
these even with no file; the summary counts include them.

### Requirements file schema (the agent's `bindings.yaml`)

```yaml
atlas: {source: <dir>}            # optional: a private set of models
bindings:
  - id: stripe-refunds
    entry: gallery:stripe/refunds  # catalogue id | gallery:<family>/<name> | file:<path> | repo:<dir>#<path>@<ref>
    version: 2024-06-20           # pinned; the reference artifact id is ref:<entry>@<version>
    conformance: {kind: refinement|equivalence|invariant, strength: proof|sat|tests|static_analysis|attested}
    code: [{file: payments.py, symbols: [refundable_amount], maps_to: [refundable_amount]}]   # optional
    interpretation: {finding: ..., chosen: ..., justification: ..., approved_by: ...}         # optional
    invariants: [...]             # optional
```
Ids of the derived objects (as the CodeLogician agent writes them): goal `binding:<id>`; acceptance items
`binding:<id>:<symbol>` / `binding:<id>:project`; reading residual `binding:<id>:interpretation`;
reference artifact `ref:<entry>@<version>` (or `ref:<entry>` when no version is pinned). A `requirements:`
key is accepted as a synonym of `bindings:`; a YAML date under `version:` is read as its ISO string.

## `ponens trace overview <trace> [--file <requirements-file>] [--cwd <dir>] [--json]`

One JSON with everything a screen shows:

```json
{
  "requirements": [...], "summary": {...},          // as above (empty when no file)
  "gaps": [{"id": "r2", "state": "assumed", "severity": "medium", "kind": "assumption",
            "statement": "...", "symbols": ["settle"], "suggested_check": null}],
  "gate": {"state": "pass", "blocked_by": [], "rules": [{"id": "apply-formal-methods/...", "state": "pass", "severity": "error", "note": null}]},
  "next": [{"kind": "fix|meet|refresh|gap|optional", "label": "...", "why": "...", "suggested": "...", "requirement": "stripe-refunds", "item": "..."}],
  "evidence": {"proved": 0, "witnessed": 0, "tested": 13, "checked": 0, "attested": 0, "unranked": 0, "failed": 0, "out_of_date": 0,
               "by_symbol": {"settle": {"grade": "proved", "status": "proved", "freshness": "fresh", "artifact_id": "...", "gaps": 0}}},
  "record": {"title": "...", "trace_id": "...", "artifacts": 43, "actions": 57, "outcome": "ProcessCompleted"},
  "counts": {"gaps": {"missing": 0, "assumed": 2, "failed": 0, "out_of_date": 0}}
}
```

`gaps` = open residuals (declared + derived) with `state` from kind: assumption/limitation → `assumed`;
defeater → `failed`; stale/detached evidence or needs_rereasoning → `out_of_date`; anything else
(open_question, unverified, coverage_regression) → `missing`; ordered critical → info. `gate.rules` come
from `policy_evaluations` (passed → `pass`, failed → `blocked` for severity error, `warning` otherwise,
else `unchecked`); `gate.state` is `blocked` when any error-severity rule is blocked. `next` is
`next_steps` with kinds renamed (`establish` → `meet`) and the requirement id resolved from the goal id.
`evidence.by_symbol` is the blame projection's best result per symbol, graded; the grade counts count
every symbol's best result by grade (a failed tested result still counts as `tested` and as `failed`).
`next[]` carries `requirement` (the id, when the goal is `binding:<id>`), `goal`, `item`, `severity`.
Freshness note: a ConformanceResult with no fingerprint and no `engine` is of unknown freshness (the
blame rule), and unknown is never assumed fresh — so such a row is `out_of_date` ("freshness unknown").

## `ponens trace integrity <before> <after> [--json]`

Names the established evidence in `before` that `after` no longer holds — a passed ConformanceResult
or a proved VerificationResult that is gone, a ConformanceResult that no longer cites its reference, a
done acceptance item that is open again. A changed verdict under a new id is a new fact, not a loss.

```json
{"ok": false, "lost": [{"id": "fr3-conformance", "what": "met requirement", "reference": "ref:...", "detail": "is gone"},
                       {"id": "g1/a1", "what": "done requirement item", "reference": null, "detail": "was done and is open again"}]}
```

Exit status 0 when nothing is lost, 3 otherwise (so a hook can refuse the write).

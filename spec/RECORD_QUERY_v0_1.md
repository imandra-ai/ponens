# Record Query Specification

## Version

**Version:** 0.1
**Status:** Draft
**Purpose:** How a reasoning trace is *asked* - what is known about a symbol, and is it still true - so an agent consults the record instead of re-deriving from source. Companion to `RECORD_OVERVIEW_v0_1.md` (where the record *stands*) and `TRACE_SPEC_v1_13.md`. Implemented by `ponens trace symbols` and `ponens trace symbol`.

The overview answers "where does this project stand". This answers "what do you already know about
`step`, and can I still believe it". Both read the same record; neither needs an engine.

## Why it exists

An agent re-derives what a function does every time it needs it: the source goes back into the context
window, the branches get enumerated again, and the answer differs slightly each time. The record already
holds that enumeration - exhaustive, in closed form, computed once on a CPU. It is not reachable, because
there is no way to ask.

Two properties make it safe to substitute for re-reading, and both must hold:

- **Freshness rides on every record.** A stale answer says so. An agent that reasons confidently from a
  result that no longer describes the code is worse off than one that re-read the file.
- **Nothing is returned that was not established.** Absence is reported as absence. The query never
  infers, summarises speculatively, or fills a gap with a plausible answer.

## Size is part of the contract

The point of the query is to spend fewer tokens than reading the source. An interface that returns
everything defeats itself, so size is specified rather than left to the caller:

| | shape | budget |
|---|---|---|
| `trace symbols` | one record per symbol | ~25 tokens each; whole projects fit in a prompt |
| `trace symbol` (default) | summary: counts, distinct outcomes, what the splits are on | ~150 tokens |
| `trace symbol --regions` | the region map | bounded by `--limit` (default 20) and `--where` |

A caller that wants everything asks for it explicitly and is told what it did not get.

## `ponens trace symbols <trace> [--cwd <dir>] [--file <requirements-file>] [--json]`

The index. One line per symbol the record knows anything about - enough to decide whether to ask a
second question, never enough to answer one. This is what a host injects into a system prompt each turn.

```json
{
  "symbols": [
    {
      "symbol": "step",
      "file": "payments.py",
      "kind": "decomposition",
      "grade": "tested",
      "freshness": "fresh",
      "regions": 83,
      "gaps": 1,
      "requirement": "stripe-payment-lifecycle",
      "ref": "fr58",
      "established_at": "2026-09-13T13:16:18Z"
    }
  ],
  "summary": {"symbols": 12, "fresh": 9, "out_of_date": 2, "unknown": 1}
}
```

- `kind` - `decomposition` · `verification` · `conformance` · `model` · `tests`. What backs the entry.
- `grade` - the five-word grade (`proved` · `witnessed` · `tested` · `checked` · `attested`), or
  `unranked`.
- `freshness` - `fresh` · `out_of_date` · `unknown`, relative to the source the entry was derived from.
- `requirement` - the requirement this serves, when `--file` is given; `null` otherwise.
- `ref` - the record entry, so a reader can open it (`/cl-show #fr58`) and a writer can cite it.

**Latest wins.** One record per `(symbol, file)`: the most recent entry that is not superseded. The
history is in the trace and is not what an index is for.

## `ponens trace symbol <trace> <symbol> [--file <path>] [--regions] [--where <expr>] [--limit <n>] [--cwd <dir>] [--json]`

What is actually known. Summary by default:

```json
{
  "symbol": "step",
  "file": "payments.py",
  "freshness": {"state": "out_of_date", "since": "the source changed after this was established",
                "derived_from": "payments.py@467518e3"},
  "evidence": [
    {"kind": "decomposition", "grade": "tested", "ref": "fr58", "regions": 83},
    {"kind": "conformance", "grade": "tested", "ref": "fr15", "reference": "gallery:stripe/payment-lifecycle:step@2024-06-20",
     "outcome": "met", "total": 83, "diverged": 0, "raised": 0}
  ],
  "shape": {
    "splits_on": ["s.status", "a.c", "a.needs_action", "s.stored"],
    "outcomes": 5,
    "outcome_labels": ["Executed", "Replayed", "Conflicted", "Rejected", "Ignored"]
  },
  "gaps": [
    {"id": "r11", "state": "missing", "severity": "high", "statement": "ImandraX could not decide …"}
  ],
  "assumptions": [
    {"target": "amount", "kind": "representation", "abstraction": "contract",
     "detail": "integer quantity modelled as real"}
  ],
  "scope": "covers only the subspace where `pre` holds"
}
```

`shape` is the reason the summary is usually enough: which variables the behaviour actually turns on,
how many distinct outcomes there are, and what they are. Three lines that answer most questions without
returning a single region.

`assumptions` and `scope` are not decoration. A region map produced under a side condition describes part
of a domain, and an answer drawn from it inherits that limit. Returning the regions without the scope
would be the same class of error as reporting an unrun check as a failed one.

### `--regions`

Returns the map. Each region is the constraint that reaches it and the invariant it produces, plus the
witness when the engine synthesised one:

```json
{
  "symbol": "step",
  "complete": true,
  "bound": null,
  "total": 83,
  "returned": 4,
  "regions": [
    {
      "id": "1.1.1.1",
      "constraints": ["a.c = Capture", "s.status = Requires_capture", "not a.needs_action"],
      "invariant": "{s with status = Succeeded; amount_received = s.amount; last = Executed}",
      "witness": {"input": "…", "output": "…"}
    }
  ]
}
```

- **`complete`** - whether the decomposition is exhaustive over the domain. `false` with a `bound` when
  recursion forced a depth. "Every case satisfies it" and "every case to depth 12 satisfies it" are
  different claims; a consumer that cannot see which it has will conflate them.
- **`returned` vs `total`** - a truncated answer says so, always.

### `--where <expr>`

Narrows the map. `expr` is a substring match against a region's constraints and invariant, or one of:

- `outcome:<label>` - regions producing that outcome
- `diverged` - regions where a conformance check disagreed
- `raised` - regions where the code raised before returning (adapter trouble, not divergence)

`--where 'a.c = Cancel'` turns eighty-three regions into three. This is where the token saving is.

## Absence, and being wrong

- Symbol not in the record: `{"symbol": "…", "known": false}`. Not an error - "nothing is known" is an
  answer, and the caller should read the source.
- Trace unreadable or too old: exit 2 with a message naming the version needed. Never a partial answer.
- No entry is returned without its freshness. A consumer may trust `fresh`, must warn on `out_of_date`,
  and must not treat `unknown` as either.

## How a host uses it

1. **Inject the index at turn start**, the way a requirements block is injected. It is what makes the
   rest reachable: an agent cannot consult what it does not know exists.
2. **Ask the detail query when a question touches a known symbol**, summary first.
3. **Ask for regions only when the answer needs a specific case**, with `--where`.
4. **Cite the `ref`**, do not inline the content. A citation costs a few tokens and keeps the record out
   of the context window while leaving the reader able to open it.
5. **Re-read the source when the answer is `out_of_date` or `known: false`.** The query is a substitute
   for re-deriving behaviour, never for reading code nobody has reasoned about.

## What this is not

Not a code index. It knows nothing about imports, call graphs, or where a handler lives, because nobody
reasoned about those. Pair it with an ordinary symbol index; expect it to answer structural questions and
it will disappoint.

"""`ponens trace blame` — evidence per symbol (`git blame` for what a trace established).

For every code symbol a trace carries evidence about, the projection answers: what is the BEST standing
evidence for it, at what strength (ORACLE_SPEC v0.2 §1.2), is it still fresh (§18.3), which artifact
carries it, and which residuals hang off it. It is a read over what `enrich` already derives — no new
judgement — so `cl blame`, the GitHub Action's per-function lines and a desktop gutter all render the
same numbers.

Output (JSON):
  { "symbols": { "<symbol>": { "best": {...} | null, "results": [ {...}, ... ], "residuals": [ {...}, ... ] } },
    "unattributed": [ result ids with no symbol ] }

A `result` is { artifact_id, artifact_type, status, strength, freshness, oracle, producer_action_id }.
`best` is the strongest FRESH result (strength rank, then latest); with no fresh result, the strongest
result at all, flagged by its freshness. `freshness` is fresh | stale | detached | unknown.
"""
from __future__ import annotations

import json

from . import goals as goalops
from . import lineage
from . import oracles


# Result artifact types that speak ABOUT a symbol, and how to find that symbol.
_RESULT_TYPES = ("VerificationResult", "StateSpaceAnalysisResult", "ConformanceResult",
                 "CoSimulationResult", "Observation", "TestResult", "CommandResult", "UserApproval")

# Statuses that mean the result ESTABLISHED something (a refutation establishes a counterexample).
_ESTABLISHED = {"proved", "sat", "refuted", "completed", "passed", "observed", "matched", "approved", "done"}


def _payload(a):
    p = a.get("payload")
    return p if isinstance(p, dict) else {}


def _symbol_of(a, trace, by_id):
    """The symbol a result is about: its own target_symbol, its VerificationGoal's, or the single
    specific target its lineage names."""
    p = _payload(a)
    if p.get("target_symbol"):
        return p["target_symbol"]
    if a.get("artifact_type") == "VerificationResult":
        vg = by_id.get(p.get("goal_artifact_id"))
        if vg is None:
            vg = next((x for x in trace.get("artifacts", []) if x.get("artifact_type") == "VerificationGoal"
                       and _payload(x).get("goal_id") == p.get("goal_id")), None)
        if vg is not None and _payload(vg).get("target_symbol"):
            return _payload(vg)["target_symbol"]
    fp = oracles.fingerprint_of(p)
    if fp and fp.get("subject_ref") and a.get("artifact_type") not in ("Observation", "CommandResult"):
        return fp["subject_ref"]
    specific, _model = lineage._lineage_symbols(a.get("artifact_id"), trace)
    if len(specific) == 1:
        return next(iter(specific))
    return None


def _freshness_index(trace):
    """artifact id -> fresh | stale | detached | unknown, from what `enrich` derives: the reasoner-closure
    stale/detached residuals, and the any-oracle verdicts (incl. `unknown` for evidence whose subject
    cannot be re-read); plus the extension's hash-based `artifact_freshness` by ref."""
    idx = {}
    for r in goalops.stale_evidence(trace):
        tgt = r.get("target") or {}
        if tgt.get("target_type") == "artifact" and tgt.get("target_id"):
            idx[tgt["target_id"]] = "detached" if r.get("kind") == "detached_evidence" else "stale"
    for aid, v in goalops.generic_evidence_freshness(trace)["verdicts"].items():
        idx.setdefault(aid, v)
    ext = trace.get("artifact_freshness") or {}
    return idx, ext


def _freshness_of(aid, idx, ext, payload):
    if aid in idx:
        return idx[aid]
    for ref, v in ext.items():
        if aid == ref or (isinstance(aid, str) and aid.startswith(str(ref) + "-")):
            if v in ("stale", "gone", "modified"):
                return "stale"
            if v == "fresh":
                return "fresh"
    fp = oracles.fingerprint_of(payload)
    if fp is None:
        # No fingerprint at all: a reasoner result is judged by the closure path above (absent → fresh
        # under the 1.7 heuristic); anything else cannot be re-read.
        return "fresh" if payload.get("engine") or payload.get("goal_artifact_id") else "unknown"
    return "fresh"


def blame(trace):
    arts = trace.get("artifacts", []) or []
    by_id = {a.get("artifact_id"): a for a in arts}
    idx, ext = _freshness_index(trace)
    symbols: dict[str, dict] = {}
    unattributed = []
    for a in arts:
        if a.get("artifact_type") not in _RESULT_TYPES or lineage.is_residual(a):
            continue
        p = _payload(a)
        status = str(p.get("status") or p.get("disposition") or "").lower()
        rec = {
            "artifact_id": a.get("artifact_id"),
            "artifact_type": a.get("artifact_type"),
            "status": status or None,
            "strength": oracles.strength_of(p),
            "freshness": _freshness_of(a.get("artifact_id"), idx, ext, p),
            "oracle": (oracles.attribution_of(p) or {}).get("id"),
            "producer_action_id": a.get("producer_action_id"),
            "established": status in _ESTABLISHED,
        }
        # A counterexample sits at the payload top level (SDK oracles) or under the spec's §10.4
        # `result.refuted` variant (the CodeLogician exporter).
        cex = p.get("counterexample")
        if not cex and isinstance(p.get("result"), dict):
            ref = p["result"].get("refuted")
            cex = ref.get("counterexample") if isinstance(ref, dict) else (ref if isinstance(ref, str) else None)
        if cex:
            rec["counterexample"] = cex
        sym = _symbol_of(a, trace, by_id)
        if not sym:
            unattributed.append(rec["artifact_id"])
            continue
        symbols.setdefault(sym, {"best": None, "results": [], "residuals": []})["results"].append(rec)

    # Residuals anchored to a symbol's results: a Residual artifact hangs off them by `derived_from`
    # (§13.1); the legacy list / payload name them in `target` / `related_artifact_ids`.
    result_sym = {r["artifact_id"]: s for s, e in symbols.items() for r in e["results"]}
    anchors = {}
    for a in arts:
        if lineage.is_residual(a):
            anchors[a.get("artifact_id")] = set(a.get("derived_from") or [])
    for r in lineage.residual_surface(trace):
        if str(r.get("status") or "open").lower() != "open":
            continue
        ids = set(r.get("related_artifact_ids") or []) | anchors.get(r.get("residual_id"), set())
        tgt = (r.get("target") or {}).get("target_id")
        if tgt:
            ids.add(tgt)
        hit = {result_sym[i] for i in ids if i in result_sym}
        if not hit and tgt in symbols:
            hit = {tgt}
        for s in hit:
            symbols[s]["residuals"].append({"residual_id": r.get("residual_id"), "kind": r.get("kind"),
                                             "severity": r.get("severity"), "statement": r.get("statement")})

    def rank(rec):
        return (0 if rec["freshness"] == "fresh" else 1, 0 if rec["established"] else 1,
                oracles.strength_rank(rec["strength"]), -(rec["producer_action_id"] or 0))
    for e in symbols.values():
        e["results"].sort(key=rank)
        e["best"] = e["results"][0] if e["results"] else None
    return {"symbols": dict(sorted(symbols.items())), "unattributed": sorted(unattributed)}


_ICON = {"fresh": "", "stale": " ⚠ stale", "detached": " ✗ detached", "unknown": " ? unknown"}


def render(b) -> str:
    lines = []
    width = max((len(s) for s in b["symbols"]), default=6)
    for sym, e in b["symbols"].items():
        best = e["best"]
        if not best:
            lines.append(f"{sym:<{width}}  —")
            continue
        grade = best["strength"] or "unranked"
        st = best["status"] or "?"
        lines.append(f"{sym:<{width}}  {grade:<15} {st:<9}{_ICON.get(best['freshness'], '')}  "
                     f"{best['artifact_id']}" + (f"  ({best['oracle']})" if best.get("oracle") else "")
                     + (f"  · {len(e['residuals'])} open gap{'s' if len(e['residuals']) != 1 else ''}" if e["residuals"] else ""))
    if b["unattributed"]:
        lines.append(f"\n{len(b['unattributed'])} result(s) name no symbol: {', '.join(b['unattributed'][:6])}")
    return "\n".join(lines) if lines else "No evidence about any symbol."


def cmd_blame(args):
    from .trace import load_trace
    trace = load_trace(args.trace_file)
    b = blame(trace)
    if getattr(args, "symbol", None):
        b = {"symbols": {k: v for k, v in b["symbols"].items() if k in args.symbol}, "unattributed": []}
    if getattr(args, "json", False):
        print(json.dumps(b, indent=2, ensure_ascii=False))
    else:
        print(render(b))
    return 0


def register(trace_sub):
    p = trace_sub.add_parser("blame", help="Evidence per symbol: best standing result, its strength and freshness (git blame for what was established)")
    p.add_argument("trace_file")
    p.add_argument("--symbol", action="append", help="Only these symbols (repeatable)")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.set_defaults(func=cmd_blame)

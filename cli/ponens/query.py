"""Asking the record what it knows.

`overview` answers "where does this project stand". This answers "what do you already know about
`step`, and can I still believe it" — so an agent consults the record instead of re-deriving a
function's behaviour from source on every turn it needs it.

Two properties make that substitution safe, and both are enforced here rather than left to a caller:
freshness rides on every record, so a stale answer says so; and nothing is returned that was not
established, so absence is reported as absence rather than filled with something plausible.

Size is part of the contract. The point is to spend fewer tokens than reading the source, which an
interface that returns everything defeats. The index is ~25 tokens a symbol, the detail is a summary
until asked otherwise, and a truncated answer always says what it left out.

See spec/RECORD_QUERY_v0_1.md.  SPDX-License-Identifier: Apache-2.0
"""
import json
import os

from . import blame as blamemod
from .overview import (
    _lc, _payload, freshness_word, grade_of, gap_state, _SEV_RANK, _load_reqs, requirements,
    _trace_symbols,
)

# What an entry is backed by, in the five words' terms rather than the trace's artifact types.
_KIND = {
    "StateSpaceAnalysisResult": "decomposition",
    "Decomposition": "decomposition",
    "VerificationResult": "verification",
    "ConformanceResult": "conformance",
    "IMLModel": "model",
    "GeneratedTests": "tests",
}

DEFAULT_REGION_LIMIT = 20

# Syntax, not state: words that appear in every constraint and describe none of them.
_NOISE = {"not", "true", "false", "get", "fun", "let", "in", "if", "then", "else", "with", "match"}


def _regions_of(payload):
    """The region list, wherever this producer put it."""
    for key in ("regions", "decomposition", "cases"):
        v = payload.get(key)
        if isinstance(v, list):
            return v
        if isinstance(v, dict) and isinstance(v.get("regions"), list):
            return v["regions"]
    return []


def _region_rec(r, i):
    if not isinstance(r, dict):
        return {"id": str(i + 1), "constraints": [], "invariant": None}
    cons = r.get("constraints") or r.get("constraints_str") or []
    if isinstance(cons, str):
        cons = [cons]
    inv = r.get("invariant") or r.get("invariant_str") or r.get("expected")
    out = {
        "id": str(r.get("id") or r.get("label_path") or (i + 1)),
        "constraints": [str(c) for c in cons],
        "invariant": str(inv) if inv is not None else None,
    }
    w_in, w_out = r.get("input") or r.get("model_str"), r.get("expected") or r.get("model_eval_str")
    if w_in is not None or w_out is not None:
        out["witness"] = {"input": w_in, "output": w_out}
    return out


def _splits_on(regions):
    """Which variables the behaviour actually turns on — the three lines that answer most questions
    without returning a single region. Taken from how often a name appears across constraints."""
    import re
    seen = {}
    for r in regions:
        for c in r.get("constraints") or []:
            # A variable or field path, not a constructor: `s.order.shipped` and `a.c` are what the
            # behaviour turns ON; `Cancel`, `Reserve`, `Some` are values it is compared AGAINST, and
            # listing those tells a reader nothing about the shape of the function.
            for name in re.findall(r"\b[a-z_][\w]*(?:\.[A-Za-z_]\w*)*", str(c)):
                head = name.split(".")[0]
                if head in _NOISE:
                    continue
                seen[name] = seen.get(name, 0) + 1
    ranked = sorted(seen.items(), key=lambda kv: (-kv[1], kv[0]))
    return [n for n, _ in ranked[:6]]


def _outcomes(regions):
    labels, seen = [], set()
    for r in regions:
        inv = r.get("invariant")
        if not inv:
            continue
        key = str(inv)[:120]
        if key not in seen:
            seen.add(key)
            labels.append(key)
    return labels


def _entries_for(trace):
    """symbol → the result records the record holds for it, newest first, with kind and regions."""
    b = blamemod.blame(trace)
    # Where each symbol actually lives, from the SourceCode artifacts. A result record names the MODEL
    # it ran on, which for a decomposition is a .iml — true, and not what a reader means by "where".
    declared = {}
    for f, syms in (_trace_symbols(trace) or {}).items():
        for sname in syms:
            declared.setdefault(sname, f)

    def _source_of(a, p, depth=0):
        """The SOURCE file behind a result. A result names the artifact it ran against rather than a
        path — `target_artifact_id` for a conformance, `derived_from` otherwise — so follow the link
        until a SourceCode artifact turns up. Bounded, because `derived_from` is a graph."""
        if depth > 3 or not isinstance(a, dict):
            return None
        if a.get("artifact_type") == "SourceCode":
            return (_payload(a).get("path") or a.get("name"))
        nxt = p.get("target_artifact_id") or p.get("source_artifact_id")
        links = [nxt] if nxt else []
        df = a.get("derived_from")
        links += df if isinstance(df, list) else ([df] if df else [])
        for lid in links:
            nb = arts.get(lid)
            if nb:
                got = _source_of(nb, _payload(nb), depth + 1)
                if got:
                    return got
        return None
    arts = {a.get("artifact_id"): a for a in (trace.get("artifacts") or [])}
    out = {}
    for sym, e in (b.get("symbols") or {}).items():
        recs = []
        for r in e.get("results") or []:
            a = arts.get(r.get("artifact_id")) or {}
            p = _payload(a)
            kind = _KIND.get(a.get("artifact_type") or "", None)
            regions = _regions_of(p)
            rec = {
                "kind": kind or _lc(a.get("artifact_type") or "") or "result",
                "grade": grade_of(r.get("strength")),
                "status": r.get("status"),
                "freshness": freshness_word(r.get("freshness")),
                "ref": a.get("ref") or r.get("artifact_id"),
                "artifact_id": r.get("artifact_id"),
                "file": p.get("path") or p.get("file") or _source_of(a, p),
                "at": a.get("created_at") or a.get("when"),
            }
            if regions:
                rec["regions"] = len(regions)
                rec["_regions"] = regions
            # The conformance counts sit at the payload top level for this producer, under `fidelity`
            # for others. Take either, so `--where diverged` works whoever wrote the record.
            fid = p.get("fidelity") if isinstance(p.get("fidelity"), dict) else p
            for k, into in (("total", "total"), ("regions_total", "total"), ("diverged", "diverged"), ("raised", "raised")):
                if k in fid and fid[k] is not None:
                    rec[into] = fid[k]
            if p.get("complete") is not None:
                rec["complete"] = bool(p["complete"])
            ref = p.get("reference_artifact_id") or (p.get("reference") or {}).get("entry") if isinstance(p.get("reference"), dict) else p.get("reference_artifact_id")
            if ref:
                rec["reference"] = ref
            recs.append(rec)
        recs.sort(key=lambda r: (r.get("at") or "", r.get("artifact_id") or ""), reverse=True)
        # A decomposition names the MODEL it decomposed, not the source it came from. Take the file from
        # whichever record does name one, newest first, so the index says where the symbol lives rather
        # than which .iml happened to be on disk.
        src = declared.get(sym) or next((r["file"] for r in recs if r.get("file") and not str(r["file"]).endswith(".iml")), None)
        if src:
            for r in recs:
                r.setdefault("_source", src)
        out[sym] = {"results": recs, "gaps": e.get("residuals") or [], "best": e.get("best"), "file": src}
    return out


def _headline(ent):
    """The record that speaks for a symbol: the one `blame` picked, else the newest.

    One function because there are two views of a symbol - the index row and the detail header - and
    they have to agree. They did not: the index was moved to the best result while the detail header
    kept reading `recs[0]`, so the same trace reported `proved · fresh` in a list and `unknown` at the
    top of the page describing that very symbol. `blame` already ranks; neither view ranks again.
    """
    recs = ent["results"]
    best = ent.get("best") or {}
    return next((r for r in recs if r.get("artifact_id") and r["artifact_id"] == best.get("artifact_id")),
                recs[0])


def symbols(trace, reqs=None, cwd=None):
    """The index: one record per symbol the record knows anything about. Enough to decide whether to
    ask a second question, never enough to answer one.

    The row describes the symbol's BEST result, not its latest one - `blame`'s own choice: the strongest
    FRESH result, or, when none is fresh, the strongest there is, carrying its own freshness. Latest-wins
    was the earlier rule and it read badly: running a test suite against a function that had been PROVED
    moved the row from `proved · proof` to `tested · tests`, so the strongest thing known about a symbol
    became invisible the moment anything weaker happened afterwards, and the index contradicted `blame`
    about the same trace. A later run does not retract an earlier proof.

    History is still not what an index is for - `trace symbol <name>` lists every record, newest first."""
    ent = _entries_for(trace)
    req_of = {}
    if reqs:
        for r in (requirements(trace, reqs, cwd=cwd) or {}).get("requirements") or []:
            for s in r.get("symbols") or []:
                name = s.get("symbol") if isinstance(s, dict) else s
                if name:
                    req_of[str(name)] = r.get("id")
    rows, counts = [], {"fresh": 0, "out_of_date": 0, "unknown": 0}
    for sym in sorted(ent):
        recs = ent[sym]["results"]
        if not recs:
            continue
        top = _headline(ent[sym])
        counts[top["freshness"]] = counts.get(top["freshness"], 0) + 1
        row = {
            "symbol": sym,
            "file": ent[sym].get("file") or top.get("file"),
            "kind": top["kind"],
            "grade": top["grade"],
            "freshness": top["freshness"],
            "gaps": len(ent[sym]["gaps"]),
            "requirement": req_of.get(sym),
            "ref": top["ref"],
            "established_at": top.get("at"),
        }
        # ANY record's region count, not just the newest one's. A decomposition is a one-time fact about
        # a symbol; a test run recorded after it does not retract it. Reading only `top` meant the count
        # showed up if and only if the decomposition happened to be the last thing recorded - so the same
        # symbol reported `regions=None` here and `2 regions` from `trace symbol`, which searches all
        # records (below). Two views of one trace disagreeing is worse than either answer.
        n_regions = next((r["regions"] for r in recs if r.get("regions")), None)
        if n_regions:
            row["regions"] = n_regions
        rows.append(row)
    return {"symbols": rows, "summary": {"symbols": len(rows), **counts}}


def symbol(trace, name, regions=False, where=None, limit=DEFAULT_REGION_LIMIT):
    """What is actually known about one symbol. Summary unless `regions` is asked for — and a
    truncated region list always says what it left out."""
    ent = _entries_for(trace).get(name)
    if not ent or not ent["results"]:
        return {"symbol": name, "known": False}

    recs = ent["results"]
    top = _headline(ent)
    with_regions = next((r for r in recs if r.get("_regions")), None)
    regs = [_region_rec(r, i) for i, r in enumerate(with_regions["_regions"])] if with_regions else []

    if regions:
        picked = [r for r in regs if _matches(r, where, recs)] if where else regs
        n = max(0, int(limit or 0)) or len(picked)
        complete = bool((with_regions or {}).get("complete", True))
        return {
            "symbol": name,
            "complete": complete,
            "bound": (with_regions or {}).get("bound"),
            "total": len(regs),
            "matched": len(picked),
            "returned": min(n, len(picked)),
            "regions": picked[:n],
        }

    evidence = [{k: v for k, v in r.items() if not k.startswith("_")} for r in recs[:4]]
    return {
        "symbol": name,
        "file": ent.get("file") or top.get("file"),
        "freshness": {"state": top["freshness"], "derived_from": ent.get("file") or top.get("file")},
        "evidence": evidence,
        "shape": {"splits_on": _splits_on(regs), "outcomes": len(_outcomes(regs))} if regs else None,
        "gaps": [
            {"id": g.get("residual_id") or g.get("id"), "state": gap_state(g.get("kind"), g.get("status")),
             "severity": g.get("severity"), "statement": g.get("statement")}
            for g in sorted(ent["gaps"], key=lambda g: _SEV_RANK.get(_lc(g.get("severity")), 9))[:6]
        ],
    }


def _matches(region, where, recs):
    """`--where`: a substring over constraints and invariant, or one of the named filters."""
    w = (where or "").strip()
    if not w:
        return True
    if w.startswith("outcome:"):
        return (region.get("invariant") or "").find(w[len("outcome:"):].strip()) >= 0
    if w in ("diverged", "raised"):
        return any(r.get(w if w == "diverged" else "raised") for r in recs)
    hay = " ".join(region.get("constraints") or []) + " " + (region.get("invariant") or "")
    return w.lower() in hay.lower()


# ---------------------------------------------------------------------------- rendering + CLI

def render_symbols(res):
    rows = res.get("symbols") or []
    if not rows:
        return "Nothing has been established about any symbol in this record."
    w = max(len(r["symbol"]) for r in rows)
    out = []
    for r in rows:
        bits = [r["kind"], r["grade"]]
        if r.get("regions"):
            bits.insert(1, "%d regions" % r["regions"])
        if r["freshness"] != "fresh":
            bits.append(r["freshness"].replace("_", " "))
        if r.get("gaps"):
            bits.append("%d gap%s" % (r["gaps"], "" if r["gaps"] == 1 else "s"))
        out.append("%s  %s  #%s" % (r["symbol"].ljust(w), " · ".join(bits), r["ref"]))
    s = res.get("summary") or {}
    out.append("")
    out.append("%d symbol(s) · %d fresh · %d out of date" % (s.get("symbols", 0), s.get("fresh", 0), s.get("out_of_date", 0)))
    return "\n".join(out)


def render_symbol(res):
    if res.get("known") is False:
        return "Nothing is known about `%s` — read the source." % res["symbol"]
    if "regions" in res:
        head = "%s: %d region(s)%s" % (
            res["symbol"], res["total"],
            "" if res.get("complete", True) else " (bounded to depth %s — NOT exhaustive)" % res.get("bound"))
        lines = [head + (", showing %d of %d matched" % (res["returned"], res["matched"]) if res["returned"] < res["matched"] else "")]
        for r in res["regions"]:
            lines.append("  %s: %s" % (r["id"], " ∧ ".join(r["constraints"]) or "(no constraints)"))
            if r.get("invariant"):
                lines.append("      → %s" % r["invariant"])
        return "\n".join(lines)
    lines = ["%s (%s)" % (res["symbol"], res.get("file") or "?"),
             "  freshness  %s" % res["freshness"]["state"].replace("_", " ")]
    for e in res.get("evidence") or []:
        lines.append("  %-10s %s%s  #%s" % (e["kind"], e["grade"],
                                            "" if e["freshness"] == "fresh" else " (%s)" % e["freshness"].replace("_", " "),
                                            e["ref"]))
    sh = res.get("shape")
    if sh:
        lines.append("  splits on  %s" % ", ".join(sh["splits_on"]))
        lines.append("  outcomes   %d" % sh["outcomes"])
    for g in res.get("gaps") or []:
        lines.append("  gap        %s (%s) %s" % (g["state"], g["severity"], (g["statement"] or "")[:90]))
    return "\n".join(lines)


def cmd_symbols(args):
    from .trace import load_trace
    reqs = _load_reqs(getattr(args, "file", None))
    cwd = getattr(args, "cwd", None) or (os.path.dirname(os.path.abspath(args.file)) if getattr(args, "file", None) else None)
    res = symbols(load_trace(args.trace_file), reqs, cwd=cwd)
    print(json.dumps(res, indent=2, ensure_ascii=False) if args.json else render_symbols(res))
    return 0


def cmd_symbol(args):
    from .trace import load_trace
    res = symbol(load_trace(args.trace_file), args.symbol,
                 regions=bool(getattr(args, "regions", False)),
                 where=getattr(args, "where", None),
                 limit=getattr(args, "limit", DEFAULT_REGION_LIMIT))
    print(json.dumps(res, indent=2, ensure_ascii=False) if args.json else render_symbol(res))
    return 0 if res.get("known") is not False else 0


def register(trace_sub):
    p = trace_sub.add_parser("symbols", help="The index: every symbol the record knows something about, with its grade and freshness — small enough to carry in a prompt")
    p.add_argument("trace_file")
    p.add_argument("--file", help="A requirements file, to name the requirement each symbol serves")
    p.add_argument("--cwd", help="Repository root the requirements' files are relative to")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.set_defaults(func=cmd_symbols)

    p = trace_sub.add_parser("symbol", help="What is known about one symbol, and whether it is still true")
    p.add_argument("trace_file")
    p.add_argument("symbol")
    p.add_argument("--regions", action="store_true", help="Return the region map instead of the summary")
    p.add_argument("--where", help="Narrow the regions: a substring, or outcome:<label> / diverged / raised")
    p.add_argument("--limit", type=int, default=DEFAULT_REGION_LIMIT, help="Most regions to return (default 20)")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.set_defaults(func=cmd_symbol)

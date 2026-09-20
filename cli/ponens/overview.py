"""`ponens trace requirements` / `overview` / `integrity` — where a record stands, in five words.

RECORD_OVERVIEW v0.1: every renderer (a terminal, an agent, a desktop, a PR comment) reads ONE JSON
and never re-derives semantics. The formal terms stay in the record (artifact, residual, policy,
conformance, reference artifact, acceptance item); this module fixes how they are READ:

    requirement   what the code must satisfy     met · open · failed · out_of_date
    evidence      what shows it does             proved · witnessed · tested · checked · attested; fresh · out_of_date · unknown
    gap           what is missing or assumed     missing · assumed · failed · out_of_date
    record        the trace                      (health)
    gate          the verdict over all of it     pass · blocked

plus `model` for what a requirement points at (the reference artifact).

Everything here is a read over what `goals.enrich`, `goals.next_steps`, `goals.stale_evidence` and
`blame.blame` already derive — no new freshness or resolution judgement.
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys

from . import blame as blameops
from . import goals as goalops
from . import lineage
from . import oracles

# ── vocabulary ────────────────────────────────────────────────────────────────────────────────────

GRADE = {"proof": "proved", "sat": "witnessed", "tests": "tested", "static_analysis": "checked", "attested": "attested"}
STRENGTH_OF_GRADE = {v: k for k, v in GRADE.items()}
GRADES = tuple(GRADE[s] for s in oracles.EVIDENCE_STRENGTH)          # strongest first

_REQ_RANK = {"met": 0, "open": 1, "out_of_date": 2, "failed": 3}     # worst wins
_SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
_FAILED = {"failed", "refuted"}


def grade_of(strength):
    """Evidence strength (the ladder in the record) → the grade a person reads; `unranked` otherwise."""
    return GRADE.get(strength, "unranked") if strength else "unranked"


def grade_at_least(grade, required):
    """Grade `grade` meets `required` on the ladder (unranked never does)."""
    if grade not in GRADES or required not in GRADES:
        return False
    return GRADES.index(grade) <= GRADES.index(required)


def freshness_word(f):
    if f == "fresh":
        return "fresh"
    if f in ("stale", "detached", "gone", "modified"):
        return "out_of_date"
    return "unknown"


def gap_state(kind, status=None):
    """A residual's kind → the gap state a person reads."""
    k = (kind or "").lower()
    if k in ("stale_evidence", "detached_evidence", "needs_rereasoning"):
        return "out_of_date"
    if k in ("assumption", "limitation"):
        return "assumed"
    if k == "defeater":
        return "failed"
    return "missing"        # open_question · unverified · coverage_regression · unknown kinds


def _lc(s):
    return str(s or "").lower()


def _payload(a):
    p = a.get("payload") if isinstance(a, dict) else None
    return p if isinstance(p, dict) else {}


# ── the requirements file (the agent's bindings.yaml) ─────────────────────────────────────────────

def load_requirements_file(path):
    """The requirements file as a dict. JSON is read with the standard library; YAML needs pyyaml, and a
    YAML file that happens to be JSON (YAML is a superset) is read either way, so a repository that keeps
    everything in JSON needs no YAML parser at all."""
    with open(path) as f:
        text = f.read()
    if path.endswith(".json"):
        data = json.loads(text)
    else:
        try:
            data = json.loads(text)                 # a .yaml file holding JSON: no pyyaml needed
        except ValueError:
            import yaml
            data = yaml.safe_load(text)
    return data if isinstance(data, dict) else {}


def _requirements_of(reqs):
    """The normalized requirement records of a requirements file dict (`bindings:` or `requirements:`)."""
    if not isinstance(reqs, dict):
        return []
    items = reqs.get("bindings")
    if items is None:
        items = reqs.get("requirements")
    out = []
    for b in items or []:
        if not isinstance(b, dict) or not b.get("id") or not b.get("entry"):
            continue
        conf = b.get("conformance") if isinstance(b.get("conformance"), dict) else {}
        strength = conf.get("strength") or "tests"
        out.append({
            "id": str(b["id"]), "entry": str(b["entry"]),
            "version": str(b["version"]) if b.get("version") is not None else None,
            "kind": conf.get("kind") or "refinement",
            "strength": strength if strength in oracles.EVIDENCE_STRENGTH else "tests",
            "code": [c for c in (b.get("code") or []) if isinstance(c, dict) and c.get("file")],
            "interpretation": b.get("interpretation") if isinstance(b.get("interpretation"), dict) else None,
            "invariants": [str(x) for x in (b.get("invariants") or [])],
        })
    return out


def entry_ref(r):
    """The entry as the trace cites it: `<entry>@<version>` (a scheme-prefixed entry stays as is)."""
    return r["entry"] + ("@" + r["version"] if r.get("version") else "")


def reference_id(r):
    return "ref:" + entry_ref(r)


def goal_id(r):
    return "binding:" + r["id"]


def item_id(r, symbol=None):
    return "binding:%s:%s" % (r["id"], symbol if symbol else "project")


def reading_residual_id(r):
    return "binding:%s:interpretation" % r["id"]


def _pairs(r):
    """(file, symbol, entry_symbol) per named code symbol; empty for a project-level requirement."""
    out = []
    for c in r["code"]:
        syms = c.get("symbols") or []
        maps = c.get("maps_to") or None
        for i, s in enumerate(syms):
            es = (maps[0] if len(maps) == 1 else (maps[i] if i < len(maps) else s)) if maps else s
            out.append((str(c["file"]), str(s), str(es)))
    return out


# ── sources ───────────────────────────────────────────────────────────────────────────────────────

_DEF_PATTERNS = {
    ".py": lambda s: [r"^\s*(async\s+)?def\s+%s\s*\(" % s, r"^\s*class\s+%s\b" % s],
    ".ts": lambda s: [r"\bfunction\s+%s\s*[<(]" % s, r"\b(const|let|var)\s+%s\s*[=:]" % s, r"\bclass\s+%s\b" % s, r"^\s+(async\s+)?%s\s*\(" % s],
}
_DEF_PATTERNS[".js"] = _DEF_PATTERNS[".tsx"] = _DEF_PATTERNS[".jsx"] = _DEF_PATTERNS[".mjs"] = _DEF_PATTERNS[".ts"]


def _trace_symbols(trace):
    """file → symbols the trace's SourceCode artifacts list."""
    out = {}
    for a in trace.get("artifacts", []) or []:
        if a.get("artifact_type") != "SourceCode":
            continue
        p = _payload(a)
        file = p.get("path") or a.get("name")
        if not file:
            continue
        for s in p.get("symbols") or []:
            n = s if isinstance(s, str) else (s.get("name") if isinstance(s, dict) else None)
            if n:
                out.setdefault(str(file), set()).add(n)
    return out


def _bound(file, symbol, cwd, trace_syms):
    """True/False when the symbol's definition can (not) be found; None when the file is missing or
    the language unknown. A SourceCode artifact listing the symbol for that file also binds it."""
    if symbol in trace_syms.get(file, set()):
        return True
    if not cwd:
        return None
    path = os.path.join(cwd, file)
    ext = os.path.splitext(path)[1].lower()
    if ext not in _DEF_PATTERNS or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            src = f.read()
    except OSError:
        return None
    pats = _DEF_PATTERNS[ext](re.escape(symbol))
    return any(re.search(p, src, re.M) for p in pats)


def _ref_stale_index(trace):
    """artifact id → True when a derived stale-ref / detached-ref residual targets it."""
    out = {}
    for r in goalops.reference_freshness(trace):
        tgt = (r.get("target") or {}).get("target_id")
        if tgt:
            out[tgt] = True
    return out


def _evidence_rec(a, freshness):
    p = _payload(a)
    return {
        "artifact_id": a.get("artifact_id"),
        "grade": grade_of(oracles.strength_of(p)),
        "status": _lc(p.get("status")) or None,
        "freshness": freshness,
        "oracle": (oracles.attribution_of(p) or {}).get("id"),
        "producer_action_id": a.get("producer_action_id"),
        "counterexample": p.get("counterexample") or (p.get("result") or {}).get("refuted") if isinstance(p.get("result"), dict) else p.get("counterexample"),
    }


def _conformance_lookup(trace, blame_out):
    """(reference id, entry symbol?, code symbol?) → the LATEST ConformanceResult against that reference
    whose stamped symbols match, graded, with freshness from the reasoner projection; None when nothing."""
    arts = [a for a in (trace.get("artifacts") or []) if a.get("artifact_type") == "ConformanceResult"]
    fresh = {}
    for e in (blame_out or {}).get("symbols", {}).values():
        for r in e.get("results", []):
            fresh[r["artifact_id"]] = r.get("freshness")
    stale_ref = _ref_stale_index(trace)

    def look(ref_id, entry_symbol=None, code_symbol=None):
        cands = []
        for a in arts:
            p = _payload(a)
            if str(p.get("reference_artifact_id") or "") != ref_id:
                continue
            if entry_symbol is not None and p.get("entry_symbol") is not None and str(p["entry_symbol"]) != entry_symbol:
                continue
            if code_symbol is not None and p.get("target_symbol") is not None:
                ts = str(p["target_symbol"])
                if ts != code_symbol and not ts.startswith(code_symbol + "_"):
                    continue
            cands.append(a)
        if not cands:
            return None
        a = max(cands, key=lambda x: (x.get("producer_action_id") or 0))
        aid = a.get("artifact_id")
        if stale_ref.get(aid):
            f = "out_of_date"
        else:
            f = freshness_word(fresh.get(aid)) if aid in fresh else "unknown"
        return _evidence_rec(a, f)
    return look


def _declared_index(goals):
    """acceptance item id → status, over the trace's (enriched) goals."""
    out = {}
    for g in goals or []:
        for it in g.get("acceptance") or []:
            if it.get("id"):
                out[str(it["id"])] = _lc(it.get("status") or "todo")
    return out


def _model_index(trace):
    return {str(r.get("reference_artifact_id")): r for r in (trace.get("reference_artifacts") or []) if isinstance(r, dict)}


# ── requirements ──────────────────────────────────────────────────────────────────────────────────

def _row_state(bound, declared, ev, required_grade, file=None):
    """The seven rules, first that applies → (state, reason)."""
    if bound is False:
        return "open", "symbol not found in %s" % file
    if not declared:
        return "open", "not yet in the record"
    if ev is None:
        return "open", "no evidence yet"
    if ev.get("status") in _FAILED:
        cex = ev.get("counterexample")
        return "failed", (str(cex) if cex else "the last check failed")
    if ev.get("freshness") == "out_of_date":
        return "out_of_date", "the code or the model changed since"
    if ev.get("freshness") == "unknown":
        return "out_of_date", "freshness unknown"
    if not grade_at_least(ev.get("grade"), required_grade):
        return "open", "%s, needs %s" % (ev.get("grade"), required_grade)
    return "met", None


def _goal_requirements(enriched):
    """Every acceptance item of a goal NOT derived from the requirements file (goal ids not starting
    with `binding:`) is a requirement too: `<goal id>/<item id>`, no model, state from the resolved item."""
    out = []
    for g in enriched.get("goals") or []:
        gid = str(g.get("id") or "goal")
        if gid.startswith("binding:"):
            continue
        for it in g.get("acceptance") or []:
            if it.get("id") is None:
                continue
            st = _lc(it.get("status") or "todo")
            fresh = it.get("freshness")
            if st == "done":
                state, why = ("out_of_date", "the evidence is out of date") if fresh in ("stale", "detached", "gone") else ("met", None)
            elif st == "blocked":
                state, why = "failed", "evidence exists but is contested (a failed check or an open defeater)"
            elif st == "doing":
                state, why = "open", "in progress"
            else:
                state, why = "open", "no evidence yet"
            want = it.get("min_strength") or (it.get("evidence") or {}).get("strength") if isinstance(it.get("evidence"), dict) else it.get("min_strength")
            ev = None
            if it.get("evidence_ref"):
                ev = {"artifact_id": it["evidence_ref"], "grade": grade_of(it.get("evidence_strength")),
                      "status": None, "freshness": freshness_word(fresh) if fresh else ("fresh" if st == "done" else "unknown")}
            out.append({
                "id": "%s/%s" % (gid, it["id"]), "label": it.get("label") or str(it["id"]), "goal": gid, "item": it["id"],
                "model": None, "kind": it.get("kind"), "required_grade": grade_of(want) if want in oracles.EVIDENCE_STRENGTH else None,
                "required": it.get("required", True) is not False,
                "state": state, "reason": why, "evidence": ev, "symbols": [],
                "reading": {"state": "not_needed", "chosen": None, "approved_by": None}, "open_findings": [], "invariants": [],
            })
    return out


def _worst(states):
    return max(states, key=lambda s: _REQ_RANK.get(s, 0)) if states else "open"


def requirements(trace, reqs, cwd=None, enriched=None, blame_out=None):
    """RECORD_OVERVIEW §requirements: one row per requirement (+ one per named symbol), joined from the
    requirements file, the trace's goals, its reference artifacts, its conformance results and the
    reasoner freshness. Returns {"requirements": [...], "summary": {...}}."""
    recs = _requirements_of(reqs) if reqs is not None else []
    if enriched is None:
        enriched = goalops.enrich(copy.deepcopy(trace))
    if blame_out is None:
        blame_out = blameops.blame(trace)
    declared = _declared_index(enriched.get("goals") or trace.get("goals") or [])
    models = _model_index(trace)
    residual_ids = {r.get("residual_id") for r in lineage.residual_surface(enriched)}
    look = _conformance_lookup(trace, blame_out)
    trace_syms = _trace_symbols(trace)
    best_by_symbol = {s: e.get("best") for s, e in (blame_out or {}).get("symbols", {}).items()}

    out = []
    for r in recs:
        ref = reference_id(r)
        model = models.get(ref) or models.get("ref:" + r["entry"])
        required_grade = GRADE[r["strength"]]
        rows = []
        pairs = _pairs(r)
        if not pairs:
            ev = look(ref)
            st, why = _row_state(None, item_id(r) in declared, ev, required_grade)
            rows.append({"scope": "project", "file": ", ".join(c["file"] for c in r["code"]), "symbol": None,
                         "entry_symbol": r["entry"], "bound": None, "declared": item_id(r) in declared,
                         "state": st, "reason": why, "evidence": ev, "other_evidence": None})
        for file, sym, esym in pairs:
            bound = _bound(file, sym, cwd, trace_syms)
            ev = look(ref, esym, sym)
            other = best_by_symbol.get(sym) or best_by_symbol.get(sym + "_decomp")
            other_rec = None
            if other and (ev is None or other.get("artifact_id") != ev.get("artifact_id")):
                other_rec = {"artifact_id": other.get("artifact_id"), "grade": grade_of(other.get("strength")),
                             "status": other.get("status"), "freshness": freshness_word(other.get("freshness"))}
            st, why = _row_state(bound, item_id(r, sym) in declared, ev, required_grade, file)
            rows.append({"scope": "symbol", "file": file, "symbol": sym, "entry_symbol": esym, "bound": bound,
                         "declared": item_id(r, sym) in declared, "state": st, "reason": why,
                         "evidence": ev, "other_evidence": other_rec})

        # The model: pinned version vs the version the trace last saw of it.
        now_version = str(model.get("version")) if model and model.get("version") is not None else None
        if not r.get("version") or not now_version:
            model_status = "unknown"
        else:
            model_status = "current" if now_version == r["version"] else "revised"
        findings = list((_payload(model).get("findings") or []) if model else [])
        # The reading of the model's text, where it admits more than one.
        interp = r.get("interpretation")
        if interp:
            reading_state = "recorded" if reading_residual_id(r) in residual_ids else "chosen"
        else:
            reading_state = "missing" if findings else "not_needed"
        reading = {"state": reading_state,
                   "chosen": interp.get("chosen") if interp else None,
                   "approved_by": interp.get("approved_by") if interp else None}

        state = _worst([x["state"] for x in rows])
        reason = next((x["reason"] for x in rows if x["state"] == state and x["reason"]), None)
        if model_status == "revised":
            state, reason = "out_of_date", "the model was revised: %s → %s" % (r["version"], now_version)
        elif reading_state == "missing" and state == "met":
            state, reason = "open", "reading not chosen"
        evidence = rows[0]["evidence"] if len(rows) == 1 else None
        if evidence is None and rows and all(x["evidence"] for x in rows):
            # several symbols: the weakest evidence stands for the requirement
            evidence = min((x["evidence"] for x in rows), key=lambda e: -GRADES.index(e["grade"]) if e["grade"] in GRADES else 1)
        out.append({
            "id": r["id"], "label": (model or {}).get("name") or r["entry"],
            "model": {"entry": r["entry"], "name": (model or {}).get("name") or r["entry"], "version": r.get("version"),
                      "current_version": now_version, "status": model_status, "reference": ref},
            "kind": r["kind"], "required_grade": required_grade,
            "state": state, "reason": reason, "evidence": evidence,
            "symbols": rows, "reading": reading, "open_findings": findings, "invariants": r["invariants"],
        })
    out.extend(_goal_requirements(enriched))
    counts = {s: sum(1 for x in out if x["state"] == s) for s in ("met", "open", "failed", "out_of_date")}
    blocked_by = [x["id"] for x in out if x["state"] != "met"]
    summary = {"requirements": len(out), **counts, "gate": "pass" if not blocked_by else "blocked", "blocked_by": blocked_by}
    return {"requirements": out, "summary": summary}


# ── gaps · gate · next · evidence · record ────────────────────────────────────────────────────────

def gaps(enriched, blame_out=None):
    """Open residuals (declared + derived) as gaps, worst severity first."""
    sym_of = {}
    for s, e in (blame_out or {}).get("symbols", {}).items():
        for r in e.get("residuals", []):
            sym_of.setdefault(r.get("residual_id"), []).append(s)
    out = []
    for r in lineage.residual_surface(enriched):
        if _lc(r.get("status") or "open") != "open":
            continue
        out.append({
            "id": r.get("residual_id"), "state": gap_state(r.get("kind")), "severity": _lc(r.get("severity") or "medium"),
            "kind": r.get("kind"), "statement": r.get("statement"), "symbols": sorted(sym_of.get(r.get("residual_id"), [])),
            "suggested_check": r.get("suggested_check"), "derived": bool(r.get("derived")),
        })
    out.sort(key=lambda g: (_SEV_RANK.get(g["severity"], 2), str(g["id"])))
    return out


def gate(trace):
    """policy_evaluations → the gate: pass, or blocked by the error-severity rules that failed."""
    sev = {}
    for p in trace.get("policies") or []:
        if isinstance(p, dict):
            pid = p.get("policy_id") or p.get("name")
            if pid:
                sev[str(pid)] = _lc(p.get("severity") or "error")
    rules = []
    for e in trace.get("policy_evaluations") or []:
        if not isinstance(e, dict):
            continue
        pid = str(e.get("policy_id") or "")
        s = _lc(e.get("status"))
        severity = sev.get(pid, _lc(e.get("severity") or "error"))
        if s == "passed":
            state = "pass"
        elif s == "failed":
            state = "blocked" if severity == "error" else "warning"
        else:
            state = "unchecked"
        rules.append({"id": pid, "state": state, "severity": severity, "note": e.get("note") or e.get("message")})
    blocked = [r["id"] for r in rules if r["state"] == "blocked"]
    # How many policies the trace CARRIES, which is a different number from how many were evaluated:
    # `rules` comes from `policy_evaluations`, and nothing stamps those until `trace check --write`
    # runs. Without this the renderer cannot tell "there are no rules" from "the rules were never
    # run", and those two states need opposite advice.
    attached = len([p for p in (trace.get("policies") or []) if isinstance(p, dict)])
    return {"state": "blocked" if blocked else "pass", "blocked_by": blocked, "rules": rules,
            "attached": attached}


_NEXT_KIND = {"establish": "meet"}


def next_steps(trace, limit=None):
    """`goals.next_steps` in the five words: kinds fix · meet · refresh · gap · optional, the requirement
    id resolved from the goal id."""
    out = []
    for s in goalops.next_steps(trace, limit=limit):
        gid = s.get("goal_id")
        req = gid[len("binding:"):] if isinstance(gid, str) and gid.startswith("binding:") else None
        out.append({"kind": _NEXT_KIND.get(s["kind"], s["kind"]), "label": s.get("label"), "why": s.get("why"),
                    "suggested": s.get("suggested"), "requirement": req, "goal": gid, "item": s.get("item_id"),
                    "severity": s.get("severity")})
    return out


def evidence_summary(blame_out):
    by_symbol = {}
    counts = {g: 0 for g in GRADES}
    counts.update({"failed": 0, "out_of_date": 0, "unranked": 0})
    for s, e in (blame_out or {}).get("symbols", {}).items():
        b = e.get("best")
        if not b:
            continue
        g = grade_of(b.get("strength"))
        f = freshness_word(b.get("freshness"))
        by_symbol[s] = {"artifact_id": b.get("artifact_id"), "grade": g, "status": b.get("status"), "freshness": f,
                        "gaps": len(e.get("residuals") or [])}
        counts[g] = counts.get(g, 0) + 1
        if b.get("status") in _FAILED:
            counts["failed"] += 1
        if f == "out_of_date":
            counts["out_of_date"] += 1
    return {**counts, "by_symbol": by_symbol}


def record_health(trace):
    outcome = trace.get("outcome") if isinstance(trace.get("outcome"), dict) else {}
    return {
        "title": trace.get("title") or (trace.get("task") or {}).get("description") if isinstance(trace.get("task"), dict) else trace.get("title"),
        "trace_id": trace.get("trace_id"),
        "artifacts": len(trace.get("artifacts") or []),
        "actions": len(trace.get("actions") or []),
        "outcome": outcome.get("type"),
    }


def overview(trace, reqs=None, cwd=None):
    """RECORD_OVERVIEW §overview: one JSON with everything a screen shows."""
    enriched = goalops.enrich(copy.deepcopy(trace))
    blame_out = blameops.blame(trace)
    req = requirements(trace, reqs, cwd=cwd, enriched=enriched, blame_out=blame_out)
    g = gate(trace)
    gp = gaps(enriched, blame_out)
    return {
        "requirements": req["requirements"], "summary": req["summary"],
        "gaps": gp, "gate": g, "next": next_steps(trace),
        "evidence": evidence_summary(blame_out), "record": record_health(trace),
        "counts": {"gaps": {s: sum(1 for x in gp if x["state"] == s) for s in ("missing", "assumed", "failed", "out_of_date")}},
    }


# ── integrity ─────────────────────────────────────────────────────────────────────────────────────

def _evidence_index(trace):
    out = {}
    for a in (trace or {}).get("artifacts") or []:
        aid = a.get("artifact_id")
        if not aid:
            continue
        t = a.get("artifact_type")
        p = _payload(a)
        st = _lc(p.get("status"))
        if t == "ConformanceResult" and st == "passed":
            ref = str(p.get("reference_artifact_id") or "")
            out[aid] = {"type": t, "reference": ref if ref.startswith("ref:") else None}
        elif t == "VerificationResult" and st == "proved":
            out[aid] = {"type": t, "reference": None}
    for g in (trace or {}).get("goals") or []:
        gid = str(g.get("id") or "goal")
        for it in g.get("acceptance") or []:
            if it.get("id") is None:
                continue
            # EVERY criterion, not only the `done` ones. Indexing only what was already met missed the
            # loss that actually matters: delete the criteria you have NOT met and the goal reads
            # 100%. Measured on the Stripe demo - one unmet item dropped took it from 88% to 100% and
            # `integrity` reported nothing lost. A criterion that was asked for and is now absent is a
            # loss whatever state it was in; `done` vs `open again` is only the DETAIL below.
            out["goal:%s/%s" % (gid, it["id"])] = {
                "type": "goal", "reference": None, "done": _lc(it.get("status")) == "done"}
    return out


def integrity(before, after):
    """What established evidence in `before` is missing or weakened in `after`. A changed verdict under
    a new id is a new fact, not a loss; an empty `before` never loses anything."""
    was = _evidence_index(before)
    lost = []
    if not was:
        return {"ok": True, "lost": []}
    now = _evidence_index(after)
    for aid, e in was.items():
        n = now.get(aid)
        if e["type"] == "goal":
            if not n:
                # Gone entirely: the definition of done itself shrank. That is a different loss from a
                # met item going back to open, and the worse one - it changes what was being asked.
                lost.append({"id": aid[len("goal:"):], "what": "requirement item",
                             "reference": None, "detail": "is gone from the definition of done"})
            elif e["done"] and not n["done"]:
                lost.append({"id": aid[len("goal:"):], "what": "done requirement item",
                             "reference": None, "detail": "was done and is open again"})
            continue
        what = "met requirement" if e["type"] == "ConformanceResult" else "proof"
        if not n:
            lost.append({"id": aid, "what": what, "reference": e["reference"], "detail": "is gone"})
        elif e["reference"] and n.get("reference") != e["reference"]:
            lost.append({"id": aid, "what": what, "reference": e["reference"], "detail": "no longer cites " + e["reference"]})
    return {"ok": not lost, "lost": lost}


# ── renderers (plain text, the five words) ────────────────────────────────────────────────────────

def render_requirements(res):
    lines = []
    for r in res["requirements"]:
        ev = r.get("evidence")
        ev_txt = ("%s · %s" % (ev["grade"], ev["freshness"].replace("_", " "))) if ev else "no evidence"
        why = (" (" + r["reason"] + ")") if r.get("reason") else ""
        where = ("%s@%s" % (r["model"]["entry"], r["model"].get("version") or "?")) if r.get("model") else r.get("label", "")
        lines.append("%-12s %s  %s  %s%s" % (r["state"].replace("_", " "), r["id"], where, ev_txt, why))
        for s in r["symbols"]:
            if s["scope"] != "symbol":
                continue
            e = s.get("evidence")
            lines.append("    %-10s %s → %s  %s%s" % (s["state"].replace("_", " "), s["symbol"], s["entry_symbol"],
                                                    ("%s · %s" % (e["grade"], e["freshness"].replace("_", " "))) if e else "no evidence",
                                                    (" (" + s["reason"] + ")") if s.get("reason") else ""))
    s = res["summary"]
    parts = ["%d requirement%s" % (s["requirements"], "" if s["requirements"] == 1 else "s")]
    for k in ("met", "open", "failed", "out_of_date"):
        if s[k]:
            parts.append("%d %s" % (s[k], k.replace("_", " ")))
    parts.append("gate " + s["gate"])
    lines.append(" · ".join(parts))
    return "\n".join(lines)


def render_overview(o):
    out = []
    if o["requirements"]:
        out.append("Requirements")
        out.append(render_requirements({"requirements": o["requirements"], "summary": o["summary"]}))
        out.append("")
    out.append("Gaps" if o["gaps"] else "Gaps: none open")
    for g in o["gaps"]:
        out.append("  %-12s %-9s %s  [%s]" % (g["state"].replace("_", " "), g["severity"], (g.get("statement") or "").replace("\n", " "), g["id"]))
    out.append("")
    gt = o["gate"]
    # `pass` with no rules means nothing was ASKED, not that nothing failed - the state is right (no
    # policy blocked anything) and the bare word reads as an endorsement. A record with a refuted
    # property and a failing test suite printed "Gate: pass" with no qualification. The data already
    # said so (`rules: []`); only the line dropped it.
    gate_note = ""
    if not gt["rules"]:
        # Attached-but-unevaluated is NOT the same state as unattached, and it was reported as one:
        # a trace carrying eight policies said "no policies attached", sending a reader to go attach
        # policies it already had, when what it needed was for the checker to be run and stamped.
        n = gt.get("attached") or 0
        gate_note = (" (%d polic%s attached, none evaluated - run `ponens trace check --write`)"
                     % (n, "y" if n == 1 else "ies")) if n else \
                    " (no policies attached - nothing was checked)"
    elif gt["state"] == "pass":
        n = len(gt["rules"])
        gate_note = " (%d rule%s checked)" % (n, "" if n == 1 else "s")
    out.append("Gate: " + gt["state"]
               + ((" — " + ", ".join(gt["blocked_by"])) if gt["blocked_by"] else "")
               + gate_note)
    for r in gt["rules"]:
        out.append("  %-9s %-8s %s%s" % (r["state"], r["severity"], r["id"], ("  " + r["note"]) if r.get("note") else ""))
    out.append("")
    if o["next"]:
        out.append("Next")
        for i, s in enumerate(o["next"], 1):
            out.append("  %d. [%s] %s" % (i, s["kind"].upper(), s["label"]) + (("  (" + s["requirement"] + ")") if s.get("requirement") else ""))
            out.append("     why: " + str(s["why"]))
            out.append("     do:  " + str(s["suggested"]))
    else:
        out.append("Next: nothing to do — every requirement is met and no open gap has a suggested check.")
    return "\n".join(out)


def render_integrity(res):
    if res["ok"]:
        return "Record check: nothing would be lost."
    n = len(res["lost"])
    lines = ["Record check: this save would drop %d item%s of evidence the record already holds." % (n, "" if n == 1 else "s")]
    for l in res["lost"][:8]:
        lines.append("  - %s (%s%s) %s" % (l["id"], l["what"], (" against " + l["reference"]) if l.get("reference") else "", l["detail"]))
    if n > 8:
        lines.append("  - … and %d more" % (n - 8))
    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────────────────────────────────

def _load_reqs(path):
    if not path:
        return None
    if not os.path.exists(path):
        print("Error: requirements file not found: %s" % path, file=sys.stderr)
        sys.exit(1)
    try:
        return load_requirements_file(path)
    except ImportError:
        print("Error: YAML support needs PyYAML — `pip install pyyaml`.", file=sys.stderr)
        sys.exit(1)


def cmd_requirements(args):
    from .trace import load_trace
    trace = load_trace(args.trace_file)
    res = requirements(trace, _load_reqs(args.file) or {}, cwd=getattr(args, "cwd", None) or os.path.dirname(os.path.abspath(args.file)))
    print(json.dumps(res, indent=2, ensure_ascii=False) if args.json else render_requirements(res))
    return 0


def cmd_overview(args):
    from .trace import load_trace
    trace = load_trace(args.trace_file)
    reqs = _load_reqs(getattr(args, "file", None))
    cwd = getattr(args, "cwd", None) or (os.path.dirname(os.path.abspath(args.file)) if getattr(args, "file", None) else None)
    o = overview(trace, reqs, cwd=cwd)
    print(json.dumps(o, indent=2, ensure_ascii=False) if args.json else render_overview(o))
    return 0


def cmd_integrity(args):
    from .trace import load_trace
    res = integrity(load_trace(args.before), load_trace(args.after))
    print(json.dumps(res, indent=2, ensure_ascii=False) if args.json else render_integrity(res))
    return 0 if res["ok"] else 3


def register(trace_sub):
    p = trace_sub.add_parser("requirements", help="Where each requirement stands (met · open · failed · out of date) against its model, from a requirements file")
    p.add_argument("trace_file")
    p.add_argument("--file", required=True, help="The requirements file (bindings.yaml / .json)")
    p.add_argument("--cwd", help="Repository root the requirements' files are relative to (default: the file's directory)")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.set_defaults(func=cmd_requirements)

    p = trace_sub.add_parser("overview", help="Where the record stands, in five words: requirements · gaps · gate · next · evidence — one JSON for every screen")
    p.add_argument("trace_file")
    p.add_argument("--file", help="A requirements file (bindings.yaml / .json) to include")
    p.add_argument("--cwd", help="Repository root the requirements' files are relative to")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.set_defaults(func=cmd_overview)

    p = trace_sub.add_parser("integrity", help="What established evidence in BEFORE is gone or weakened in AFTER (exit 3 when something is lost)")
    p.add_argument("before")
    p.add_argument("after")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.set_defaults(func=cmd_integrity)

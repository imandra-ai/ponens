"""Goal operations over a trace: acceptance resolution, stale-evidence, the relevance cone, enrich.

A goal lives in the trace as `trace.goals[]` (intent + scope + acceptance items). These functions are
the trace-level logic that used to live in the desktop app's TypeScript (goalResolve / staleness /
goalSlice); keeping it here means the coding agent stays a thin viewer and ponens owns the reasoning
over the trace.

Goal shape (in the trace):
    {id, intent, scope: [str], status, acceptance: [item, ...]}
Acceptance item:
    {id, kind: change|property|gap|obligation, label, status, binding: {...}}
Bindings (snake_case, matching the rest of the trace):
    change: {symbol, file?}   property: {symbol?, property?}   gap: {residual_id}   obligation: {policy_id}
"""

import copy

from . import lineage  # artifact provenance primitive — dependency-free, no import cycle


def _lc(s):
    return str(s if s is not None else "").lower()


def _payload(a):
    return (a or {}).get("payload") or {}


def _binding(item):
    return (item or {}).get("binding") or {}


def _vg_matches(vg, sym, prop):
    """Does a VerificationGoal match a `property` binding {symbol?, property?}?

    The property keyword (if given) must appear in the goal's description. The symbol (if given)
    must equal the goal's `target_symbol` -- BUT when the goal carries no `target_symbol` (the common
    case for check_vg-recorded goals, which describe the property, not the code symbol), we cannot
    disqualify on symbol and instead rely on the property keyword having pinned the match."""
    payload = _payload(vg)
    if prop and _lc(prop) not in _lc(payload.get("description")):
        return False
    if not sym:
        return True
    tsym = payload.get("target_symbol")
    if tsym:
        return tsym == sym
    # No target_symbol to check against: accept only if a property keyword already pinned it.
    return bool(prop)


# ================================================================
# Acceptance resolution (was goalResolve.ts)
# ================================================================

# --- Goal Contract v0.1 §4: typed criteria resolved by artifact LINEAGE (not description text) ------

def _property_matches(vg, prop):
    """Does a VerificationGoal establish the named property? Prefers the STRUCTURED `property_name`
    (exact), then `goal_id`, then a description-keyword match (transitional, until `DefineVG` records
    `property_name`). The component is matched separately by lineage, so this only disambiguates
    among a single component's own goals — much safer than the old whole-trace keyword search."""
    if not prop:
        return True
    p = _payload(vg)
    pn = p.get("property_name")
    if pn:
        return _lc(pn) == _lc(prop)
    if _lc(p.get("goal_id")) == _lc(prop):
        return True
    return _lc(prop) in _lc(p.get("description"))


# What engine verdict satisfies each `expect` (Goal Contract evidence.expect).
_EXPECT = {
    "proved":   {"done": ("proved", "sat"), "blocked": ("refuted",)},
    "refuted":  {"done": ("refuted",), "blocked": ("proved", "sat")},
    "explored": {"done": ("proved", "sat", "refuted", "unknown"), "blocked": ()},
}


def _verdict_for_expect(status, expect):
    m = _EXPECT.get(expect, _EXPECT["proved"])
    if status in m["done"]:
        return "done"
    if status in m["blocked"]:
        return "blocked"
    return "doing"


def _resolve_typed(item, trace):
    """Resolve a typed criterion (`component` + `evidence`) by lineage. Returns a resolution dict, or
    None if the item is not a typed criterion (caller falls back to the legacy binding path)."""
    comp = item.get("component") or {}
    comp = comp.get("function") or comp.get("function_") or comp.get("symbol")
    ev = item.get("evidence") or {}
    kind = _lc(ev.get("kind"))
    if not comp or not kind:
        return None
    keep = {"status": item.get("status", "todo"), "from_trace": False, "evidence": None}
    arts = trace.get("artifacts", [])

    def rooted(a):
        return lineage.roots_in_component(a.get("artifact_id"), comp, trace)

    if kind == "verification":
        prop = ev.get("property")
        expect = _lc(ev.get("expect") or "proved")
        # VGs targeting this component, against an AUTOFORMALIZED model, establishing the property.
        vgs = [a for a in arts if a.get("artifact_type") == "VerificationGoal"
               and rooted(a) and lineage.autoformalized(a.get("artifact_id"), trace)
               and _property_matches(a, prop)]
        if not vgs:
            return keep
        vg_ids = {v.get("artifact_id") for v in vgs}
        goal_ids = {_payload(v).get("goal_id") for v in vgs}
        vrs = [a for a in arts if a.get("artifact_type") == "VerificationResult"
               and (_payload(a).get("goal_artifact_id") in vg_ids or _payload(a).get("goal_id") in goal_ids)]
        if not vrs:
            return {"status": "doing", "from_trace": True, "evidence": None}
        vr = max(vrs, key=lambda a: a.get("producer_action_id") or 0)  # latest — a refuted-then-fixed reads proved
        return {"status": _verdict_for_expect(_lc(_payload(vr).get("status")), expect),
                "from_trace": True, "evidence": vr.get("artifact_id")}

    if kind == "tests":
        min_n = ev.get("min")
        tests = [a for a in arts if a.get("artifact_type") == "Tests" and rooted(a)]
        if not tests:
            return keep
        t = max(tests, key=lambda a: a.get("producer_action_id") or 0)
        p = _payload(t)
        count = p.get("count") or p.get("total") or p.get("num_tests") or 0
        failing = p.get("failing")
        all_pass = p.get("all_pass")
        passed = all_pass if all_pass is not None else (failing in (0, None))
        enough = (min_n is None) or (count >= min_n)
        if passed and enough:
            st = "done"
        elif all_pass is False or (isinstance(failing, int) and failing > 0):
            st = "blocked"
        else:
            st = "doing"
        return {"status": st, "from_trace": True, "evidence": t.get("artifact_id")}

    if kind == "decomposition":
        min_r = ev.get("min_regions")
        decs = [a for a in arts if a.get("artifact_type") == "Decomp" and rooted(a)]
        if not decs:
            return keep
        d = max(decs, key=lambda a: a.get("producer_action_id") or 0)
        p = _payload(d)
        regions = p.get("region_count") or p.get("regions") or p.get("count") or 0
        if isinstance(regions, list):
            regions = len(regions)
        st = "done" if (min_r is None or regions >= min_r) else "doing"
        return {"status": st, "from_trace": True, "evidence": d.get("artifact_id")}

    return keep


def resolve_item(item, trace):
    """Resolve one acceptance item to {status, from_trace, evidence} against the trace's evidence."""
    # Goal Contract typed criterion (component + evidence) → resolve by lineage (§4), not text.
    if item.get("component") is not None and item.get("evidence") is not None:
        typed = _resolve_typed(item, trace)
        if typed is not None:
            return typed
    keep = {"status": item.get("status", "todo"), "from_trace": False, "evidence": None}
    binding = item.get("binding")
    if not binding:
        return keep
    kind = item.get("kind")
    arts = trace.get("artifacts", [])

    if kind == "obligation":
        pid = binding.get("policy_id")
        ev = next((e for e in trace.get("policy_evaluations", []) if e.get("policy_id") == pid), None)
        if not ev:
            return keep
        s = _lc(ev.get("status"))
        st = "done" if s == "passed" else "blocked" if s == "failed" else "doing"
        return {"status": st, "from_trace": True, "evidence": pid}

    if kind == "gap":
        rid = binding.get("residual_id")
        r = next((x for x in trace.get("residuals", []) if x.get("residual_id") == rid), None)
        if not r:
            return keep
        s = _lc(r.get("status") or "open")
        st = "done" if s in ("addressed", "waived") else "todo"
        return {"status": st, "from_trace": True, "evidence": rid}

    if kind == "property":
        sym = binding.get("symbol")
        prop = binding.get("property")
        vgs = [a for a in arts if a.get("artifact_type") == "VerificationGoal" and _vg_matches(a, sym, prop)]
        if not vgs:
            return keep
        vg_ids = {v.get("artifact_id") for v in vgs}
        goal_ids = {_payload(v).get("goal_id") for v in vgs}
        vrs = [a for a in arts if a.get("artifact_type") == "VerificationResult"
               and (_payload(a).get("goal_artifact_id") in vg_ids or _payload(a).get("goal_id") in goal_ids)]
        if not vrs:
            return {"status": "doing", "from_trace": True, "evidence": None}
        # latest result by producer action, so a refuted-then-fixed property reads proved
        vr = max(vrs, key=lambda a: a.get("producer_action_id") or 0)
        s = _lc(_payload(vr).get("status"))
        st = "done" if s in ("proved", "sat") else "blocked" if s == "refuted" else "doing"
        return {"status": st, "from_trace": True, "evidence": vr.get("artifact_id")}

    if kind == "change":
        sym = binding.get("symbol")
        touched = next((a for a in arts if a.get("artifact_type") in ("Diff", "IMLModel")
                        and sym and _lc(sym) in _lc(a.get("summary") or a.get("name"))), None)
        if touched:
            return {"status": "done", "from_trace": True, "evidence": touched.get("artifact_id")}
        return keep

    return keep


def progress_of(items):
    if not items:
        return 0.0
    score = sum(1.0 if i["status"] == "done" else 0.5 if i["status"] == "doing" else 0.0 for i in items)
    return score / len(items)


# ================================================================
# Faithfulness -- is the definition of done RIGHT, not just met? (GOAL_FAITHFULNESS_v0_1)
# ================================================================

def faithfulness_of(goal, high_stakes=False):
    """Grade the DEFINITION of done, not just the work. Two orthogonal axes plus supporting signals:

      met       -- every REQUIRED acceptance criterion resolved to `done` (call after resolution).
      certified -- a reviewer OTHER than the doer approved the definition of done, every intent
                   clause is covered, and it is not weakly specified. The party that MEETS a goal
                   must not be the sole party that DEFINES it.
      weakly_specified  -- "done" rests only on `change` edits (nothing proved / policy-checked); on a
                   high-stakes path, nothing PROVED (`property`) at all.
      uncovered_clauses -- intent clauses no acceptance item `covers`.

    Kept in step with the desktop `goalFaithfulness()` (TS) and the viewer `goalFaithfulnessV()` (JS).
    """
    acc = goal.get("acceptance") or []
    required = [a for a in acc if a.get("required") is not False]
    req_items = required or acc

    met = bool(req_items) and all(_lc(a.get("status")) == "done" for a in req_items)

    # "Hard" evidence = a proof (property) or a policy (obligation). A goal backed only by `change`
    # edits is weakly specified -- "done" the moment edits land, nothing proved or policy-checked.
    if not acc:
        weak = False
    elif high_stakes:
        weak = not any(a.get("kind") == "property" for a in req_items)
    else:
        weak = not any(a.get("kind") in ("property", "obligation") for a in req_items)

    clauses = goal.get("intent_clauses") or []
    covered = {c for a in acc for c in (a.get("covers") or [])}
    uncovered = [c for c in clauses if c not in covered]

    review = goal.get("criteria_review") or {}
    reviewer = review.get("reviewed_by")
    doers = {a.get("author") for a in acc if a.get("author")}
    non_doer = bool(reviewer) and reviewer not in doers
    certified = bool(review.get("verdict") == "approved" and non_doer and not uncovered and not weak)

    return {
        "met": met,
        "certified": certified,
        "weakly_specified": weak,
        "uncovered_clauses": uncovered,
    }


# ================================================================
# Stale evidence -> derived residuals (was staleness.ts)
# ================================================================

def stale_evidence(trace):
    """Proofs invalidated by a later code change, as derived residuals (tagged `derived: True`)."""
    arts = trace.get("artifacts", [])
    by_id = {a.get("artifact_id"): a for a in arts}
    out = []
    for vr in arts:
        if vr.get("artifact_type") != "VerificationResult":
            continue
        if _lc(_payload(vr).get("status")) not in ("proved", "sat"):
            continue
        proved_at = vr.get("producer_action_id") or 0
        vg = by_id.get(_payload(vr).get("goal_artifact_id"))
        if not (vg and vg.get("artifact_type") == "VerificationGoal"):
            vg = next((a for a in arts if a.get("artifact_type") == "VerificationGoal"
                       and _payload(a).get("goal_id") == _payload(vr).get("goal_id")), None)
        sym = _payload(vg).get("target_symbol")
        if not sym:
            continue
        changes = [a for a in arts if a.get("artifact_type") in ("Diff", "IMLModel")
                   and _lc(sym) in _lc(a.get("summary") or a.get("name"))
                   and (a.get("producer_action_id") or 0) > proved_at]
        if not changes:
            continue
        changed_at = max(c.get("producer_action_id") or 0 for c in changes)
        desc = _payload(vg).get("description") or f"property of {sym}"
        out.append({
            "residual_id": f"stale-{vr.get('artifact_id')}",
            "kind": "stale_evidence",
            "severity": "medium",
            "status": "open",
            "statement": f'Proof of "{desc}" is stale: verified at step #{proved_at}, '
                         f"but {sym} changed at step #{changed_at}.",
            "suggested_check": f"Re-verify the property against the current {sym}.",
            "target": {"target_type": "artifact", "target_id": vr.get("artifact_id")},
            "derived": True,
        })
    return out


# ================================================================
# Relevance cone / goal-scoped views (was goalSlice.ts)
# ================================================================

def _seed_artifacts(goal, trace):
    """The artifacts that constitute the evidence for a goal's acceptance items (+ in-scope work)."""
    arts = trace.get("artifacts", [])
    residuals = trace.get("residuals", [])
    seeds = set()
    for item in goal.get("acceptance", []):
        # Resolved evidence (set by resolve_item during enrich) — seeds the cone for TYPED criteria
        # (which have no legacy `binding`) as well as legacy ones.
        ev = item.get("evidence")
        if ev and any(a.get("artifact_id") == ev for a in arts):
            seeds.add(ev)
        b = item.get("binding")
        if not b:
            continue
        kind = item.get("kind")
        if kind == "property":
            sym, prop = b.get("symbol"), b.get("property")
            vgs = [a for a in arts if a.get("artifact_type") == "VerificationGoal" and _vg_matches(a, sym, prop)]
            vg_ids = {v.get("artifact_id") for v in vgs}
            goal_ids = {_payload(v).get("goal_id") for v in vgs}
            for v in vgs:
                seeds.add(v.get("artifact_id"))
            for a in arts:
                if a.get("artifact_type") == "VerificationResult" and (
                        _payload(a).get("goal_artifact_id") in vg_ids or _payload(a).get("goal_id") in goal_ids):
                    seeds.add(a.get("artifact_id"))
        elif kind == "change":
            sym = b.get("symbol")
            if sym:
                for a in arts:
                    if a.get("artifact_type") in ("Diff", "IMLModel") and _lc(sym) in _lc(a.get("summary") or a.get("name")):
                        seeds.add(a.get("artifact_id"))
        elif kind == "gap":
            r = next((x for x in residuals if x.get("residual_id") == b.get("residual_id")), None)
            tid = (r.get("target") or {}).get("target_id") if r else None
            if tid and any(a.get("artifact_id") == tid for a in arts):
                seeds.add(tid)
        # obligation: policy evaluation has no producing action -> no seed
    for sym in goal.get("scope", []):
        if not sym:
            continue
        for a in arts:
            if _lc(sym) in _lc(a.get("summary") or a.get("name")):
                seeds.add(a.get("artifact_id"))
    return seeds


def goal_relevant_actions(goal, trace):
    """Action ids in the goal's evidence cone: producers of the evidence + all lineage ancestors."""
    arts = trace.get("artifacts", [])
    by_id = {a.get("artifact_id"): a for a in arts}
    action_ids = set()
    seen = set()
    stack = list(_seed_artifacts(goal, trace))
    while stack:
        aid = stack.pop()
        if aid in seen:
            continue
        seen.add(aid)
        a = by_id.get(aid)
        if not a:
            continue
        if a.get("producer_action_id") is not None:
            action_ids.add(a.get("producer_action_id"))
        for p in a.get("derived_from", []) or []:
            if p not in seen:
                stack.append(p)
    return action_ids


def _cone_scope(goal, trace):
    """(artifact_ids, action_ids) in the goal's evidence cone — the artifacts reachable from the goal's
    evidence via lineage, and their producing actions."""
    arts = trace.get("artifacts", [])
    by_id = {a.get("artifact_id"): a for a in arts}
    action_ids, seen = set(), set()
    stack = list(_seed_artifacts(goal, trace))
    while stack:
        aid = stack.pop()
        if aid in seen:
            continue
        seen.add(aid)
        a = by_id.get(aid)
        if not a:
            continue
        if a.get("producer_action_id") is not None:
            action_ids.add(a.get("producer_action_id"))
        for p in a.get("derived_from", []) or []:
            if p not in seen:
                stack.append(p)
    return seen, action_ids


def cone_trace(goal, trace):
    """The trace PROJECTED to a goal's cone: its evidence artifacts + producing actions, keeping
    trace-level context (high_stakes_paths, residuals, …). A goal's policies evaluate over this, so
    one goal is not blocked by an unrelated component's violation (Goal Contract §5)."""
    art_ids, act_ids = _cone_scope(goal, trace)
    projected = {k: v for k, v in trace.items() if k not in ("actions", "artifacts", "goals")}
    projected["actions"] = [a for a in trace.get("actions", []) if a.get("id") in act_ids]
    projected["artifacts"] = [a for a in trace.get("artifacts", []) if a.get("artifact_id") in art_ids]
    projected["goals"] = [goal]
    return projected


# --- Goal Contract §5-6: the GOVERNED axis (policies over the goal's cone) --------------------------

def governance_of(goal, trace, policies):
    """Evaluate a goal's effective `policies` over its cone.

    `policies`: the resolved effective set — dicts with {name, formula, severity, id?/policy_id?}.
    Returns {governed, evaluations, blocking}: `governed` is False iff some ENABLED `error`-severity
    policy FAILS over the cone (Goal Contract §6 — block by default). `disabled` ids (from the goal's
    `policies.disabled`) do not evaluate; the record still shows them."""
    from . import trace as traceops  # local import: trace.py imports goals (cycle) — defer to call time
    ct = cone_trace(goal, trace)
    gp = goal.get("policies")
    disabled = set(gp.get("disabled", []) if isinstance(gp, dict) else [])
    evaluations, blocking = [], []
    for pol in policies or []:
        pid = pol.get("policy_id") or pol.get("id") or pol.get("name")
        sev = _lc(pol.get("severity") or "warning")
        if pid in disabled:
            evaluations.append({"policy_id": pid, "name": pol.get("name"), "severity": sev, "status": "disabled"})
            continue
        status, note = traceops.evaluate_policy(pol, ct)
        evaluations.append({"policy_id": pid, "name": pol.get("name"), "severity": sev, "status": status, "note": note})
        if status == "failed" and sev == "error":
            blocking.append(pid)
    return {"governed": len(blocking) == 0, "evaluations": evaluations, "blocking": blocking}


# Process-lifetime memo: a resolved ref's evaluable policy dicts. Registry content is stable within a
# session, and enrich runs on every turn — so resolve each ref once. Keyed "pack:<name>"/"policy:<ref>".
_POLICY_CACHE = {}


def _load_ref_policies(ref, is_pack):
    """Resolve a pack NAME (→ all its policies) or a single policy ref (→ one) to evaluable dicts via
    the registry. GUARDED and memoized: a missing/uncached source, a registry `SystemExit`, or any
    error yields [] rather than breaking or slowing the enrich hot path."""
    key = ("pack:" if is_pack else "policy:") + ref
    if key in _POLICY_CACHE:
        return _POLICY_CACHE[key]
    out = []
    try:
        from . import registry
        if is_pack:
            src = registry.get_source(ref)
            for entry in registry.source_catalog(src).get("policies", []):
                gp = registry.fetch_policy_from(src, entry["id"], entry.get("hash"), refresh=False)
                out.append(registry.gallery_to_trace_policy(gp, src.get("name"), entry))
        else:
            src, entry = registry.resolve(ref)
            gp = registry.fetch_policy_from(src, entry["id"], entry.get("hash"), refresh=False)
            out.append(registry.gallery_to_trace_policy(gp, src.get("name"), entry))
    except (Exception, SystemExit):
        out = []  # registry unavailable/uncached/ambiguous — governance simply has nothing from this ref
    out = [p for p in out if isinstance(p, dict) and p.get("formula")]
    _POLICY_CACHE[key] = out
    return out


def _effective_policies(goal):
    """The goal's effective policy dicts to evaluate over its cone (Goal Contract §5). Assembles:
    INLINE evaluable policies (dicts with a `formula`), individual policy-id refs, and every policy in
    each declared pack — all resolved via the registry, deduped by id. Baseline / project-default
    layering is a thin remaining hook (the union order); pack + inline resolution is wired here."""
    gp = goal.get("policies")
    if isinstance(gp, list):
        return [p for p in gp if isinstance(p, dict) and p.get("formula")]
    if not isinstance(gp, dict):
        return []
    out, seen = [], set()

    def add(p):
        pid = p.get("policy_id") or p.get("id") or p.get("name")
        if pid and pid not in seen:
            seen.add(pid)
            out.append(p)

    for p in gp.get("policies", []) or []:
        if isinstance(p, dict) and p.get("formula"):
            add(p)                                   # inline evaluable policy
        elif isinstance(p, str):
            for rp in _load_ref_policies(p, is_pack=False):
                add(rp)                              # policy-id ref
    for pack in gp.get("packs", []) or []:
        if isinstance(pack, str):
            for rp in _load_ref_policies(pack, is_pack=True):
                add(rp)                              # every policy in the pack
    return out


def unattributed_actions(trace):
    """Action ids in no goal's cone -- exploration / dead-ends / setup."""
    in_cone = set()
    for g in trace.get("goals", []):
        in_cone |= goal_relevant_actions(g, trace)
    return {a.get("id") for a in trace.get("actions", []) if a.get("id") not in in_cone}


def goal_residuals(goal, trace, derived=None):
    """Open residuals (declared + derived) that qualify a goal: bound to a gap item or touching scope."""
    if derived is None:
        derived = stale_evidence(trace)
    scope = [_lc(s) for s in goal.get("scope", []) if s]
    bound_ids = {_binding(i).get("residual_id") for i in goal.get("acceptance", [])
                 if i.get("kind") == "gap" and _binding(i).get("residual_id")}

    def touches(r):
        if r.get("residual_id") in bound_ids:
            return True
        hay = _lc((r.get("statement") or "") + " " + ((r.get("target") or {}).get("target_id") or ""))
        return any(s in hay for s in scope)

    def is_open(r):
        return _lc(r.get("status") or "open") == "open"

    declared = [r for r in trace.get("residuals", []) if is_open(r) and touches(r)]
    # dedupe by id: `derived` may already be merged into trace.residuals (e.g. by enrich())
    out, seen = [], set()
    for r in declared + [r for r in derived if touches(r)]:
        rid = r.get("residual_id")
        if rid in seen:
            continue
        seen.add(rid)
        out.append(r)
    return out


# ================================================================
# Enrich: one projection carrying all derived views for a renderer
# ================================================================

def enrich(trace):
    """Return a copy of the trace augmented with everything derived, for a thin viewer to render:
      - residuals: declared + derived stale-evidence (deduped, derived tagged)
      - each goal: acceptance items resolved (status + evidence + from_trace), progress, cone, open_gaps
      - exploration_actions: action ids attributed to no goal
    The source trace (authored goals + emitted steps) is untouched.
    """
    t = copy.deepcopy(trace)
    derived = stale_evidence(t)
    t.setdefault("residuals", [])
    existing = {r.get("residual_id") for r in t["residuals"]}
    for r in derived:
        if r.get("residual_id") not in existing:
            t["residuals"].append(r)

    for g in t.get("goals", []):
        resolved = []
        for item in g.get("acceptance", []):
            r = resolve_item(item, t)
            it = dict(item)
            it["status"] = r["status"]
            it["from_trace"] = r["from_trace"]
            it["evidence"] = r["evidence"]
            resolved.append(it)
        g["acceptance"] = resolved
        g["progress"] = progress_of(resolved)
        g["cone"] = sorted(goal_relevant_actions(g, t))
        g["open_gaps"] = len(goal_residuals(g, t, derived))
        # Grade the definition of done itself (met vs certified), over the RESOLVED items. Default
        # (non-high-stakes) grading, matching the desktop/viewer so signals don't diverge across tools.
        g["faithfulness"] = faithfulness_of(g)
        # GOVERNED axis (Goal Contract §5-6): evaluate the goal's effective policies over its cone.
        # Only attached when the goal declares evaluable policies — absent means "no governance declared".
        eff = _effective_policies(g)
        if eff:
            gov = governance_of(g, t, eff)
            g["governed"] = gov["governed"]
            g["governance"] = gov["evaluations"]

    t["exploration_actions"] = sorted(unattributed_actions(t))

    # At-a-glance summary, computed here so the viewer never re-derives it.
    evals = t.get("policy_evaluations", [])
    res = t.get("residuals", [])
    is_open = lambda r: _lc(r.get("status") or "open") == "open"  # noqa: E731
    goals = t.get("goals", [])
    faith = [g.get("faithfulness") or {} for g in goals]
    t["summary"] = {
        "policy_violations": sum(1 for e in evals if _lc(e.get("status")) == "failed"),
        "open_residuals": sum(1 for r in res if is_open(r)),
        "open_high": sum(1 for r in res if is_open(r) and _lc(r.get("severity")) in ("high", "critical")),
        "stale_evidence": sum(1 for r in res if r.get("derived")),
        "goals_total": len(goals),
        "goals_met": sum(1 for f in faith if f.get("met")),
        "goals_certified": sum(1 for f in faith if f.get("certified")),
        "goals_weakly_specified": sum(1 for f in faith if f.get("weakly_specified")),
    }
    return t

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


def _lc(s):
    return str(s if s is not None else "").lower()


def _payload(a):
    return (a or {}).get("payload") or {}


def _binding(item):
    return (item or {}).get("binding") or {}


# ================================================================
# Acceptance resolution (was goalResolve.ts)
# ================================================================

def resolve_item(item, trace):
    """Resolve one acceptance item to {status, from_trace, evidence} against the trace's evidence."""
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
        vgs = [a for a in arts if a.get("artifact_type") == "VerificationGoal"
               and (not sym or _payload(a).get("target_symbol") == sym)
               and (not prop or _lc(prop) in _lc(_payload(a).get("description")))]
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
        b = item.get("binding")
        if not b:
            continue
        kind = item.get("kind")
        if kind == "property":
            sym, prop = b.get("symbol"), b.get("property")
            vgs = [a for a in arts if a.get("artifact_type") == "VerificationGoal"
                   and (not sym or _payload(a).get("target_symbol") == sym)
                   and (not prop or _lc(prop) in _lc(_payload(a).get("description")))]
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

    t["exploration_actions"] = sorted(unattributed_actions(t))

    # At-a-glance summary, computed here so the viewer never re-derives it.
    evals = t.get("policy_evaluations", [])
    res = t.get("residuals", [])
    is_open = lambda r: _lc(r.get("status") or "open") == "open"  # noqa: E731
    t["summary"] = {
        "policy_violations": sum(1 for e in evals if _lc(e.get("status")) == "failed"),
        "open_residuals": sum(1 for r in res if is_open(r)),
        "open_high": sum(1 for r in res if is_open(r) and _lc(r.get("severity")) in ("high", "critical")),
        "stale_evidence": sum(1 for r in res if r.get("derived")),
    }
    return t

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
import hashlib
import re

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
#
# A criterion is `component` + `evidence: {artifact: <type>}`. It is MET when an artifact of that TYPE
# is present in the component's lineage — that is all. Whether the evidence was derived CORRECTLY (a
# proof that is proved and autoformalized, a test suite that passes, a decomposition of enough regions,
# a diff that is reviewed) is a POLICY judgment — the GOVERNED axis — never decided here. Keeping the
# two apart is deliberate: met = "the evidence exists", governed = "the evidence is good enough".


def _artifact_type(ev):
    """The artifact TYPE a typed criterion requires as its evidence. Accepts `artifact` (canonical),
    or `artifact_type` / `type` as tolerant aliases."""
    return ev.get("artifact") or ev.get("artifact_type") or ev.get("type")


# The goal-contract evidence vocabulary and the trace's `artifact_type` vocabulary diverge for a few
# types — most importantly a region decomposition, which authors name `Decomposition` but the trace
# records as `StateSpaceAnalysisResult`. Without this bridge EVERY `Decomposition` criterion stays
# `todo` even when the decomposition plainly exists. Canonicalize both sides before comparing.
_ART_TYPE_ALIASES = {
    "decomposition": "decomposition",
    "statespaceanalysisresult": "decomposition",
    "regiondecomposition": "decomposition",
    "decomp": "decomposition",
    "generatedtests": "generatedtests",
    "tests": "generatedtests",
}


def _canon_art_type(s):
    """Fold artifact-type spellings to a canonical key for cross-vocabulary comparison (case-, space-,
    and underscore-insensitive)."""
    k = (s or "").lower().replace("_", "").replace(" ", "")
    return _ART_TYPE_ALIASES.get(k, k)


def _resolve_typed(item, trace):
    """Resolve a typed criterion (`component` + `evidence: {artifact}`) by lineage: MET iff an artifact
    of the required type roots in the component. Quality of derivation is left to policies. Returns a
    resolution dict, or None if the item is not a typed criterion (caller falls back to legacy)."""
    compd = item.get("component") or {}
    # A criterion may name the source `function` (for display / authoring) AND a formal `symbol` — the
    # name the engine actually gave the formalization (e.g. source `clamp` -> IML `clamp_decomp`). The
    # two can differ, so accept evidence rooting in EITHER: deduped, order-preserving. Only `function`
    # is ever set by deterministic authoring, so this is a no-op there; `symbol` is stamped by the
    # attribution reconciler when the engine renamed the symbol out from under the source name.
    cands, seen = [], set()
    for c in (compd.get("function"), compd.get("function_"), compd.get("symbol")):
        if c and c not in seen:
            seen.add(c)
            cands.append(c)
    art_type = _artifact_type(item.get("evidence") or {})
    if not cands or not art_type:
        return None
    keep = {"status": item.get("status", "todo"), "from_trace": False, "evidence": None}
    want_type = _canon_art_type(art_type)
    matches = [a for a in trace.get("artifacts", [])
               if _canon_art_type(a.get("artifact_type")) == want_type
               and any(lineage.roots_in_component(a.get("artifact_id"), c, trace) for c in cands)]
    if not matches:
        return keep
    a = max(matches, key=lambda x: x.get("producer_action_id") or 0)  # the latest such artifact
    return {"status": "done", "from_trace": True, "evidence": a.get("artifact_id")}


def _open_defeater_contests(ids, trace):
    """True if an OPEN `Defeater` residual (§13) targets any artifact id in `ids` — i.e. there is live
    counter-evidence against that claim, so it is contested (§18.2)."""
    ids = set(ids)
    for r in lineage.residual_surface(trace):
        if _lc(r.get("kind")) != "defeater" or _lc(r.get("status") or "open") != "open":
            continue
        refs = set(r.get("related_artifact_ids") or [])
        tgt = (r.get("target") or {}).get("target_id")
        if tgt:
            refs.add(tgt)
        if refs & ids:
            return True
    return False


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
        r = next((x for x in lineage.residual_surface(trace) if x.get("residual_id") == rid), None)
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
        # Counter-evidence (§13 Defeater / §18.2): an OPEN defeater contesting the result (or its goal)
        # blocks it — a contested proof is never done, exactly like a refutation.
        if st == "done" and _open_defeater_contests({vr.get("artifact_id")} | vg_ids, trace):
            st = "blocked"
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
    """Grade the DEFINITION of done, not just the work. Two orthogonal axes plus a supporting signal:

      met       -- every REQUIRED acceptance criterion resolved to `done` (call after resolution).
      certified -- a reviewer OTHER than the doer approved the definition of done and every intent
                   clause is covered. The party that MEETS a goal must not be the sole party that
                   DEFINES it.
      uncovered_clauses -- intent clauses no acceptance item `covers`.

    Whether the evidence is STRONG ENOUGH (a proof rather than a diff, a passing suite, ...) is not
    graded here — it is a policy judgment (the GOVERNED axis). `high_stakes` is accepted for signature
    stability but no longer changes the result.

    Kept in step with the desktop `goalFaithfulness()` (TS) and the viewer `goalFaithfulnessV()` (JS).
    """
    acc = goal.get("acceptance") or []
    required = [a for a in acc if a.get("required") is not False]
    req_items = required or acc

    met = bool(req_items) and all(_lc(a.get("status")) == "done" for a in req_items)

    clauses = goal.get("intent_clauses") or []
    covered = {c for a in acc for c in (a.get("covers") or [])}
    uncovered = [c for c in clauses if c not in covered]

    review = goal.get("criteria_review") or {}
    reviewer = review.get("reviewed_by")
    doers = {a.get("author") for a in acc if a.get("author")}
    non_doer = bool(reviewer) and reviewer not in doers
    certified = bool(review.get("verdict") == "approved" and non_doer and not uncovered)

    return {
        "met": met,
        "certified": certified,
        "uncovered_clauses": uncovered,
    }


# ================================================================
# Stale evidence -> derived residuals (was staleness.ts)
# ================================================================

# ── Freshness of reasoning evidence (TRACE_SPEC §18.3) ──────────────────────────
# A result is Fresh / Stale / Detached w.r.t. the CURRENT model. When the model's IML source is on the
# trace (FormalModel/IMLModel `payload.formal_code`) we decide by a dependency-CLOSURE checksum of the
# target symbol — the sound signal §18.3 prescribes (the target PLUS every definition it transitively
# uses), so a change to a *dependency* is caught, not just a change to the target's own text. An
# explicit producer-emitted `payload.fingerprint.task_checksum` on the result is honored when present.
# Absent both, we fall back to the legacy heuristic (a Diff/IMLModel naming the symbol at a later step).

_MODEL_TYPES = ("FormalModel", "IMLModel")


def _top_level_defs(src):
    """Map each top-level `let NAME ... = ...` to its full definition text, from IML source."""
    defs = {}
    for chunk in re.split(r"(?m)^(?=let\b)", src or ""):
        m = re.match(r"let\s+(?:rec\s+)?([A-Za-z_][A-Za-z0-9_']*)", chunk)
        if m:
            defs[m.group(1)] = chunk
    return defs


def _symbol_closure(sym, defs):
    """The transitive set of top-level defs `sym` depends on (whole-word identifier references)."""
    seen, stack = set(), [sym]
    while stack:
        n = stack.pop()
        if n in seen or n not in defs:
            continue
        seen.add(n)
        for other in defs:
            if other != n and other not in seen and re.search(r"\b" + re.escape(other) + r"\b", defs[n]):
                stack.append(other)
    return seen


def _closure_checksum(src, sym):
    """Checksum of `sym`'s definition + its full dependency closure, or None if `sym` isn't defined."""
    defs = _top_level_defs(src)
    if sym not in defs:
        return None
    blob = "\n".join(defs[n] for n in sorted(_symbol_closure(sym, defs)))
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _model_src(a):
    # The producer (imandra-pi-agent) inlines the IML model under `iml_code` (the field the desktop and
    # viewer read); the spec's canonical name is `formal_code`. Accept either so freshness fires on real
    # producer traces, not only on hand-authored ones. `src_code` is the ORIGINAL (e.g. Python) source,
    # never the formal model — deliberately not consulted here.
    return _payload(a).get("formal_code") or _payload(a).get("iml_code")


def _same_model_line(m1, m2):
    """Are two model artifacts revisions of the SAME model — so one can meaningfully DROP a symbol the
    other defined? Producer models derive from their source node, so revisions of one file share a
    `derived_from`. Bare models (no `derived_from` — hand-authored / tests) are treated as one evolving
    model, preserving the original single-model behavior."""
    d1 = set(m1.get("derived_from") or [])
    d2 = set(m2.get("derived_from") or [])
    if not d1 and not d2:
        return True
    return bool(d1 & d2)


def _freshness_verdict(vr, sym, proved_at, arts):
    """Return "fresh" | "stale" | "detached" for a result `vr` of symbol `sym`, or None when it can't
    be decided from the trace (the caller then applies the legacy heuristic). Never returns a false
    verdict: we reason only from models that carry INLINE source, and PER SYMBOL. The producer emits ONE
    model per formalization run (per file), NOT one evolving model — so the "current model" for `sym` is
    the latest inline model that actually DEFINES `sym`, and a focused later model for a DIFFERENT symbol
    is never mistaken for a deletion. Detached requires a LATER revision of the SAME model line (shared
    source) to have dropped `sym`."""
    step = lambda a: a.get("producer_action_id") or 0  # noqa: E731
    # Only models with inline source are usable — the `symbols` list alone is unreliable (a focused
    # re-model lists a subset). Without inline source we can't recompute a closure -> defer to heuristic.
    src_models = [a for a in arts if a.get("artifact_type") in _MODEL_TYPES and _model_src(a)]
    if not src_models:
        return None
    defining = [m for m in src_models if sym in _top_level_defs(_model_src(m))]
    if not defining:
        # `sym` is defined in no inline model — can't recompute a closure -> defer to heuristic.
        return None
    cur_model = max(defining, key=step)
    # Detached: a LATER revision of the SAME model line dropped `sym` — a real removal, not a focused
    # model that simply never covered it.
    dropped = [m for m in src_models if step(m) > step(cur_model)
               and _same_model_line(m, cur_model) and sym not in _top_level_defs(_model_src(m))]
    if dropped:
        return "detached"
    stored_ck = (_payload(vr).get("fingerprint") or {}).get("task_checksum")
    if stored_ck is None:
        # No producer fingerprint: reconstruct the checksum against the DEFINING model current AT proof
        # time (fall back to the earliest defining model if the proof predates them all).
        prior = [m for m in defining if step(m) <= proved_at] or defining
        stored_ck = _closure_checksum(_model_src(max(prior, key=step)), sym)
    cur_ck = _closure_checksum(_model_src(cur_model), sym)
    if cur_ck is not None and stored_ck is not None:
        return "fresh" if cur_ck == stored_ck else "stale"
    return None


def stale_evidence(trace):
    """Proofs invalidated by a later model change (Stale) or by their target's removal (Detached), as
    derived residuals (tagged `derived: True`). TRACE_SPEC §18.3.

    Preferred signal: a dependency-CLOSURE checksum over the model's IML source (or an explicit
    producer `fingerprint`) — sound against a change to a *dependency*, not just the target's own text.
    Fallback (no inline source / no fingerprint): the legacy heuristic (a Diff/IMLModel naming the
    symbol at a later step). Keying on the LATEST result per symbol means a re-proof heals the guard."""
    arts = trace.get("artifacts", [])
    by_id = {a.get("artifact_id"): a for a in arts}

    def _vg_for(vr):
        vg = by_id.get(_payload(vr).get("goal_artifact_id"))
        if not (vg and vg.get("artifact_type") == "VerificationGoal"):
            vg = next((a for a in arts if a.get("artifact_type") == "VerificationGoal"
                       and _payload(a).get("goal_id") == _payload(vr).get("goal_id")), None)
        return vg

    # Standing reasoning RESULTS that can go stale — any result computed over the model, generically:
    # verifications (proofs) and state-space analyses (decompositions). (Conformance / co-simulation
    # follow the same shape and slot in here.) Each candidate is (kind, symbol, label, standing); the
    # freshest per (kind, symbol) is the live evidence, so a re-run heals the guard.
    def _candidate(a):
        t = a.get("artifact_type")
        if t == "VerificationResult":
            status = _lc(_payload(a).get("status"))
            if status not in ("proved", "sat", "refuted"):
                return None
            vg = _vg_for(a)
            sym = _payload(vg).get("target_symbol") if vg else None
            if not sym:
                return None
            desc = (_payload(vg).get("description") if vg else None) or f"property of {sym}"
            # Only a standing PROOF (proved/sat) can be stale; a refutation is a live issue, not stale.
            return ("vr", sym, f'Proof of "{desc}"', status in ("proved", "sat"))
        if t == "StateSpaceAnalysisResult":
            sym = _payload(a).get("target_symbol")
            if not sym:
                return None
            desc = _payload(a).get("description")
            label = f'State-space analysis "{desc}"' if desc else f"State-space analysis of `{sym}`"
            return ("ssa", sym, label, True)  # a decomposition is always standing evidence
        return None

    latest = {}  # (kind, sym) -> (step, art, label, standing)
    for a in arts:
        c = _candidate(a)
        if not c:
            continue
        kind, sym, label, standing = c
        step = a.get("producer_action_id") or 0
        key = (kind, sym)
        if key not in latest or step > latest[key][0]:
            latest[key] = (step, a, label, standing)

    out = []
    for (kind, sym), (at, art, label, standing) in latest.items():
        if not standing:
            continue
        vid = art.get("artifact_id")
        verdict = _freshness_verdict(art, sym, at, arts)
        if verdict == "fresh":
            continue
        if verdict == "detached":
            out.append({
                "residual_id": f"detached-{vid}",
                "kind": "detached_evidence",
                "severity": "high",
                "status": "open",
                "statement": f"{label} is detached: its target `{sym}` no longer exists in the current model.",
                "suggested_check": f"Confirm removing `{sym}` was intended, or restore it and re-run.",
                "target": {"target_type": "artifact", "target_id": vid},
                "derived": True,
            })
            continue
        if verdict == "stale":
            out.append({
                "residual_id": f"stale-{vid}",
                "kind": "stale_evidence",
                "severity": "medium",
                "status": "open",
                "statement": f"{label} is stale: a definition `{sym}` depends on changed after step #{at}.",
                "suggested_check": f"Re-run it against the current {sym}.",
                "target": {"target_type": "artifact", "target_id": vid},
                "derived": True,
            })
            continue
        # verdict is None -> legacy heuristic: a Diff/IMLModel naming the symbol at a later step.
        changes = [c for c in arts if c.get("artifact_type") in ("Diff", "IMLModel")
                   and _lc(sym) in _lc(c.get("summary") or c.get("name"))
                   and (c.get("producer_action_id") or 0) > at]
        if not changes:
            continue
        changed_at = max(c.get("producer_action_id") or 0 for c in changes)
        out.append({
            "residual_id": f"stale-{vid}",
            "kind": "stale_evidence",
            "severity": "medium",
            "status": "open",
            "statement": f"{label} is stale: computed at step #{at}, but {sym} changed at step #{changed_at}.",
            "suggested_check": f"Re-run it against the current {sym}.",
            "target": {"target_type": "artifact", "target_id": vid},
            "derived": True,
        })
    return out


# ================================================================
# Relevance cone / goal-scoped views (was goalSlice.ts)
# ================================================================

def _seed_artifacts(goal, trace):
    """The artifacts that constitute the evidence for a goal's acceptance items (+ in-scope work)."""
    arts = trace.get("artifacts", [])
    residuals = lineage.residual_surface(trace)
    seeds = set()
    for item in goal.get("acceptance", []):
        # Typed criterion (component + evidence spec): seed EVERY artifact of the required type rooted
        # in the component — so the goal's cone carries the whole evidence history (e.g. both a refuted
        # and a later proved result), which the GOVERNED policies then judge.
        if isinstance(item.get("component"), dict) and isinstance(item.get("evidence"), dict):
            comp = (item["component"].get("function") or item["component"].get("function_")
                    or item["component"].get("symbol"))
            art_type = _artifact_type(item["evidence"])
            if comp and art_type:
                for a in arts:
                    if (_lc(a.get("artifact_type")) == _lc(art_type)
                            and lineage.roots_in_component(a.get("artifact_id"), comp, trace)):
                        seeds.add(a.get("artifact_id"))
            continue
        # Resolved evidence id (set by resolve_item during enrich) — seeds the cone for legacy items.
        ev = item.get("evidence_ref") or item.get("evidence")
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

    declared = [r for r in lineage.residual_surface(trace) if is_open(r) and touches(r)]
    # dedupe by id: `derived` may already be merged into the trace (e.g. by enrich())
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
    # Residuals are first-class artifacts (§13, v1.8): fold any legacy list forward, then merge the
    # derived stale-evidence residuals in as Residual artifacts so the viewer sees a single surface.
    lineage.migrate_residuals(t)
    derived = stale_evidence(t)
    arts = t.setdefault("artifacts", [])
    existing = {a.get("artifact_id") for a in arts if lineage.is_residual(a)}
    for r in derived:
        if r.get("residual_id") not in existing:
            arts.append(lineage.residual_to_artifact(r))

    # Living goal guard (Phase 1): a criterion resolved `done` is AT RISK when its evidence no longer
    # reflects the current code. Two independent signals feed it:
    #   1. STRUCTURAL — a derived stale-evidence residual (a Diff/IMLModel touched the symbol after the
    #      proof). Fires when the change is recorded on the trace (typically the agent's own edit).
    #   2. HASH-BASED — `artifact_freshness` (stamped by the extension: store-ref -> fresh/stale/gone by
    #      re-hashing the current source). This catches an EXTERNAL on-disk edit the trace has no Diff
    #      for. Freshness is keyed by the store ref (`fr1`); a ponens artifact id is that ref prefixed
    #      (`fr1-result-3`), so map back by prefix.
    stale_by_vr = {}
    for r in derived:
        tgt = r.get("target") or {}
        if tgt.get("target_type") == "artifact" and tgt.get("target_id"):
            stale_by_vr[tgt["target_id"]] = r
    freshness = t.get("artifact_freshness") or {}

    def _freshness_for(aid):
        if not aid or not freshness:
            return None
        if aid in freshness:
            return freshness[aid]
        for ref, fr in freshness.items():
            if aid == ref or (isinstance(aid, str) and aid.startswith(str(ref) + "-")):
                return fr
        return None

    for g in t.get("goals", []):
        resolved = []
        for item in g.get("acceptance", []):
            r = resolve_item(item, t)
            it = dict(item)
            it["status"] = r["status"]
            it["from_trace"] = r["from_trace"]
            # A typed criterion keeps its {artifact} spec in `evidence`; the resolved artifact id goes
            # to `evidence_ref`. Legacy items (no dict spec) keep `evidence` = the resolved id.
            if isinstance(item.get("evidence"), dict):
                it["evidence_ref"] = r["evidence"]
            else:
                it["evidence"] = r["evidence"]
            # AT RISK: resolved `done`, but the evidence no longer reflects the current code — via a
            # structural stale-evidence residual OR hash-based freshness (an external edit). Still met
            # (the evidence exists); this is the honesty layer that says "re-verify before you trust it".
            if r["status"] == "done":
                stale = stale_by_vr.get(r["evidence"])
                fr = _freshness_for(r["evidence"])
                if stale:
                    it["at_risk"] = True
                    it["at_risk_reason"] = stale.get("statement")
                    it["at_risk_residual_id"] = stale.get("residual_id")
                elif fr in ("stale", "gone"):
                    it["at_risk"] = True
                    it["at_risk_reason"] = ("The source was removed since this was verified."
                                            if fr == "gone"
                                            else "The code changed since this was verified — re-check to restore the guarantee.")
            resolved.append(it)
        g["acceptance"] = resolved
        g["progress"] = progress_of(resolved)
        # Count of criteria that are met-but-stale, so a card can read "met, N at risk" at a glance.
        g["at_risk"] = sum(1 for it in resolved if it.get("at_risk"))
        g["cone"] = sorted(goal_relevant_actions(g, t))
        # The residuals that QUALIFY this goal (bound to a gap item or touching its scope) — the ids so a
        # viewer can scope "needs attention" to THIS goal instead of the whole trace's negative space.
        gr = goal_residuals(g, t, derived)
        g["open_gaps"] = len(gr)
        g["gap_residual_ids"] = [r.get("residual_id") for r in gr if r.get("residual_id")]
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
    # Expose the residual surface (projected from Residual artifacts) on `residuals` — a derived view
    # for renderers; the canonical store is the artifacts themselves (§13, v1.8).
    res = lineage.residual_surface(t)
    t["residuals"] = res
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
        # GOVERNED counts only goals that DECLARE policies (governed present) and passed them.
        "goals_governed": sum(1 for g in goals if g.get("governed") is True),
        "goals_certified": sum(1 for f in faith if f.get("certified")),
        # Living guard (Phase 1): goals with ≥1 met-but-stale criterion, and the total such criteria.
        "goals_at_risk": sum(1 for g in goals if g.get("at_risk")),
        "criteria_at_risk": sum(g.get("at_risk", 0) for g in goals),
    }
    return t

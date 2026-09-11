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


def _resolve_typed(item, trace, gate_defeater=True, gate_fresh=False):
    """Resolve a typed criterion (`component` + `evidence: {artifact}`) by lineage: MET iff an artifact
    of the required type roots in the component. Quality of derivation is left to policies. Returns a
    resolution dict, or None if the item is not a typed criterion (caller falls back to legacy).

    `gate_defeater` / `gate_fresh` are the role gates (§8.8): the defaults reproduce today's behavior
    exactly (defeater-gated, not freshness-gated); `met` clears `gate_defeater`, `governed` sets both."""
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
    aid = a.get("artifact_id")
    # Counter-evidence (§13 Defeater / §18.2): an OPEN defeater contesting the evidence (or the provenance
    # it derives from) blocks the criterion — a contested result is never done, exactly like the legacy
    # property path. This is what makes a FAILING conformance (its ConformanceResult carries an undermines
    # defeater) leave a `conformance` criterion unmet, not silently `done` on mere existence. Role-gated:
    # the default (and `governed`) apply it; `met` = mere existence, so it does not.
    contest_ids = {aid} | set(a.get("derived_from") or [])
    if gate_defeater and _open_defeater_contests(contest_ids, trace):
        return {"status": "blocked", "from_trace": True, "evidence": aid}
    # Freshness (§18.3): `governed` additionally requires the evidence be non-stale.
    if gate_fresh and _evidence_stale(aid, trace):
        return {"status": "blocked", "from_trace": True, "evidence": aid}
    return {"status": "done", "from_trace": True, "evidence": aid}


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


# ================================================================
# §8.8 property-language front-end: formula AST + recursive evaluator (Phase 1)
# ================================================================
#
# The evidence logic is the design of record for acceptance; its LEAF ATOMS already exist (the kind /
# typed resolution in `_resolve_criterion` below). Phase 1 adds the COMBINATOR layer so criteria
# compose. A `formula` is JSON the agent can author:
#     {"atom": <criterion>, "role"?: "met"|"governed"}   -- a leaf; <criterion> is the legacy item shape
#     {"and": [F, ...]}   {"or": [F, ...]}   {"not": F}   {"implies": [F, F]}
# `role` (inherited down a subtree) gates HOW an atom is judged, orthogonal to the boolean shape:
#     (default, no role) -- today's behavior: the evidence EXISTS and is UNCONTESTED (defeater-gated),
#                           NOT freshness-gated. A desugared legacy item uses this → identical results.
#     "met"              -- the evidence merely EXISTS (no defeater / no freshness gate).
#     "governed"         -- EXISTS and UNCONTESTED and FRESH (§18.3).
# Phase 1 = combinators + roles only. Selectors / quantifiers (forall/exists over glob/module/tag) and
# stable property ids (properties(S)) are later phases; the AST is shaped to accept a future
# {"forall": {"in": <selector>, "holds": F}} node without disturbing this layer.


def _evidence_stale(aid, trace):
    """True if an OPEN stale/detached residual (§18.3) targets `aid`. Used only by the `governed`
    role; recomputed per governed atom (Phase 1 simplicity — `governed` is opt-in and rare)."""
    if not aid:
        return False
    return any((r.get("target") or {}).get("target_id") == aid for r in stale_evidence(trace))


def _resolve_criterion(item, trace, gate_defeater=True, gate_fresh=False):
    """Resolve ONE leaf criterion (an atom) to {status, from_trace, evidence}. This is the historical
    kind-switch, now parameterized by the two gates the role selects. The defaults
    (gate_defeater=True, gate_fresh=False) are exactly today's behavior."""
    # Goal Contract typed criterion (component + evidence) → resolve by lineage (§4), not text.
    if item.get("component") is not None and item.get("evidence") is not None:
        typed = _resolve_typed(item, trace, gate_defeater, gate_fresh)
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
        vid = vr.get("artifact_id")
        # Counter-evidence (§13 / §18.2): a contested proof is never done — role-gated (`met` skips it).
        if st == "done" and gate_defeater and _open_defeater_contests({vid} | vg_ids, trace):
            st = "blocked"
        # Freshness (§18.3): `governed` additionally requires the proof be non-stale.
        if st == "done" and gate_fresh and _evidence_stale(vid, trace):
            st = "blocked"
        return {"status": st, "from_trace": True, "evidence": vid}

    if kind == "change":
        sym = binding.get("symbol")
        touched = next((a for a in arts if a.get("artifact_type") in ("Diff", "IMLModel")
                        and sym and _lc(sym) in _lc(a.get("summary") or a.get("name"))), None)
        if touched:
            return {"status": "done", "from_trace": True, "evidence": touched.get("artifact_id")}
        return keep

    return keep


# ---- status lattice: compose child STATUSES (not booleans) so doing/blocked propagate -------------
# DESIGN DECISION (reviewable): a criterion resolves to a 4-valued status, not a bool, so the
# combinators lift and/or/not/implies over {done, doing, todo, blocked}:
#   and: blocked if ANY blocked; else done if ALL done; else doing if ANY done|doing; else todo.
#   or : done if ANY done; else doing if ANY doing; else blocked if ALL blocked; else todo.
#   not: done<->todo; doing->doing; blocked->blocked  (contested stays contested — absence of proof is
#        not proof of absence; a defeater against P is not evidence FOR not-P. Defeasible; documented.)
#   implies(a, b) = or(not(a), b).
# Empty and/or -> todo (no evidence), avoiding a vacuous `done`.

def _pick_evidence(rs, want):
    """Best-effort representative evidence id: prefer a child whose status drove the result, else any."""
    for r in rs:
        if r.get("status") == want and r.get("evidence"):
            return r.get("evidence")
    for r in rs:
        if r.get("evidence"):
            return r.get("evidence")
    return None


def _combine(status, rs, want_for_evidence):
    return {"status": status,
            "from_trace": any(r.get("from_trace") for r in rs),
            "evidence": _pick_evidence(rs, want_for_evidence)}


def _combine_and(rs):
    ss = [r.get("status") for r in rs]
    if any(s == "blocked" for s in ss):
        return _combine("blocked", rs, "blocked")
    if rs and all(s == "done" for s in ss):
        return _combine("done", rs, "done")
    if any(s in ("done", "doing") for s in ss):
        return _combine("doing", rs, "doing")
    return _combine("todo", rs, "doing")


def _combine_or(rs):
    ss = [r.get("status") for r in rs]
    if any(s == "done" for s in ss):
        return _combine("done", rs, "done")
    if any(s == "doing" for s in ss):
        return _combine("doing", rs, "doing")
    if rs and all(s == "blocked" for s in ss):
        return _combine("blocked", rs, "blocked")
    return _combine("todo", rs, "doing")


_NOT_STATUS = {"done": "todo", "todo": "done", "doing": "doing", "blocked": "blocked"}


def _combine_not(r):
    return {"status": _NOT_STATUS.get(r.get("status"), "todo"),
            "from_trace": r.get("from_trace", False), "evidence": None}


def _empty_resolution():
    return {"status": "todo", "from_trace": False, "evidence": None}


def _subst_atom(atom, env):
    """Substitute a bound quantifier variable into an atom's element slots (§8.8 Phase 2). An inner atom
    references the bound element as `{"component": {"var": "f"}}` and/or `binding: {"symbol": {"var":
    "f"}}`; at eval time the element's concrete symbol replaces it. No-op with no env / no `var` refs."""
    if not env or not isinstance(atom, dict):
        return atom
    a = dict(atom)
    comp = a.get("component")
    if isinstance(comp, dict) and "var" in comp:
        el = env.get(comp["var"]) or {}
        a["component"] = {"function": el.get("symbol"), "symbol": el.get("symbol")}
    b = a.get("binding")
    if isinstance(b, dict):
        nb = dict(b)
        for k in ("symbol", "property"):
            v = nb.get(k)
            if isinstance(v, dict) and "var" in v:
                nb[k] = (env.get(v["var"]) or {}).get("symbol")
        a["binding"] = nb
    return a


def eval_formula(node, trace, inherited_role=None, env=None, goal=None):
    """Recursively resolve a formula node to {status, from_trace, evidence}. `role` on any node is
    inherited by descendant atoms that don't set their own; `env` carries quantifier variable bindings
    (var -> element); `goal` is the resolving goal (its `scope` feeds the `{"scope": true}` selector)."""
    if not isinstance(node, dict):
        return _empty_resolution()
    role = node.get("role", inherited_role)
    if "atom" in node:
        return _resolve_criterion(_subst_atom(node["atom"], env), trace,
                                  gate_defeater=(role != "met"), gate_fresh=(role == "governed"))
    if "and" in node:
        return _combine_and([eval_formula(c, trace, role, env, goal) for c in (node.get("and") or [])])
    if "or" in node:
        return _combine_or([eval_formula(c, trace, role, env, goal) for c in (node.get("or") or [])])
    if "not" in node:
        return _combine_not(eval_formula(node.get("not"), trace, role, env, goal))
    if "implies" in node:
        parts = node.get("implies") or []
        a = eval_formula(parts[0], trace, role, env, goal) if len(parts) > 0 else _empty_resolution()
        b = eval_formula(parts[1], trace, role, env, goal) if len(parts) > 1 else _empty_resolution()
        return _combine_or([_combine_not(a), b])
    if "forall" in node or "exists" in node:
        is_forall = "forall" in node
        q = (node.get("forall") if is_forall else node.get("exists")) or {}
        from .component import resolve_selector  # lazy: component imports goals transitively
        elements = resolve_selector(q.get("in"), trace, goal)
        # Empty selector -> todo (REVIEWABLE DECISION): an empty match is almost always a mis-spec, and a
        # vacuous `done` (∀ over ∅) would be false-green — the dangerous direction. Same for exists.
        if not elements:
            return _empty_resolution()
        var = q.get("as") or "x"
        holds = q.get("holds")
        results = [eval_formula(holds, trace, role, {**(env or {}), var: el}, goal) for el in elements]
        return _combine_and(results) if is_forall else _combine_or(results)
    return _empty_resolution()


def eval_atom(atom, trace, role=None, env=None):
    """Resolve a single leaf criterion under a role (None = default/today, 'met', 'governed')."""
    return _resolve_criterion(_subst_atom(atom, env), trace,
                              gate_defeater=(role != "met"), gate_fresh=(role == "governed"))


def resolve_item(item, trace, goal=None):
    """Resolve one acceptance item to {status, from_trace, evidence} against the trace's evidence.

    §8.8: if the item carries a `formula`, evaluate the AST (quantifier selectors read `goal.scope`).
    Otherwise the item IS a single leaf criterion (the legacy kind-switch / typed criterion), desugared
    to an atom with the default role — byte-for-byte identical to before the formula layer existed."""
    formula = item.get("formula")
    if formula is not None:
        return eval_formula(formula, trace, goal=goal)
    return _resolve_criterion(item, trace, gate_defeater=True, gate_fresh=False)


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


def _freshness_verdict_renamed(vr, old_sym, new_sym, proved_at, arts):
    """Freshness of a result recorded against `old_sym` whose component is now named `new_sym` (2d,
    component-identity rename path). The stored (proof-time) signal is `old_sym`'s closure checksum in
    the model current AT proof time (the model that still defined `old_sym`); the current signal is
    `new_sym`'s closure checksum in the latest model that defines `new_sym`. A mismatch is "stale"; equal
    (a pure rename, identical body) is "fresh"; None when it can't be recomputed (caller falls back)."""
    step = lambda a: a.get("producer_action_id") or 0  # noqa: E731
    src_models = [a for a in arts if a.get("artifact_type") in _MODEL_TYPES and _model_src(a)]
    old_defs = [m for m in src_models if old_sym in _top_level_defs(_model_src(m))]
    new_defs = [m for m in src_models if new_sym in _top_level_defs(_model_src(m))]
    if not old_defs or not new_defs:
        return None
    stored_ck = (_payload(vr).get("fingerprint") or {}).get("task_checksum")
    if stored_ck is None:
        prior = [m for m in old_defs if step(m) <= proved_at] or old_defs
        stored_ck = _closure_checksum(_model_src(max(prior, key=step)), old_sym)
    cur_model = max(new_defs, key=step)
    cur_ck = _closure_checksum(_model_src(cur_model), new_sym)
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

    # Component-identity (2d): when the trace carries stamped `component_ids` (via assign_component_ids,
    # injected by enrich), key the latest-per grouping on the COMPONENT id instead of the raw symbol name
    # — so a proof of `clamp` and a later model that renamed it to `clamp_int` chain as the SAME component
    # (the proof correctly follows the rename and goes stale). The current name of a component is read
    # from the latest model's stamped map, so the freshness closure is recomputed under the CURRENT name.
    # Additive: absent component_ids, `_component_id_for` returns None and the key is (kind, sym) as before.
    comp_by_name = lineage._component_by_name(trace)          # name -> component_id (latest wins)
    # component_id -> its CURRENT name: walk model stamps in ascending producer order so the latest
    # model's name for a component wins (a rename's newest name, not an arbitrary dict order).
    cur_name_of_comp = {}
    _stamped_models = sorted(
        (a for a in arts if a.get("artifact_type") in _MODEL_TYPES and _payload(a).get("component_ids")),
        key=lambda a: a.get("producer_action_id") or 0)
    for m in _stamped_models:
        for name, cid in (_payload(m).get("component_ids") or {}).items():
            cur_name_of_comp[cid] = name

    def _component_id_for(a, sym):
        """The component id stamped for this result's target, or None (pre-2d / unstamped)."""
        if a.get("artifact_type") == "VerificationResult":
            vg = _vg_for(a)
            cid = _payload(vg).get("target_component_id") if vg else None
        else:
            cid = _payload(a).get("target_component_id")
        return cid or comp_by_name.get(sym)

    latest = {}  # (kind, key) -> (step, art, label, standing, sym, comp_id)
    for a in arts:
        c = _candidate(a)
        if not c:
            continue
        kind, sym, label, standing = c
        step = a.get("producer_action_id") or 0
        comp_id = _component_id_for(a, sym)
        key = (kind, comp_id) if comp_id is not None else (kind, sym)
        if key not in latest or step > latest[key][0]:
            latest[key] = (step, a, label, standing, sym, comp_id)

    out = []
    for _key, (at, art, label, standing, sym, comp_id) in latest.items():
        if not standing:
            continue
        vid = art.get("artifact_id")
        # Follow the rename: check freshness under the component's CURRENT name when it differs from the
        # name the result was recorded against (e.g. proof of `clamp`, component now named `clamp_int`).
        # The rename path compares the OLD name's proof-time closure against the NEW name's current
        # closure, so a renamed+changed component goes stale; a pure rename stays fresh.
        fresh_sym = cur_name_of_comp.get(comp_id, sym) if comp_id is not None else sym
        if fresh_sym != sym:
            verdict = _freshness_verdict_renamed(art, sym, fresh_sym, at, arts)
        else:
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
    out.extend(generic_evidence_freshness(trace)["residuals"])
    return out


# ── Freshness of ANY oracle's evidence (ORACLE_SPEC v0.2 §4, TRACE_SPEC 1.12 §18.3) ──────────────
# The reasoner path above decides freshness by recomputing the task closure from the model source. Any
# OTHER evidence with a generic fingerprint (`subject_checksum`) — an Observation from a database, a
# test run, an analysis, a sign-off — is decided by the §4 rule: probe the producing oracle for the
# subject's CURRENT fingerprint when it is registered, else fall back to `valid_until`, else Unknown.

_REASONER_RESULT_TYPES = ("VerificationResult", "StateSpaceAnalysisResult", "ConformanceResult",
                          "CoSimulationResult")


def generic_evidence_freshness(trace, now=None):
    """Return {"verdicts": {artifact_id: fresh|stale|detached|unknown}, "residuals": [...]} for every
    artifact carrying a generic evidence fingerprint that the reasoner path does not cover. Only the
    LATEST artifact per subject_ref is live evidence (a re-observation heals the guard)."""
    from . import oracles as _oracles
    arts = trace.get("artifacts", []) or []
    latest = {}  # subject_ref (or artifact id) -> (step, art)
    for a in arts:
        if a.get("artifact_type") in _REASONER_RESULT_TYPES or lineage.is_residual(a):
            continue
        fp = _oracles.fingerprint_of(_payload(a))
        if not fp:
            continue
        key = fp.get("subject_ref") or a.get("artifact_id")
        step = a.get("producer_action_id") or 0
        if key not in latest or step > latest[key][0]:
            latest[key] = (step, a)
    verdicts, residuals = {}, []
    for _key, (at, a) in latest.items():
        payload = _payload(a)
        aid = a.get("artifact_id")
        fp = _oracles.fingerprint_of(payload)
        current = _oracles.probe_evidence(payload)
        verdict = _oracles.freshness_of(payload, current=current, now=now)
        verdicts[aid] = verdict
        label = a.get("name") or a.get("artifact_type") or aid
        subject = fp.get("subject_ref") or "its subject"
        if verdict == _oracles.STALE:
            residuals.append({
                "residual_id": f"stale-{aid}",
                "kind": "stale_evidence",
                "severity": "medium",
                "status": "open",
                "statement": (f"{label} is stale: {subject} changed (or its validity expired) since it was "
                              f"observed at step #{at}."),
                "suggested_check": f"Re-invoke {fp.get('oracle_id') or 'the oracle'} for {subject}.",
                "target": {"target_type": "artifact", "target_id": aid},
                "derived": True,
            })
        elif verdict == _oracles.DETACHED:
            residuals.append({
                "residual_id": f"detached-{aid}",
                "kind": "detached_evidence",
                "severity": "high",
                "status": "open",
                "statement": f"{label} is detached: {subject} no longer resolves at its source.",
                "suggested_check": "Confirm the source change was intended, or restore the subject and re-observe.",
                "target": {"target_type": "artifact", "target_id": aid},
                "derived": True,
            })
    return {"verdicts": verdicts, "residuals": residuals}


def evidence_strength_of(artifact_id, trace):
    """The honest strength of an evidence artifact (its attribution block, or derived from `engine`)."""
    from . import oracles as _oracles
    a = next((x for x in trace.get("artifacts", []) or [] if x.get("artifact_id") == artifact_id), None)
    return _oracles.strength_of(_payload(a)) if a else None


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
    # Component identity (2c/2d): stamp durable component_ids onto the enrich PROJECTION (never the
    # source trace) so the downstream consumers — roots_in_component (goal rooting) and stale_evidence
    # (freshness) — can FOLLOW A RENAME by component instead of by name. Purely additive: on a trace with
    # no stampable models the stamp is empty and every consumer is byte-identical to its pre-2d behavior.
    from .component import assign_component_ids
    assign_component_ids(t)
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
    # Generic (any-oracle) freshness verdicts, incl. `unknown` for evidence whose subject cannot be
    # re-read (ORACLE_SPEC v0.2 §4) — reported on the item, never silently fresh.
    generic_fresh = generic_evidence_freshness(t)["verdicts"]
    from . import oracles as _oracles

    def _freshness_for(aid):
        if not aid or not freshness:
            return None
        if aid in freshness:
            return freshness[aid]
        for ref, fr in freshness.items():
            if aid == ref or (isinstance(aid, str) and aid.startswith(str(ref) + "-")):
                return fr
        return None

    # An OPEN drift residual the EXTENSION emitted for this evidence (freshness `limitation`/`defeater`
    # over a stale/gone/hand-edited artifact), related to the evidence id. Lets the hash-based at_risk
    # path name a residual + carry its statement, exactly like the structural stale_evidence path, so
    # `at_risk_residual_id`/`at_risk_reason` are populated consistently however the drift was detected.
    _DRIFT_KINDS = {"limitation", "defeater", "stale_evidence"}

    def _drift_residual_for(aid):
        if not aid:
            return None
        for r in lineage.residual_surface(t):
            if str(r.get("status") or "open").lower() != "open" or r.get("kind") not in _DRIFT_KINDS:
                continue
            rel = r.get("related_artifact_ids") or []
            if any(aid == x or (isinstance(aid, str) and isinstance(x, str)
                                and (aid.startswith(x + "-") or x.startswith(aid + "-"))) for x in rel):
                return r
        return None

    for g in t.get("goals", []):
        resolved = []
        for item in g.get("acceptance", []):
            r = resolve_item(item, t, goal=g)
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
                    # Name the extension's drift residual when present, so this path carries an
                    # `at_risk_residual_id` + statement like the structural path above.
                    drift = _drift_residual_for(r["evidence"])
                    if drift:
                        it["at_risk_reason"] = drift.get("statement")
                        it["at_risk_residual_id"] = drift.get("residual_id")
                    else:
                        it["at_risk_reason"] = ("The source was removed since this was verified."
                                                if fr == "gone"
                                                else "The code changed since this was verified — re-check to restore the guarantee.")
            # Graded evidence (ORACLE_SPEC v0.2 §6): the honest strength of what resolved this item, and
            # its freshness verdict when one is derivable — so "met" is never read without its grade.
            if r.get("evidence"):
                st = evidence_strength_of(r["evidence"], t)
                if st:
                    it["evidence_strength"] = st
                if r["evidence"] in stale_by_vr:
                    it["freshness"] = "detached" if stale_by_vr[r["evidence"]].get("kind") == "detached_evidence" else "stale"
                elif r["evidence"] in generic_fresh:
                    it["freshness"] = generic_fresh[r["evidence"]]
                    if generic_fresh[r["evidence"]] == _oracles.UNKNOWN and r["status"] == "done":
                        it["freshness_note"] = "The subject of this evidence cannot currently be re-read; treat as unverified-fresh."
            resolved.append(it)
        g["acceptance"] = resolved
        g["progress"] = progress_of(resolved)
        # Weakest link: the minimum strength over REQUIRED items that resolved done (unranked ignored).
        ranked = [it["evidence_strength"] for it in resolved
                  if it.get("status") == "done" and it.get("required", True) and it.get("evidence_strength")]
        if ranked:
            g["min_strength"] = max(ranked, key=_oracles.strength_rank)
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

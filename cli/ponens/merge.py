"""Residual-aware trace MERGE: carry forward the provably-unaffected standing results, flag the rest.

This is the THIN, sound-but-conservative Python realization of the proved merge-composition model in
`formal/merge/{delta,classify}.iml` (the conformance spec). Scope: the SkipDisjoint, SkipContract, and
ReReason branches — the SkipContract / opaque-contract branch is implemented for the SOUND slice only
(`uninterpreted`-abstracted dependencies). A `contract` whose callee changed has a stale discharge and
would need re-proof (no reproof formula is recorded in the trace), so it re-reasons; `pinned`/`concrete`/
no-assumption re-reason too. Anything not provably safe collapses onto ReReason (never-false-fresh).

The pipeline mirrors the IML:
  * merge_delta  ~ delta.iml   — the component-wise change set THEIRS introduces vs the ancestor. The
                                 never-guess rule is automatic: any checksum divergence counts as
                                 `changed`, so nothing genuinely-changed is ever dropped from the delta.
  * classify     ~ classify.iml — per standing result R over `touched = closure ∩ delta`:
                                 touched == ∅                         -> SkipDisjoint  (CarriedForward);
                                 else, EVERY touched dep is `uninterpreted` in OURS's model assumptions
                                   -> SkipContract (CarriedForward, basis "uninterpreted-opaque"): the
                                   result proved its property for ALL values of the opaque dep, so any
                                   merge change to it leaves the property holding;
                                 else                                 -> ReReason (a `needs_rereasoning`
                                   residual). The proved classifier's opaque `dep_kind` is realized by
                                   the model's structured `payload.assumptions` (`_assumptions_index`).

`merge()` returns a REPORT projection; it never mutates its inputs.

Reuses goals.py for all the IML-source machinery (top-level defs, symbol closure, closure checksum),
and replicates stale_evidence's "standing result" extraction so the two derived views agree on what a
standing result IS.
"""

from .goals import (
    _top_level_defs,
    _symbol_closure,
    _closure_checksum,
    _model_src,
    _payload,
    _lc,
    _MODEL_TYPES,
)
from . import lineage
from .component import match_descriptor


# ================================================================
# Trace-level source / symbol helpers (over the model artifacts)
# ================================================================

def _trace_defs(trace):
    """Every top-level def in the trace's model source. The model artifacts (types in `_MODEL_TYPES`)
    carry inline IML under `payload.formal_code`/`iml_code`; we concatenate them in ASCENDING
    `producer_action_id` order so a LATER revision of a symbol overwrites an earlier one (the latest
    revision wins), matching the freshness convention in goals.py."""
    return _top_level_defs(_concat_src(trace))


def _concat_src(trace):
    """The trace's model source, concatenated in ascending producer-action order (latest revision last
    so `_top_level_defs` keeps the newest definition of each symbol)."""
    models = [a for a in trace.get("artifacts", []) or []
              if a.get("artifact_type") in _MODEL_TYPES and _model_src(a)]
    models.sort(key=lambda a: a.get("producer_action_id") or 0)
    return "\n".join(_model_src(a) for a in models)


def _symbol_checksum(trace, sym):
    """Checksum of `sym`'s definition + its full dependency closure in the trace's model source, or None
    if `sym` is not defined anywhere in the trace."""
    return _closure_checksum(_concat_src(trace), sym)


def _symbols(trace):
    """The set of top-level def names defined in the trace's model source."""
    return set(_trace_defs(trace).keys())


def _standing_results(trace):
    """The latest STANDING result per (kind, symbol): proved/sat VerificationResults (via their
    VerificationGoal's `target_symbol`) and StateSpaceAnalysisResults (via `target_symbol`). Replicates
    stale_evidence's candidate + latest-per-(kind,sym) logic so both derived views agree on the standing
    set. Returns a list of {result_id, kind, symbol}."""
    arts = trace.get("artifacts", []) or []
    by_id = {a.get("artifact_id"): a for a in arts}

    def _vg_for(vr):
        vg = by_id.get(_payload(vr).get("goal_artifact_id"))
        if not (vg and vg.get("artifact_type") == "VerificationGoal"):
            vg = next((a for a in arts if a.get("artifact_type") == "VerificationGoal"
                       and _payload(a).get("goal_id") == _payload(vr).get("goal_id")), None)
        return vg

    def _candidate(a):
        t = a.get("artifact_type")
        if t == "VerificationResult":
            status = _lc(_payload(a).get("status"))
            # Only a standing PROOF (proved/sat) survives a merge as evidence; a refutation is a live
            # issue, not a fact to carry forward — so it is not a standing result here.
            if status not in ("proved", "sat"):
                return None
            vg = _vg_for(a)
            sym = _payload(vg).get("target_symbol") if vg else None
            if not sym:
                return None
            return ("vr", sym)
        if t == "StateSpaceAnalysisResult":
            sym = _payload(a).get("target_symbol")
            if not sym:
                return None
            return ("ssa", sym)
        return None

    latest = {}  # (kind, sym) -> (step, art)
    for a in arts:
        c = _candidate(a)
        if not c:
            continue
        kind, sym = c
        step = a.get("producer_action_id") or 0
        key = (kind, sym)
        if key not in latest or step > latest[key][0]:
            latest[key] = (step, a)

    return [{"result_id": art.get("artifact_id"), "kind": kind, "symbol": sym}
            for (kind, sym), (_step, art) in latest.items()]


# ================================================================
# Delta (delta.iml) — the change set THEIRS introduces vs the ancestor
# ================================================================

import hashlib as _hashlib
import re as _re


def _symbol_descriptor(src, sym):
    """A component descriptor for `sym` in `src`: {fingerprint, text}.

    The fingerprint is a NAME-INDEPENDENT content fingerprint of `sym`'s definition: the def text with
    the symbol's OWN name replaced by a placeholder before hashing, so a pure rename (same body, new
    name) yields the SAME fingerprint — which is exactly what lets tier-2 exactness distinguish a
    rename-unchanged (identical fingerprint) from a rename-changed (different fingerprint). Renaming a
    symbol necessarily edits its signature line, so a plain closure checksum would ALWAYS differ across a
    rename and could never witness "content unchanged". `text` is the raw def block — the concrete signal
    `_line_similarity` compares (the similarity tier tolerates the changed signature line)."""
    defs = _top_level_defs(src)
    text = defs.get(sym, "")
    normed = _re.sub(r"\b" + _re.escape(sym) + r"\b", "\x00SYM\x00", text)
    fp = "sha256-body:" + _hashlib.sha256(normed.encode("utf-8")).hexdigest()
    return {"id": sym, "fingerprint": fp, "text": text}


def merge_delta(ours, theirs, base=None):
    """The component-wise change set THEIRS introduces relative to the ancestor (`base` if given, else
    `ours`). For each symbol in the union of symbols across the traces:
      * in THEIRS, absent in the reference -> added,
      * in the reference, absent in THEIRS -> removed,
      * in both but closure-checksum differs                -> changed.

    RENAME-AWARENESS (component-identity aware, via `match_descriptor`): a symbol renamed by THEIRS looks
    like a name-based remove+add, which over-fires (the caller re-reasons needlessly). After the
    name-based sets are computed, each `removed` symbol `r` is matched (as a descriptor) against the
    `added` symbols (as candidates) with the PROVED resolver:
      * reuse with IDENTICAL fingerprint  -> a rename, content unchanged: drop `r` from removed and the
        matched symbol from added, record it under `renamed` (changed: False) — NOT a change, so NOT in
        the delta set.
      * reuse with a DIFFERENT fingerprint -> a rename, content changed: drop from removed/added, record
        under `renamed` (changed: True), and add `r` to `changed` (one changed component, not remove+add).
      * mint (no confident/unique match, incl. the never-guess ambiguous case) -> genuinely removed: `r`
        stays in removed and any unmatched added stay in added (conservative, sound).

    `added ∪ removed ∪ changed` (renamed-unchanged excluded) is the full delta set. When no rename is
    detected the output is byte-for-byte the pre-rename behavior (`renamed` is empty)."""
    reference = base if base is not None else ours
    ref_src = _concat_src(reference)
    their_src = _concat_src(theirs)
    ref_syms = _symbols(reference)
    their_syms = _symbols(theirs)
    added, removed, changed = [], [], []
    for sym in sorted(ref_syms | their_syms):
        in_ref = sym in ref_syms
        in_theirs = sym in their_syms
        if in_theirs and not in_ref:
            added.append(sym)
        elif in_ref and not in_theirs:
            removed.append(sym)
        else:  # in both
            if _symbol_checksum(theirs, sym) != _symbol_checksum(reference, sym):
                changed.append(sym)

    # Rename reconciliation: match each removed symbol against the still-available added symbols.
    renamed = []
    if removed and added:
        available = list(added)  # candidates consumed as they are matched (each added maps to ≤1 rename)
        still_removed = []
        for r in removed:
            r_desc = _symbol_descriptor(ref_src, r)
            candidates = [_symbol_descriptor(their_src, a) for a in available]
            decision, matched = match_descriptor(r_desc, candidates)
            if decision != "reuse":
                still_removed.append(r)          # mint / ambiguous -> genuinely removed
                continue
            available.remove(matched)            # this added symbol is the rename target, not a new add
            matched_fp = next(c["fingerprint"] for c in candidates if c["id"] == matched)
            content_changed = matched_fp != r_desc["fingerprint"]
            renamed.append({"from": r, "to": matched, "changed": content_changed})
            if content_changed:
                changed.append(r)                # one changed component (its old name), not remove+add
        removed = still_removed
        added = available

    delta = {"changed": sorted(changed), "added": sorted(added), "removed": sorted(removed)}
    if renamed:
        delta["renamed"] = renamed
    return delta


def _delta_symbols(delta):
    """The flat delta set: added ∪ removed ∪ changed. Renamed-unchanged symbols are deliberately absent
    (they are not a change), so they never force a re-reason."""
    return set(delta["changed"]) | set(delta["added"]) | set(delta["removed"])


# ================================================================
# Assumption abstraction index (dep_kind, from the model's structured assumptions)
# ================================================================

def _assumptions_index(trace):
    """`target -> abstraction` over the trace's model artifacts, the trace-level realization of the
    proved classifier's opaque `dep_kind ∈ {Uninterpreted, Typed, Axiomatized, Pinned}`.

    A model artifact records the dependencies it abstracted as structured `payload.assumptions`, a list of
    `{target, abstraction, discharged?, ...}` where `abstraction ∈ 'concrete'|'contract'|'uninterpreted'|
    'pinned'` (the producer's `ArtifactAssumption`). We scan every model artifact (`_MODEL_TYPES`) and map
    each assumption's `target` to its `abstraction`; the LATEST model revision wins (ascending
    `producer_action_id`, so a later entry for the same target overwrites an earlier one), matching the
    freshness convention elsewhere in this module. Tolerant: missing/empty `assumptions`, or an entry
    lacking `target`/`abstraction`, is skipped."""
    out = {}
    models = [a for a in trace.get("artifacts", []) or [] if a.get("artifact_type") in _MODEL_TYPES]
    models.sort(key=lambda a: a.get("producer_action_id") or 0)
    for a in models:
        for asm in _payload(a).get("assumptions", []) or []:
            if not isinstance(asm, dict):
                continue
            target = asm.get("target")
            abstraction = asm.get("abstraction")
            if not target or not abstraction:
                continue
            out[target] = _lc(abstraction)
    return out


# ================================================================
# Coverage regression (SelectorRegression, realized over goal.scope)
# ================================================================

def _in_scope(name, scope):
    """Is component `name` in a goal's `scope`? Reuses goals.py's scope predicate: a scope entry (case-
    insensitively) SUBSTRING-matches the component name. `scope` is the goal's raw `scope` list."""
    if not name:
        return False
    hay = _lc(name)
    return any(_lc(s) in hay for s in scope if s)


# ================================================================
# Residual-awareness — open assumptions standing on a result
# ================================================================

def _assumptions_in_question(result_id, trace):
    """Ids of OPEN `assumption`-kind residuals in `trace` whose `related_artifact_ids` include
    `result_id`. A re-reasoned result that stood on an open assumption cites it as an extra cause. Coarse
    — we do not re-check the assumption here, only surface that it is in question."""
    out = []
    for r in lineage.residual_surface(trace):
        if _lc(r.get("kind")) != "assumption":
            continue
        if _lc(r.get("status") or "open") != "open":
            continue
        if result_id in (r.get("related_artifact_ids") or []):
            out.append(r.get("residual_id"))
    return out


# ================================================================
# The merge report (classify.iml, thin: SkipDisjoint | ReReason)
# ================================================================

def merge(ours, theirs, base=None):
    """Combine two traces: carry forward the provably-unaffected standing results of OURS, flag the rest
    for re-reasoning. A REPORT projection — inputs are never mutated.

    For each standing result R of symbol `sym` from OURS:
      * closure = `sym`'s dependency closure in OURS's model source,
      * touched = closure ∩ delta_syms,
      * touched == ∅                                                 -> SkipDisjoint  -> carried_forward
        (basis "closure-disjoint"),
      * else, EVERY component in `touched` is `uninterpreted` in OURS's assumptions -> SkipContract ->
        carried_forward (basis "uninterpreted-opaque", recording the relied-on `via_assumptions`),
      * else                                                         -> ReReason     -> a
        needs_rereasoning residual.
    """
    delta = merge_delta(ours, theirs, base=base)
    delta_syms = _delta_symbols(delta)
    defs = _trace_defs(ours)
    standing = _standing_results(ours)
    assumptions_idx = _assumptions_index(ours)
    reference = base if base is not None else ours
    ref_src = _concat_src(reference)
    their_src = _concat_src(theirs)

    def _own_body_changed(t):
        """Did component `t`'s OWN definition body change between the reference and THEIRS (name-independent
        fingerprint)? A touched component that is only in the delta because a DEPENDENCY of it changed (its
        own body is byte-identical) is not itself an obstacle to a SkipContract carry-forward — only a
        genuine change to its own body is."""
        return _symbol_descriptor(ref_src, t)["fingerprint"] != _symbol_descriptor(their_src, t)["fingerprint"]

    carried, rereason = [], []
    theirs_standing = {(r["kind"], r["symbol"]): r for r in _standing_results(theirs)}
    for r in standing:
        rid, sym = r["result_id"], r["symbol"]
        closure = _symbol_closure(sym, defs)  # includes sym itself when defined
        # A symbol OURS proved about but that isn't in OURS's own model source has an empty closure;
        # fall back to the bare symbol so a direct touch of it is still caught.
        if not closure:
            closure = {sym}
        touched = sorted(closure & delta_syms)
        if not touched:
            carried.append(_graded({
                "result_id": rid,
                "symbol": sym,
                "kind": r["kind"],
                "closure": sorted(closure),
                "basis": "closure-disjoint",
            }, ours, theirs, theirs_standing.get((r["kind"], sym))))
            continue

        # SkipContract (sound slice): every touched component that genuinely CHANGED its own body is an
        # `uninterpreted` dependency in OURS's model assumptions. The result proved its property for ALL
        # possible values of each such opaque dep, so any merge change to it leaves the property holding —
        # carry forward. A touched component whose OWN body is unchanged (in the delta only because a
        # dependency of it changed) is not itself an obstacle. Requires ALL genuinely-changed touched
        # components be uninterpreted; a single non-opaque change (concrete/contract/pinned/absent — incl.
        # the result's own symbol changing its body) falls through to ReReason. A contract's discharge is
        # stale once its callee changed and there is no recorded reproof formula, so contracts are
        # (soundly) NOT skipped here (future work: reproof needs the formula).
        changed_touched = [t for t in touched if _own_body_changed(t)]
        if changed_touched and all(assumptions_idx.get(t) == "uninterpreted" for t in changed_touched):
            carried.append(_graded({
                "result_id": rid,
                "symbol": sym,
                "kind": r["kind"],
                "closure": sorted(closure),
                "basis": "uninterpreted-opaque",
                "via_assumptions": changed_touched,
            }, ours, theirs, theirs_standing.get((r["kind"], sym))))
        else:
            assumptions = _assumptions_in_question(rid, ours)
            cause = "closure-changed"
            statement = (f"Standing result `{rid}` about `{sym}` needs re-reasoning: the merge touched "
                         f"{', '.join('`%s`' % t for t in touched)} in its dependency closure.")
            if assumptions:
                statement += (f" It also stands on open assumption(s) "
                              f"{', '.join('`%s`' % a for a in assumptions)}, now in question.")
            rereason.append({
                "residual_id": f"rereason-{rid}",
                "kind": "needs_rereasoning",
                "status": "open",
                "result_id": rid,
                "symbol": sym,
                "touched": touched,
                "cause": cause,
                "assumptions_in_question": assumptions,
                "statement": statement,
                "derived": True,
                "target": {"target_type": "artifact", "target_id": rid},
            })

    # Totality (the proved invariant, classify_total + basis_disjoint restricted to the two branches):
    # every standing result is bucketed EXACTLY once — the standing set == disjoint union of
    # carried_forward ∪ rereason (none missing, none in both).
    standing_ids = [r["result_id"] for r in standing]
    carried_ids = [c["result_id"] for c in carried]
    rereason_ids = [rr["result_id"] for rr in rereason]
    totality_ok = (
        len(carried_ids) + len(rereason_ids) == len(standing_ids)
        and set(carried_ids).isdisjoint(rereason_ids)
        and set(carried_ids) | set(rereason_ids) == set(standing_ids)
    )

    coverage_regressions = _coverage_regressions(ours, theirs, delta)

    report = {
        "delta": delta,
        "carried_forward": carried,
        "rereason": rereason,
        "totality_ok": totality_ok,
        "counts": {
            "standing": len(standing_ids),
            "carried": len(carried_ids),
            "rereason": len(rereason_ids),
            "delta": len(delta_syms),
        },
    }
    # Purely additive: only surface the field when there is something to report, so a merge with no
    # scoped goals (or no in-scope membership change) is byte-for-byte its pre-coverage output.
    if coverage_regressions:
        report["coverage_regressions"] = coverage_regressions
    return report


import copy as _copy


def _artifact_by_id(trace, aid):
    return next((a for a in trace.get("artifacts", []) or [] if a.get("artifact_id") == aid), None)


def _graded(entry, ours, theirs, theirs_result):
    """Stamp graded-evidence fields on a carried-forward entry (ORACLE_SPEC v0.2 §6): the strength of
    OURS's result and, when THEIRS also carries a standing result for the same (kind, symbol), which side
    is preferred - the stronger `evidence_strength`; at equal strength, the later result. Purely
    additive: without strengths on either side the entry is unchanged except for `strength: None`."""
    from . import oracles as _oracles
    ours_art = _artifact_by_id(ours, entry["result_id"])
    ours_strength = _oracles.strength_of(_payload(ours_art)) if ours_art else None
    entry["strength"] = ours_strength
    if not theirs_result:
        return entry
    their_art = _artifact_by_id(theirs, theirs_result["result_id"])
    their_strength = _oracles.strength_of(_payload(their_art)) if their_art else None
    entry["theirs_result_id"] = theirs_result["result_id"]
    entry["theirs_strength"] = their_strength
    ro, rt = _oracles.strength_rank(ours_strength), _oracles.strength_rank(their_strength)
    if rt < ro:
        entry["preferred"] = "theirs"
    elif ro < rt:
        entry["preferred"] = "ours"
    else:
        ours_step = (ours_art or {}).get("producer_action_id") or 0
        their_step = (their_art or {}).get("producer_action_id") or 0
        entry["preferred"] = "theirs" if their_step > ours_step else "ours"
    return entry


def combine(ours, theirs, base=None):
    """Materialize `merge(ours, theirs, base)` into a VALID merged trace (not just the report).

    The merged trace is a deepcopy of OURS — it carries the standing results + goals we reason about —
    then augmented so it faithfully records the two-parent COMBINE and the merge's findings:

    1. MergeEvent (two-parent provenance): a top-level `merge` field naming both parents + the base, a
       fresh `trace_id`, and a `trace_links` entry recording the parents. The merged trace's own
       `derived_from` DAG stays well-founded (the two-parent link lives in `merge`/`trace_links`, not in
       the artifact DAG).
    2. Overlay theirs's changed/added model artifacts so the merged trace reflects the incoming code
       (union by `artifact_id`; on collision prefer THEIRS's version for a changed/added component).
    3. Materialize the findings:
         * each `carried_forward` entry  -> a `CarriedForward` artifact,
         * each `rereason` entry         -> a `needs_rereasoning` residual,
         * each `coverage_regression`    -> a `coverage_regression` residual.
    4. A `merge` action so the materialized artifacts/residuals have a resolvable `producer_action_id`.
    5. Totality: every standing result of the parents is represented exactly once (a CarriedForward
       artifact OR a needs_rereasoning residual) — asserted before returning.

    `merge()` is reused verbatim; neither input trace is mutated (the skeleton is a deepcopy)."""
    report = merge(ours, theirs, base=base)

    merged = _copy.deepcopy(ours)
    ours_id = ours.get("trace_id")
    theirs_id = theirs.get("trace_id")
    base_id = base.get("trace_id") if base is not None else None
    merged["trace_id"] = f"merge-{ours_id}-{theirs_id}"

    # 1. MergeEvent — two-parent provenance recorded off the artifact DAG.
    merged["merge"] = {
        "parents": [ours_id, theirs_id],
        "base": base_id,
        "kind": "merge",
    }
    links = merged.setdefault("trace_links", [])
    links.append({"kind": "merge", "parents": [ours_id, theirs_id], "base": base_id})

    arts = merged.setdefault("artifacts", [])

    # 2. Overlay theirs's changed/added model artifacts. `changed`/`added` name the components THEIRS
    #    revised/introduced; bring in the model artifacts of THEIRS that carry those symbols, preferring
    #    theirs's version on an artifact_id collision (dedup by artifact_id).
    changed_added = set(report["delta"].get("changed", [])) | set(report["delta"].get("added", []))
    if changed_added:
        their_models = [a for a in theirs.get("artifacts", []) or []
                        if a.get("artifact_type") in _MODEL_TYPES and _model_src(a)]
        by_id = {a.get("artifact_id"): i for i, a in enumerate(arts)}
        for m in their_models:
            syms = set(_top_level_defs(_model_src(m)).keys())
            if not (syms & changed_added):
                continue
            aid = m.get("artifact_id")
            m_copy = _copy.deepcopy(m)
            if aid in by_id:
                arts[by_id[aid]] = m_copy  # prefer theirs's version for a changed/added component
            else:
                by_id[aid] = len(arts)
                arts.append(m_copy)

    # 4. A merge action (added first so its id is available to the materialized artifacts/residuals).
    existing_ids = [a.get("id") for a in merged.get("actions", []) or [] if isinstance(a.get("id"), int)]
    merge_action_id = (max(existing_ids) + 1) if existing_ids else 1
    merged.setdefault("actions", []).append({
        "id": merge_action_id,
        "type": "merge",
        "rationale": "combine ours + theirs",
    })

    # 3a. CarriedForward artifacts — one per carried result. When THEIRS carries a STRONGER standing
    #     result for the same subject (ORACLE_SPEC v0.2 §6), its artifact rides along in the merged trace
    #     (deduped by id) and the CarriedForward names it as `preferred_result_id`.
    by_id_now = {a.get("artifact_id"): i for i, a in enumerate(arts)}
    for c in report["carried_forward"]:
        rid = c["result_id"]
        payload = {
            "basis": c.get("basis"),
            "symbol": c.get("symbol"),
            "closure": c.get("closure"),
        }
        if c.get("strength"):
            payload["strength"] = c["strength"]
        derived = [rid]
        if c.get("preferred") == "theirs" and c.get("theirs_result_id"):
            trid = c["theirs_result_id"]
            payload["preferred_result_id"] = trid
            payload["theirs_strength"] = c.get("theirs_strength")
            if trid not in by_id_now:
                their_art = _artifact_by_id(theirs, trid)
                if their_art:
                    arts.append(_copy.deepcopy(their_art))
                    by_id_now[trid] = len(arts) - 1
            derived.append(trid)
        arts.append({
            "artifact_id": f"carried-{rid}",
            "artifact_type": "CarriedForward",
            "producer_action_id": merge_action_id,
            "derived_from": derived,
            "payload": payload,
        })

    # 3b/3c. Residuals — needs_rereasoning (per re-reasoned result) and coverage_regression.
    residuals = merged.setdefault("residuals", [])
    for rr in report["rereason"]:
        residuals.append({
            "residual_id": rr["residual_id"],
            "kind": "needs_rereasoning",
            "status": rr.get("status", "open"),
            "statement": rr.get("statement"),
            "derived": True,
            "introduced_by_action_id": merge_action_id,
            "target": rr.get("target"),
        })
    for cr in report.get("coverage_regressions", []):
        residuals.append({
            "residual_id": cr["residual_id"],
            "kind": "coverage_regression",
            "status": cr.get("status", "open"),
            "statement": cr.get("statement"),
            "severity": cr.get("severity"),
            "derived": True,
            "introduced_by_action_id": merge_action_id,
            "goal_id": cr.get("goal_id"),
        })

    # 5. Totality: every standing result is represented exactly once (CarriedForward OR needs_rereasoning).
    standing_ids = {r["result_id"] for r in _standing_results(ours)}
    carried_ids = {c["result_id"] for c in report["carried_forward"]}
    rereason_ids = {rr["result_id"] for rr in report["rereason"]}
    assert carried_ids.isdisjoint(rereason_ids), "combine: a result was both carried and re-reasoned"
    assert carried_ids | rereason_ids == standing_ids, "combine: standing results not totally represented"
    assert report["totality_ok"], "combine: merge report totality invariant failed"

    return merged


def _coverage_regressions(ours, theirs, delta):
    """Goal-COVERAGE layer of the merge (SelectorRegression, realized over `goal.scope`): a merge that
    changes WHAT A GOAL MUST COVER — adds/removes an in-scope component — regresses the obligation, even
    when no existing proof's closure changed (that's the distinct RESULT-level concern above).

    For each OURS goal with a non-empty `scope`:
      * added in-scope, unproven  -> regression. A component in `delta["added"]` that is in the goal's
        scope AND has NO covering standing result in the MERGED view (no proved/sat VerificationResult or
        StateSpaceAnalysisResult about it) widened the goal's surface with unproven ground.
      * removed in-scope          -> coverage shrank (lower severity: the goal's surface got smaller).

    Renames are already reconciled by `merge_delta` (matched renames are excluded from `added`/`removed`),
    so using the post-rename delta sets here never double-counts a rename as add+remove.

    One entry per affected goal, aggregating its added/removed members. Returns [] when no goal has scope
    or no membership changed."""
    goals = ours.get("goals", []) or []
    if not goals:
        return []
    added = delta.get("added", [])
    removed = delta.get("removed", [])
    if not added and not removed:
        return []

    # Covering evidence in the MERGED view: a component is "covered" if there is a standing proof/ssa
    # about it in EITHER side (the added symbol comes from theirs, so its proof — if any — lives there).
    covered = {r["symbol"] for r in _standing_results(ours)}
    covered |= {r["symbol"] for r in _standing_results(theirs)}

    out = []
    for i, goal in enumerate(goals):
        scope = goal.get("scope", []) or []
        if not scope:
            continue
        added_members = [c for c in added if _in_scope(c, scope) and c not in covered]
        removed_members = [c for c in removed if _in_scope(c, scope)]
        if not added_members and not removed_members:
            continue
        gid = goal.get("id") or goal.get("goal_id") or goal.get("intent") or f"goal-{i}"
        parts = []
        if added_members:
            parts.append(f"gained {len(added_members)} in-scope unproven component(s) "
                         f"({', '.join(added_members)})")
        if removed_members:
            parts.append(f"lost {len(removed_members)} in-scope component(s) "
                         f"({', '.join(removed_members)})")
        # Added unproven ground is the hard regression; a pure shrink is a lower-severity note.
        severity = "medium" if added_members else "low"
        out.append({
            "residual_id": f"coverage-{gid}",
            "kind": "coverage_regression",
            "status": "open",
            "derived": True,
            "goal_id": gid,
            "scope": scope,
            "added_members": added_members,
            "removed_members": removed_members,
            "statement": f"Goal `{gid}` " + "; ".join(parts) + ".",
            "severity": severity,
        })
    return out

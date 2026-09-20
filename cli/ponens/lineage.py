"""Artifact lineage / provenance over a trace — a reusable primitive.

The trace links artifacts via `derived_from` (parent artifact ids); an artifact's *lineage* is the
transitive closure of that relation. These helpers answer, for a SPECIFIC artifact, "what produced it,
and does its provenance root in a given code component / kind of step?" — e.g. does this
`VerificationResult` trace back to autoformalizing `settle`?

This is the substrate for Goal-Contract acceptance resolution (GOAL_CONTRACT_v0_2 §4 — resolve by
lineage, not description text) and for provenance policies (APPLY_FORMAL_METHODS_PACK — "a proof or a
decomposition in its lineage"). Kept dependency-free (walks the trace dict only) so both `goals.py`
and the policy engine can use it without an import cycle.
"""


def _artifacts_by_id(trace):
    return {a.get("artifact_id"): a for a in trace.get("artifacts", []) if isinstance(a, dict)}


def _payload(a):
    return (a or {}).get("payload") or {}


def ancestor_ids(artifact_id, trace, _by_id=None, _seen=None):
    """The transitive `derived_from` closure of an artifact — its ancestor ids (excluding itself).

    Cycle-safe (a malformed trace with a `derived_from` cycle terminates)."""
    by_id = _by_id if _by_id is not None else _artifacts_by_id(trace)
    seen = _seen if _seen is not None else set()
    out = set()
    art = by_id.get(artifact_id)
    if not art:
        return out
    for pid in art.get("derived_from") or []:
        if pid in seen:
            continue
        seen.add(pid)
        out.add(pid)
        out |= ancestor_ids(pid, trace, by_id, seen)
    return out


def lineage_artifacts(artifact_id, trace):
    """The artifact plus all its ancestors, as artifact dicts (the artifact itself first)."""
    by_id = _artifacts_by_id(trace)
    self_art = by_id.get(artifact_id)
    if not self_art:
        return []
    return [self_art] + [by_id[i] for i in ancestor_ids(artifact_id, trace, by_id) if i in by_id]


def lineage_types(artifact_id, trace):
    """The set of `artifact_type`s appearing in an artifact's lineage (self + ancestors)."""
    return {a.get("artifact_type") for a in lineage_artifacts(artifact_id, trace)}


def _lineage_symbols(artifact_id, trace):
    """(specific_targets, model_symbols) over an artifact's lineage, read from STRUCTURED fields.

    `specific_targets` — per-artifact `target_symbol`s: a VerificationGoal, Decomp, or targeted Diff
    names the ONE component it is about. `model_symbols` — the broader set an IMLModel formalized.
    The specific targets, when present, pin the component precisely; the model's full symbol list is
    only a fallback for artifacts that declare no target of their own (otherwise a decomposition of
    `fee_tier` would look like it "roots in" every symbol the shared model happens to contain)."""
    specific, model = set(), set()
    for a in lineage_artifacts(artifact_id, trace):
        p = _payload(a)
        ts = p.get("target_symbol") or a.get("target_symbol")
        if ts:
            specific.add(ts)
        for s in (p.get("symbols") or []):
            if isinstance(s, str):
                model.add(s)
            elif isinstance(s, dict) and s.get("name"):
                model.add(s["name"])
    return specific, model


def source_symbols(artifact_id, trace):
    """The code symbols / components an artifact's lineage rests on (specific targets ∪ model symbols)."""
    specific, model = _lineage_symbols(artifact_id, trace)
    return specific | model


def roots_in_component(artifact_id, component, trace):
    """Does this artifact's lineage rest SPECIFICALLY on the given component (function / symbol)? An
    artifact that declares its own `target_symbol` is about THAT symbol — not every symbol the shared
    model formalized. Only when nothing in the lineage names a target do we fall back to model symbols.

    ADDITIVE component-identity path (2d): when the trace carries stamped `component_ids` (via
    `assign_component_ids`, injected by enrich), the artifact ALSO roots in `component` if its own (or a
    lineage ancestor's) `target_component_id` equals the component id that the NAME `component` currently
    resolves to. This makes rooting FOLLOW A RENAME (clamp -> clamp_int chains to the same component id).
    The result is `name_result OR component_id_result` — purely additive: a trace with no component_ids
    is byte-identical to the pre-2d behavior, and nothing that matched by name before stops matching."""
    specific, model = _lineage_symbols(artifact_id, trace)
    name_result = component in specific if specific else component in model
    if name_result:
        return True

    # Component-identity alternative — only when the trace has been stamped.
    by_name = _component_by_name(trace)
    if not by_name:
        return False
    want = by_name.get(component)
    if want is None:
        return False
    return want in _lineage_component_ids(artifact_id, trace)


def _component_by_name(trace):
    """The trace's LATEST-wins `name -> component_id` map, recovered from stamped `component_ids` on
    model artifacts (`assign_component_ids`). Empty dict when the trace was never stamped — the signal
    that turns the whole component-identity path off (pre-2d behavior). Latest wins: model artifacts are
    read in ascending `producer_action_id` so a later revision's mapping overrides an earlier one."""
    models = [a for a in trace.get("artifacts", []) or []
              if isinstance(a, dict) and (_payload(a).get("component_ids"))]
    models.sort(key=lambda a: a.get("producer_action_id") or 0)
    out = {}
    for m in models:
        for name, cid in (_payload(m).get("component_ids") or {}).items():
            out[name] = cid
    return out


def _lineage_component_ids(artifact_id, trace):
    """The set of `target_component_id`s stamped on an artifact's lineage (self + ancestors) — mirrors
    `_lineage_symbols`'s specific-target read, but over the stamped component id. A VerificationResult
    has no target of its own; its VerificationGoal (an ancestor) carries the `target_component_id`."""
    out = set()
    for a in lineage_artifacts(artifact_id, trace):
        p = _payload(a)
        cid = p.get("target_component_id") or a.get("target_component_id")
        if cid:
            out.add(cid)
    return out


def autoformalized(artifact_id, trace):
    """True iff an `IMLModel` is in the lineage — i.e. the evidence traces back to autoformalization
    of a code component (not hand-authored IML)."""
    return "IMLModel" in lineage_types(artifact_id, trace)


def decomposition_backed(artifact_id, trace):
    """True iff a region `Decomp` is in the lineage — e.g. a test suite generated FROM a decomposition
    rather than ad hoc (a stronger provenance; GOAL_CONTRACT §5 / APPLY_FORMAL_METHODS)."""
    return "Decomp" in lineage_types(artifact_id, trace)


def provenance(artifact_id, trace):
    """A structured provenance summary for a specific artifact — what it is, the code it rests on, and
    which analysis steps are in its lineage. The reusable 'explain this artifact' view."""
    by_id = _artifacts_by_id(trace)
    art = by_id.get(artifact_id)
    if not art:
        return None
    return {
        "artifact_id": artifact_id,
        "artifact_type": art.get("artifact_type"),
        "source_symbols": sorted(source_symbols(artifact_id, trace)),
        "lineage_types": sorted(t for t in lineage_types(artifact_id, trace) if t),
        "autoformalized": autoformalized(artifact_id, trace),
        "decomposition_backed": decomposition_backed(artifact_id, trace),
        "ancestor_ids": sorted(ancestor_ids(artifact_id, trace)),
    }


# --- Residuals as artifacts (Trace Spec §13, v1.8) -----------------------------------------------
# A residual — the trace's *negative space* (an assumption relied on, a claim left unverified, an
# out-of-scope item, a known limitation, a question deferred to review) — is a first-class artifact of
# `artifact_type` "Residual". Its residual-specific fields live in `payload`; it anchors into the
# lineage DAG via `derived_from` (the artifact it qualifies). Pre-1.8 traces carried these in a
# separate top-level `residuals` list; the accessors below read BOTH shapes so old traces keep
# working, and `migrate_residuals` folds a legacy list into artifacts.

RESIDUAL_TYPE = "Residual"

# residual fields carried in an artifact's `payload` (and promoted into the flat surface dict)
_RESIDUAL_PAYLOAD_KEYS = (
    "kind", "defeater_kind", "severity", "status", "source", "statement", "target",
    "related_artifact_ids", "suggested_check", "introduced_by_action_id", "tags", "derived",
    # Plain-language lead (`summary`) shown first by viewers, with the formal IML kept as detail —
    # the `property` that was checked and a `counterexample` input that breaks it (§13).
    "summary", "property", "counterexample",
)


def is_residual(a):
    return isinstance(a, dict) and a.get("artifact_type") == RESIDUAL_TYPE


def residual_anchor(r):
    """The artifact id(s) a residual hangs off in the DAG: its `target` (when it points at an artifact)
    then any `related_artifact_ids`. Empty when unanchored (e.g. the residual targets an action)."""
    out = []
    tgt = r.get("target") or {}
    if tgt.get("target_type") == "artifact" and tgt.get("target_id"):
        out.append(tgt["target_id"])
    for rid in r.get("related_artifact_ids") or []:
        if rid not in out:
            out.append(rid)
    return out


def _residual_name(r):
    kind = (r.get("kind") or "residual").replace("_", " ")
    stmt = (r.get("statement") or "").strip()
    short = (stmt[:48] + "…") if len(stmt) > 49 else stmt
    return f"{kind}: {short}" if short else kind


def residual_to_artifact(r):
    """Convert a legacy residual dict (§13 pre-1.8) into a first-class Residual artifact."""
    payload = {k: r[k] for k in _RESIDUAL_PAYLOAD_KEYS if r.get(k) is not None}
    art = {
        "artifact_id": r.get("residual_id"),
        "artifact_type": RESIDUAL_TYPE,
        "name": _residual_name(r),
        "payload": payload,
    }
    anchor = residual_anchor(r)
    if anchor:
        art["derived_from"] = anchor
    if r.get("statement"):
        art["summary"] = r["statement"]
    if r.get("introduced_by_action_id") is not None:
        art["producer_action_id"] = r["introduced_by_action_id"]
    return art


def artifact_to_residual(a):
    """Project a Residual artifact back to the flat residual dict the surface / §13 policies consume."""
    p = _payload(a)
    r = {"residual_id": a.get("artifact_id")}
    for k in _RESIDUAL_PAYLOAD_KEYS:
        if p.get(k) is not None:
            r[k] = p[k]
    if "statement" not in r and a.get("summary"):
        r["statement"] = a["summary"]
    return r


# --- closing a residual (v1.14) ---------------------------------------------------------------------
#
# A gap is closed by APPENDING a `ResidualResolution` artifact that names it, never by editing the
# residual's `status` in place. Editing is indistinguishable from never having declared the gap: the
# record loses who decided, when, on what grounds, and at which point in the work - and a reader cannot
# tell a waiver from a deletion. A trace is append-only everywhere else; its negative space should be
# no different.
#
# The effective status is therefore DERIVED: the declared status is the base, and the last resolution
# naming the residual wins. Superseding a resolution is itself an append, so a waiver that was later
# reversed stays visible as both.

RESOLUTION_TYPE = "ResidualResolution"

# A resolution may only move a gap to one of these. `open` is not among them - a residual is born open
# and re-opening is a new resolution back to `acknowledged`, not a pretence it was never closed.
RESOLUTION_STATUSES = ("acknowledged", "addressed", "waived")


def is_resolution(a):
    return isinstance(a, dict) and a.get("artifact_type") == RESOLUTION_TYPE


def _resolution_order(a):
    """Trace order: by the action that made the decision when it is known, else last. Ties keep list
    order, which is append order, so two resolutions in one action resolve predictably."""
    aid = a.get("producer_action_id")
    return aid if isinstance(aid, int) else float("inf")


def resolutions_of(trace):
    """Every resolution in the trace, oldest first, grouped by the residual it closes."""
    rows = []
    for i, a in enumerate(trace.get("artifacts") or []):
        if not is_resolution(a):
            continue
        p = _payload(a)
        rid = p.get("residual_id")
        if not rid:
            continue
        rows.append((_resolution_order(a), i, rid, {
            "resolution_id": a.get("artifact_id"),
            "status": p.get("status"),
            "justification": p.get("justification"),
            "by": p.get("by"),
            "at": p.get("at"),
            "action_id": a.get("producer_action_id"),
            "evidence_artifact_ids": p.get("evidence_artifact_ids") or [],
        }))
    out = {}
    for _, _, rid, row in sorted(rows, key=lambda t: (t[0], t[1])):
        out.setdefault(rid, []).append(row)
    return out


# A justification is a CLAIM, and the way a claim is attacked in this model is a Defeater (§13.2): an
# open one means the claim it targets must not be treated as established. A `ResidualResolution` is an
# artifact with an id, so a defeater can target it like any other claim - and when one stands, the
# closure does not hold and the gap is open again. That is how a justification is invalidated without
# being removed: both the waiver and the reason it does not hold stay in the record, and a reader sees
# the argument rather than a silent edit.
#
# Defeating a defeater's own resolution is legal and terminates here by bounded iteration. Eight rounds
# is far past anything real (each round can only settle one more link of a chain of contested
# closures); a tangle that has not settled by then is NOT resolved in favour of closure - see below.
_CONTEST_ROUNDS = 8


def _contested_index(residuals):
    """artifact id -> the residual ids of the Defeaters aimed at it."""
    out = {}
    for r in residuals:
        if str(r.get("kind") or "").lower() != "defeater":
            continue
        rid = r.get("residual_id")
        for ref in residual_anchor(r):
            out.setdefault(ref, []).append(rid)
    return out


def apply_resolutions(residuals, trace):
    """Stamp each residual with its DERIVED status. Mutates and returns the list.

    `status` becomes the status of the last resolution IN FORCE; `declared_status` keeps what the
    producer originally wrote, `resolution` is the one in force, and `resolutions` the full history -
    so a consumer that only reads `status` (every policy, `next`, the grader) gets the right answer,
    and one that wants the audit trail has it without re-deriving anything.

    A resolution contested by an open Defeater is NOT in force: the gap it claimed to close is open
    again, and `resolution_contested_by` names the defeaters that put it there."""
    res = resolutions_of(trace)
    if not res:
        return residuals

    by_id = {r.get("residual_id"): r for r in residuals}
    contested = _contested_index(residuals)
    # Seed from what each producer declared, then settle.
    status = {rid: (r.get("status") or "open") for rid, r in by_id.items()}

    def live_defeaters(resolution_id):
        return [d for d in contested.get(resolution_id, []) if status.get(d, "open") == "open"]

    settled = False
    for _ in range(_CONTEST_ROUNDS):
        changed = False
        for rid, r in by_id.items():
            eff = r.get("status") or "open"
            for row in res.get(rid, []):
                if live_defeaters(row["resolution_id"]):
                    continue                    # contested: this one closes nothing
                if row.get("status"):
                    eff = row["status"]
            if status.get(rid) != eff:
                status[rid] = eff
                changed = True
        if not changed:
            settled = True
            break

    for rid, r in by_id.items():
        hist = res.get(rid)
        if not hist:
            continue
        r["declared_status"] = r.get("status", "open")
        r["resolutions"] = hist
        in_force = None
        for row in hist:
            # A tangle that did not settle is read AGAINST closure: an unresolvable argument about
            # whether a gap is closed is not a closed gap. Failing the other way would let a cycle
            # close a gap that nobody can show is closed.
            blockers = contested.get(row["resolution_id"], []) if not settled else live_defeaters(row["resolution_id"])
            row["contested_by"] = list(blockers)
            if not blockers and row.get("status"):
                in_force = row
        if in_force is not None:
            r["status"] = in_force["status"]
            r["resolution"] = in_force
            if in_force.get("justification") and not r.get("justification"):
                r["justification"] = in_force["justification"]
        else:
            # Every closure is contested - the gap stands as declared, and we say who put it back.
            r["status"] = r["declared_status"]
            r["resolution_contested_by"] = sorted(
                {d for row in hist for d in (row.get("contested_by") or [])})
    return residuals


# --- amending the definition of done (v1.14) ---------------------------------------------------------
#
# The same rule as closing a gap, applied to the thing that says what "done" means. Withdrawing an
# acceptance criterion is the sharper case: a gap that is waived still READS as a gap, but a criterion
# that is deleted leaves nothing behind at all - the goal simply reads met. Measured on the shipped
# Stripe demo: dropping the one criterion that was not met took it from 88% to 100%, and `ponens trace
# integrity` (which indexed only ALREADY-DONE items) reported nothing lost.
#
# So a withdrawal appends a `GoalAmendment` carrying the criterion VERBATIM. It leaves the goal's
# `acceptance` list as the current definition of done - consumers need one unambiguous answer to "what
# is being asked" - while the record keeps what was asked for before, who withdrew it and why.

AMENDMENT_TYPE = "GoalAmendment"

AMENDMENT_CHANGES = ("item_withdrawn", "goal_withdrawn", "goal_replaced", "criteria_reviewed")


def is_amendment(a):
    return isinstance(a, dict) and a.get("artifact_type") == AMENDMENT_TYPE


def amendments_of(trace, goal_id=None):
    """Every amendment in the trace, oldest first, optionally for one goal."""
    rows = []
    for i, a in enumerate(trace.get("artifacts") or []):
        if not is_amendment(a):
            continue
        p = _payload(a)
        if goal_id is not None and p.get("goal_id") != goal_id:
            continue
        aid = a.get("producer_action_id")
        rows.append((aid if isinstance(aid, int) else float("inf"), i,
                     dict(p, amendment_id=a.get("artifact_id"), action_id=aid)))
    return [r for _, _, r in sorted(rows, key=lambda t: (t[0], t[1]))]


def amendment_artifact(goal_id, change, reason, action_id, seq, was=None, item_id=None, by=None, at=None):
    """Build the record of one amendment. `was` is the thing as it stood - the whole point: withdrawn
    from the definition of done is not the same as gone from the record."""
    payload = {"goal_id": goal_id, "change": change, "reason": reason}
    if item_id is not None:
        payload["item_id"] = item_id
    if was is not None:
        payload["was"] = was
    if by:
        payload["by"] = by
    if at:
        payload["at"] = at
    what = item_id or goal_id
    return {
        "artifact_id": f"ga{seq}",
        "artifact_type": AMENDMENT_TYPE,
        "name": f"{change}: {what}",
        "summary": reason,
        "producer_action_id": action_id,
        "derived_from": [],
        "payload": payload,
    }


def residual_surface(trace):
    """The trace's residual surface as flat residual dicts — Residual artifacts projected back to the
    §13 shape, plus any legacy top-level `residuals` (deduped by id). The single accessor every residual
    consumer (policies, goals, faithfulness, report) reads, independent of how a trace stores them."""
    out, seen = [], set()
    for a in trace.get("artifacts", []) or []:
        if not is_residual(a):
            continue
        r = artifact_to_residual(a)
        rid = r.get("residual_id")
        if rid in seen:
            continue
        seen.add(rid)
        out.append(r)
    for r in trace.get("residuals", []) or []:
        rid = r.get("residual_id")
        if rid in seen:
            continue
        seen.add(rid)
        out.append(r)
    # Closure is derived, not stored (see RESOLUTION_TYPE above). Applying it HERE is what makes every
    # existing consumer - the validator, the policy witnesses, `next`, the grader, the report - agree
    # on whether a gap is open without any of them learning about resolutions.
    return apply_resolutions(out, trace)


def migrate_residuals(trace):
    """Fold a legacy top-level `residuals` list into Residual artifacts (idempotent). Returns the count
    migrated and empties `residuals` so re-runs are no-ops and legacy readers see nothing stale."""
    legacy = trace.get("residuals") or []
    if not legacy:
        return 0
    arts = trace.setdefault("artifacts", [])
    have = {a.get("artifact_id") for a in arts if is_residual(a)}
    n = 0
    for r in legacy:
        if r.get("residual_id") in have:
            continue
        arts.append(residual_to_artifact(r))
        n += 1
    trace["residuals"] = []
    return n

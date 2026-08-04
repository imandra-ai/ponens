"""Artifact lineage / provenance over a trace — a reusable primitive.

The trace links artifacts via `derived_from` (parent artifact ids); an artifact's *lineage* is the
transitive closure of that relation. These helpers answer, for a SPECIFIC artifact, "what produced it,
and does its provenance root in a given code component / kind of step?" — e.g. does this
`VerificationResult` trace back to autoformalizing `settle`?

This is the substrate for Goal-Contract acceptance resolution (GOAL_CONTRACT_v0_1 §4 — resolve by
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
    model formalized. Only when nothing in the lineage names a target do we fall back to model symbols."""
    specific, model = _lineage_symbols(artifact_id, trace)
    return component in specific if specific else component in model


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
    "kind", "severity", "status", "source", "statement", "target",
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
    return out


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

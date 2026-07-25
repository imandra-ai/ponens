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


def source_symbols(artifact_id, trace):
    """The code symbols / components an artifact's lineage rests on — read from STRUCTURED fields, not
    free text: each lineage artifact's `target_symbol` (VerificationGoals) and `payload.symbols`
    (an IMLModel's formalized symbols)."""
    syms = set()
    for a in lineage_artifacts(artifact_id, trace):
        p = _payload(a)
        ts = p.get("target_symbol") or a.get("target_symbol")
        if ts:
            syms.add(ts)
        for s in (p.get("symbols") or []):
            if isinstance(s, str):
                syms.add(s)
            elif isinstance(s, dict) and s.get("name"):
                syms.add(s["name"])
    return syms


def roots_in_component(artifact_id, component, trace):
    """Does this artifact's lineage involve the given code component (function / symbol)?"""
    return component in source_symbols(artifact_id, trace)


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

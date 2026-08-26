"""Component-identity resolver: decide whether a code descriptor is the SAME component as a prior one
(-> reuse its component_id) or a NEW one (-> mint a fresh id). The Python realization of the PROVED
model in `formal/component/identity.iml` (the conformance spec).

The dangerous error is CONFLATION: reusing an id for a genuinely-DIFFERENT code element. So the SAFE
fallback is MINT-NEW ("treat as a distinct component") — conflation is the unsound error, and the
resolver NEVER guesses when the signal is weak or ambiguous.

Tiers, most-confident first (mirrors identity.iml `resolve`):
  1. LINEAGE      — a producer-declared same-model-line link (`lineage_id is not None`) -> reuse it.
  2. UNIQUE-EXACT — exactly ONE prior with an identical fingerprint -> reuse it.
                    (0 -> nothing to reuse; >1 -> ambiguous -> mint, never conflate.)
  3. SIMILARITY   — a confident, UNIQUE match: best >= SIM_MIN AND best - second >= SIM_MARGIN ->
                    reuse the best candidate. (Same floor/margin as ambiguity.iml: 80 / 15.)
  4. else         -> MINT (the caller then allocates a fresh id).

Similarity is an integer percentage (0..100). `_line_similarity` is the Sørensen–Dice coefficient over
the SET of trimmed non-empty lines — the concrete signal the abstract `best`/`second` percentages stand
for in the proved model.
"""

import fnmatch
import re

SIM_MIN = 80
SIM_MARGIN = 15


def _lines(s):
    """The SET of trimmed, non-empty lines of `s`."""
    return {ln.strip() for ln in (s or "").splitlines() if ln.strip()}


def _line_similarity(a, b):
    """Sørensen–Dice over the SET of trimmed non-empty lines, as an integer percentage 0..100:
    `2*|A∩B| / (|A|+|B|)`. Empty/empty -> 0 (no lines to agree on)."""
    A, B = _lines(a), _lines(b)
    denom = len(A) + len(B)
    if denom == 0:
        return 0
    return (2 * len(A & B) * 100) // denom


def confident_sim(best, second):
    """The confident-similarity predicate (identity.iml `confident_sim`): the best candidate clears the
    minimum AND beats the runner-up by the margin. Integer percents."""
    return best >= SIM_MIN and best - second >= SIM_MARGIN


def resolve_component_id(lineage_id, exact_count, exact_id, best, second, sim_id):
    """The low-level proved resolver (identity.iml `resolve`), 4 tiers in order. Returns
    `("reuse", <id>)` or `("mint", None)`.

      lineage_id  : a producer-declared same-model-line link (not None) if present.
      exact_count : # priors with an identical fingerprint.
      exact_id    : the sole exact match's id (meaningful only when exact_count == 1).
      best,second : top-two similarity percentages (0..100).
      sim_id      : the best similarity candidate's id.
    Returns mint when unsure — the CALLER allocates the fresh id."""
    if lineage_id is not None:
        return ("reuse", lineage_id)               # Tier 1: lineage wins
    if exact_count == 1:
        return ("reuse", exact_id)                 # Tier 2: unique exact
    if confident_sim(best, second):
        return ("reuse", sim_id)                   # Tier 3: confident sim
    return ("mint", None)                          # Tier 4: mint new


def match_descriptor(descriptor, candidates, lineage_id=None):
    """Convenience wrapper over `resolve_component_id`.

      descriptor : {"fingerprint": ..., "text": ...}
      candidates : [{"id": ..., "fingerprint": ..., "text": ...}]

    Computes `exact_count` (# candidates whose fingerprint == descriptor's), `exact_id` (the sole exact
    match's id when the count is exactly 1), and `best`/`second`/`sim_id` from `_line_similarity` of the
    descriptor's text against each candidate's text, then calls `resolve_component_id`. Returns
    `("reuse", id)` or `("mint", None)`."""
    fp = descriptor.get("fingerprint")
    text = descriptor.get("text")

    exact = [c for c in candidates if c.get("fingerprint") == fp]
    exact_count = len(exact)
    exact_id = exact[0].get("id") if exact_count == 1 else None

    # Best / second similarity across candidates, tracking the best candidate's id.
    best, second, sim_id = 0, 0, None
    for c in candidates:
        sim = _line_similarity(text, c.get("text"))
        if sim > best:
            second = best
            best = sim
            sim_id = c.get("id")
        elif sim > second:
            second = sim

    return resolve_component_id(lineage_id, exact_count, exact_id, best, second, sim_id)


# ================================================================
# 2c — STAMP component_ids on a trace (durable component identity)
# ================================================================
#
# `assign_component_ids` walks the trace's model artifacts oldest-first, groups their top-level symbols
# into stable COMPONENTS via the proved resolver above, and returns the grouping. It is the record-time
# realization of identity.iml's `resolve` (which decides SAME vs NEW per descriptor): each symbol either
# REUSES a known component id (lineage / unique-exact / confident-unique similarity) or MINTS a fresh
# `cmpN`. The dangerous error is conflation, so the resolver mints when the signal is weak or ambiguous.
#
# The point: a component_id FOLLOWS A RENAME (clamp -> clamp_int, identical body -> same cmp), so goal
# rooting and staleness can chain across the rename by component instead of by name. Purely additive:
# the caller (enrich) STAMPS the ids onto a COPY/projection; the source trace on disk is never mutated.


def _same_model_line(m1, m2):
    """Are two model artifacts revisions of the SAME model line (share a `derived_from` source node)?
    Mirrors goals.py `_same_model_line`: bare models (no `derived_from`) are treated as one evolving
    line. Used to supply the lineage tier — a symbol carried across two revisions of one model line is a
    producer-declared same-model-line link, the highest-confidence identity signal."""
    d1 = set(m1.get("derived_from") or [])
    d2 = set(m2.get("derived_from") or [])
    if not d1 and not d2:
        return True
    return bool(d1 & d2)


def assign_component_ids(trace):
    """Group the trace's model symbols into stable components and STAMP the ids onto the trace's
    descriptors (mutates the trace passed in — call on a COPY / the enrich projection, never the source).

    Walks model artifacts (`artifact_type` in `_MODEL_TYPES`) in ascending `producer_action_id`. Keeps a
    running list of known components `[{id, fingerprint, text, names, model}]`. For each top-level symbol
    of each model, builds its NAME-INDEPENDENT descriptor (`_symbol_descriptor`, exactly as merge.py) and
    resolves it against the known components with the proved `match_descriptor`:

      * lineage tier — if a known component last appeared in a model on the SAME model line as this one
        (shared `derived_from`) and under the SAME name, that is a producer-declared same-model-line link
        -> its id is passed as `lineage_id` (Tier 1: lineage wins).
      * `("reuse", id)` -> the same component: update its fingerprint / text / names / model to this
        (latest) revision.
      * `("mint", None)` -> a new component, id `f"cmp{n}"`.

    Stamps, on the trace:
      * each model artifact  -> `payload.component_ids = {symbol_name: component_id}`.
      * each VerificationGoal -> `payload.target_component_id` = the component id of its `target_symbol`
        AS OF that goal's revision (the latest component id known for that name at/ before the goal's
        `producer_action_id`).

    Returns `{"components": [...], "by_name": {name: component_id}}` where `by_name` is LATEST-wins — the
    convenience map a goal criterion authored with a NAME uses to reach the current component id."""
    # Imported lazily to avoid any import-order coupling (goals.py imports this module transitively).
    from .merge import _symbol_descriptor
    from .goals import _top_level_defs, _model_src, _MODEL_TYPES

    arts = trace.get("artifacts", []) or []
    models = [a for a in arts
              if a.get("artifact_type") in _MODEL_TYPES and _model_src(a)]
    models.sort(key=lambda a: (a.get("producer_action_id") or 0))

    known = []            # [{id, fingerprint, text, names:set, model}]
    n_minted = [0]

    def _mint():
        cid = f"cmp{n_minted[0]}"
        n_minted[0] += 1
        return cid

    # Per-name history of (step, component_id) so a VerificationGoal resolves to the component id current
    # AT its own revision — not merely the global latest (which would misattribute a pre-rename goal).
    name_history = {}     # name -> [(step, component_id)] in ascending step order

    for m in models:
        step = m.get("producer_action_id") or 0
        src = _model_src(m)
        defs = _top_level_defs(src)
        stamp = {}
        claimed = set()   # component ids already stamped by an EARLIER symbol of THIS same model
        for sym in defs:
            desc = _symbol_descriptor(src, sym)
            # Two top-level defs that COEXIST in one model are necessarily DISTINCT components — a
            # component already claimed by an earlier symbol of this same model is not a candidate for a
            # later one (otherwise two identical-body siblings would conflate onto one id).
            avail = [c for c in known if c["id"] not in claimed]
            # Lineage tier: a known component that last lived on the SAME model line under the SAME name.
            lineage_id = None
            for c in avail:
                if sym in c["names"] and c.get("model") is not None and _same_model_line(c["model"], m):
                    lineage_id = c["id"]
                    break
            candidates = [{"id": c["id"], "fingerprint": c["fingerprint"], "text": c["text"]}
                          for c in avail]
            decision, cid = match_descriptor(desc, candidates, lineage_id=lineage_id)
            if decision == "reuse":
                comp = next(c for c in known if c["id"] == cid)
                comp["fingerprint"] = desc["fingerprint"]
                comp["text"] = desc["text"]
                comp["names"].add(sym)
                comp["model"] = m
            else:
                cid = _mint()
                known.append({"id": cid, "fingerprint": desc["fingerprint"], "text": desc["text"],
                              "names": {sym}, "model": m})
            stamp[sym] = cid
            claimed.add(cid)
            name_history.setdefault(sym, []).append((step, cid))
        m.setdefault("payload", {})["component_ids"] = stamp

    def _comp_at(name, at):
        """The component id known for `name` as of step `at` (latest at/before `at`; else the earliest)."""
        hist = name_history.get(name)
        if not hist:
            return None
        prior = [(s, c) for (s, c) in hist if s <= at]
        chosen = prior[-1] if prior else hist[0]
        return chosen[1]

    # Latest-wins name -> component id, for a NAME-authored criterion to reach the current component.
    by_name = {}
    for name, hist in name_history.items():
        by_name[name] = hist[-1][1]

    # Stamp each VerificationGoal with the component id of its target_symbol as of that goal's revision.
    for a in arts:
        if a.get("artifact_type") != "VerificationGoal":
            continue
        p = a.get("payload") or {}
        tsym = p.get("target_symbol")
        if not tsym:
            continue
        cid = _comp_at(tsym, a.get("producer_action_id") or 0)
        if cid is not None:
            a.setdefault("payload", {})["target_component_id"] = cid

    return {"components": known, "by_name": by_name}


# ================================================================
# §8.8 Phase 2: selector resolver — enumerate the elements a quantifier ranges over
# ================================================================
#
# A selector maps to a list of ELEMENTS, element = {symbol, component_id?, file?}. It reuses the data the
# trace already carries: model top-level symbols (_top_level_defs), the component_ids stamped by
# assign_component_ids, model/source file paths, and high_stakes_paths. Deduped by component_id (stable
# identity) else symbol. An unknown/empty selector returns [] — the quantifier turns [] into `todo`
# (never a vacuous `done`; see eval_formula).

_SRC_EXTS = ("py", "ts", "tsx", "js", "jsx", "mjs", "cjs", "iml", "ml", "go", "rs", "java", "kt", "cs", "scala", "fs")


def _artifact_path(a):
    """Best-effort file path for an artifact: a producer-stamped path field, else a name/summary that
    looks like a path. None when the trace carries no path (then glob/module can't place the symbol)."""
    p = a.get("payload") or {}
    for k in ("path", "file", "file_path", "src_path", "source_file", "source_path"):
        v = p.get(k) or a.get(k)
        if isinstance(v, str) and v:
            return v
    for k in ("name", "summary"):
        v = a.get(k)
        if isinstance(v, str) and ("/" in v or v.rsplit(".", 1)[-1] in _SRC_EXTS):
            return v
    return None


def _model_file(model, trace):
    """The source file a model came from: the model's own path, else its SourceCode ancestor's."""
    f = _artifact_path(model)
    if f:
        return f
    by_id = {a.get("artifact_id"): a for a in (trace.get("artifacts") or [])}
    for src_id in (model.get("derived_from") or []):
        src = by_id.get(src_id)
        if src is not None:
            f = _artifact_path(src)
            if f:
                return f
    return None


def _symbol_index(trace):
    """Latest-per-symbol element list across model artifacts: {symbol, component_id?, file?}. Reads the
    component_ids stamped by assign_component_ids when present (else component_id is None)."""
    from .goals import _top_level_defs, _model_src, _MODEL_TYPES
    arts = trace.get("artifacts") or []
    models = sorted([a for a in arts if a.get("artifact_type") in _MODEL_TYPES and _model_src(a)],
                    key=lambda a: (a.get("producer_action_id") or 0))
    idx = {}  # symbol -> element (latest model wins)
    for m in models:
        stamp = (m.get("payload") or {}).get("component_ids") or {}
        f = _model_file(m, trace)
        for sym in _top_level_defs(_model_src(m)):
            idx[sym] = {"symbol": sym, "component_id": stamp.get(sym), "file": f}
    return list(idx.values())


def _dedup(elements):
    """De-dup by component_id (stable identity) else symbol, order-preserving."""
    seen, out = set(), []
    for e in elements:
        key = ("cid", e["component_id"]) if e.get("component_id") else ("sym", e.get("symbol"))
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def resolve_selector(sel, trace, goal=None):
    """Resolve a §8.8 selector to a list of elements {symbol, component_id?, file?}. Supported:
      {"glob": "payments/**"} -- symbols whose source file matches the glob (needs file paths).
      {"module": "pricing"}   -- symbols whose file path contains that module/path segment.
      {"scope": true}         -- the resolving goal's `scope` symbols (synthesized if unknown to the trace).
      {"tag": "<name>"}       -- BEST-EFFORT over `high_stakes_paths` (the only tag-like surface today).
    Returns [] for an unknown/empty selector."""
    if not isinstance(sel, dict):
        return []
    index = _symbol_index(trace)
    if "glob" in sel:
        pat = sel.get("glob") or ""
        return _dedup([e for e in index if e.get("file") and fnmatch.fnmatch(e["file"], pat)])
    if "module" in sel:
        mod = (sel.get("module") or "").strip()
        if not mod:
            return []

        def _in_module(f):
            if not f:
                return False
            return mod in re.split(r"[\\/.]", f) or mod in f
        return _dedup([e for e in index if _in_module(e.get("file"))])
    if "scope" in sel and sel.get("scope"):
        scope = list((goal or {}).get("scope") or [])
        by_sym = {e["symbol"]: e for e in index}
        return _dedup([by_sym.get(s) or {"symbol": s, "component_id": None, "file": None} for s in scope])
    if "tag" in sel:
        # DOCUMENTED GAP: there is no real symbol->tag index in the trace today. The one tag-like surface
        # is `high_stakes_paths` (substring path fragments), which is NOT keyed by tag name — so a `tag`
        # selector matches symbols whose source file contains a high-stakes fragment, REGARDLESS of the tag
        # name (we cannot tell "money" from "risk" without a real tag source). A proper symbol->tag index
        # is future work; this is the honest best-effort over what exists.
        stakes = trace.get("high_stakes_paths") or []
        return _dedup([e for e in index if e.get("file") and any(p in e["file"] for p in stakes)])
    return []

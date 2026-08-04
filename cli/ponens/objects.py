"""Content-addressed object store (spec §7 `content_ref`; provenance Gap 2).

An immutable blob store keyed by sha256. A trace references large content (source, IML model, generated
tests) by ``content_ref: "sha256:<hex>"`` instead of inlining it, so identical content is stored once
(dedup) and a trace plus its reachable objects form a portable, self-contained bundle.

The on-disk layout is a STABLE SPEC — ``<objects_dir>/sha256/<ab>/<rest>`` — so any producer that can
hash (e.g. the imandra-pi-agent extension) may write blobs directly to the agreed location, and ponens
reads / resolves / gc's them. The store location defaults to ``<.ponens>/objects`` but is overridable
via ``$PONENS_OBJECTS_DIR`` so a co-producer using a different home (``.codelogician``) shares one store.
"""
import hashlib
import os

from .sync import ponens_dir

ALGO = "sha256"
_PREFIX = ALGO + ":"

# Inline payload blobs the store externalizes/resolves. Each ``<field>`` becomes ``<field>_ref``.
# `iml_code` is the imandra-pi-agent IMLModel's model field; `formal_code` its spec-canonical name.
BLOB_FIELDS = ("src_code", "formal_code", "iml_code")


def default_objects_dir():
    """Where blobs live. ``$PONENS_OBJECTS_DIR`` lets a co-producer (e.g. an agent writing under
    ``.codelogician``) point ponens at the same store; otherwise ``<git-root>/.ponens/objects``."""
    return os.environ.get("PONENS_OBJECTS_DIR") or os.path.join(ponens_dir(), "objects")


def hash_bytes(data: bytes) -> str:
    return _PREFIX + hashlib.sha256(data).hexdigest()


def hash_text(text: str) -> str:
    return hash_bytes(text.encode("utf-8"))


def is_ref(value) -> bool:
    """True if ``value`` is a content_ref this store owns (``sha256:<hex>``)."""
    return isinstance(value, str) and value.startswith(_PREFIX) and len(value) > len(_PREFIX)


def _digest(ref: str) -> str:
    return ref.split(":", 1)[1] if ":" in ref else ref


def object_path(ref: str, root=None) -> str:
    """Sharded path for a ref: ``<root>/sha256/<first-2-hex>/<rest>``."""
    root = root or default_objects_dir()
    d = _digest(ref)
    return os.path.join(root, ALGO, d[:2], d[2:])


def put_bytes(data: bytes, root=None) -> str:
    """Store ``data`` and return its ref. Idempotent (content-addressed) and atomic."""
    ref = hash_bytes(data)
    p = object_path(ref, root)
    if not os.path.exists(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = f"{p}.tmp.{os.getpid()}"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, p)  # atomic publish — a partial write is never visible under its final name
    return ref


def put_text(text: str, root=None) -> str:
    return put_bytes(text.encode("utf-8"), root)


def has(ref: str, root=None) -> bool:
    return os.path.exists(object_path(ref, root))


def get_bytes(ref: str, root=None):
    p = object_path(ref, root)
    if not os.path.exists(p):
        return None
    with open(p, "rb") as f:
        return f.read()


def get_text(ref: str, root=None):
    b = get_bytes(ref, root)
    return b.decode("utf-8") if b is not None else None


def referenced_refs(trace) -> set:
    """Every content_ref the trace points at — ``artifact_common.content_ref`` plus any ``sha256:``
    value in an artifact payload (e.g. ``src_code_ref``/``formal_code_ref``). The gc keep-set."""
    refs = set()
    for art in trace.get("artifacts", []):
        if not isinstance(art, dict):
            continue
        if is_ref(art.get("content_ref")):
            refs.add(art["content_ref"])
        payload = art.get("payload")
        if isinstance(payload, dict):
            for v in payload.values():
                if is_ref(v):
                    refs.add(v)
    return refs


def externalize(trace, root=None) -> int:
    """Move inline payload blobs (``BLOB_FIELDS``) into the store, replacing each ``<field>`` with a
    ``<field>_ref: sha256:...`` and dropping the inline copy. Dedup is automatic. Returns the count
    externalized. This is the "prepare a portable bundle" step; ``resolve_payload`` is its inverse."""
    n = 0
    for art in trace.get("artifacts", []):
        payload = art.get("payload") if isinstance(art, dict) else None
        if not isinstance(payload, dict):
            continue
        for field in BLOB_FIELDS:
            val = payload.get(field)
            if isinstance(val, str) and val and not is_ref(val):
                payload[field + "_ref"] = put_text(val, root)
                del payload[field]
                n += 1
    return n


def resolve_payload(payload, root=None) -> dict:
    """Return a copy of ``payload`` with any externalized ``<field>_ref`` resolved back to inline
    ``<field>`` from the store (missing objects are left as the bare ref). For rendering/reporting."""
    if not isinstance(payload, dict):
        return payload
    out = dict(payload)
    for field in BLOB_FIELDS:
        ref = out.get(field + "_ref")
        if is_ref(ref) and field not in out:
            text = get_text(ref, root)
            if text is not None:
                out[field] = text
    return out


def hydrate_trace(trace, root=None) -> int:
    """Inverse of ``externalize``: restore every externalized ``<field>_ref`` back to inline
    ``<field>`` from the store and drop the ref, making the trace a fully self-contained single file
    again (for viewing / handing off). Returns the count rehydrated. A ref whose object is missing is
    left as-is. This is the "receive/view" half of the externalize↔inline round-trip."""
    n = 0
    for art in trace.get("artifacts", []):
        payload = art.get("payload") if isinstance(art, dict) else None
        if not isinstance(payload, dict):
            continue
        for field in BLOB_FIELDS:
            ref = payload.get(field + "_ref")
            if is_ref(ref) and field not in payload:
                text = get_text(ref, root)
                if text is not None:
                    payload[field] = text
                    del payload[field + "_ref"]
                    n += 1
    return n


def gc(trace, root=None) -> int:
    """Delete objects not referenced by ``trace``. Returns the count removed. Single-trace scope — a
    hub-wide gc would union ``referenced_refs`` across all traces before pruning."""
    root = root or default_objects_dir()
    keep = {_digest(r) for r in referenced_refs(trace)}
    algo_dir = os.path.join(root, ALGO)
    if not os.path.isdir(algo_dir):
        return 0
    removed = 0
    for sub in os.listdir(algo_dir):
        subdir = os.path.join(algo_dir, sub)
        if not os.path.isdir(subdir):
            continue
        for name in os.listdir(subdir):
            if (sub + name) not in keep:
                os.remove(os.path.join(subdir, name))
                removed += 1
    return removed


def store_stats(root=None):
    """(object_count, total_bytes) for the store — for ``objects stat``."""
    root = root or default_objects_dir()
    algo_dir = os.path.join(root, ALGO)
    count = total = 0
    if os.path.isdir(algo_dir):
        for sub in os.listdir(algo_dir):
            subdir = os.path.join(algo_dir, sub)
            if not os.path.isdir(subdir):
                continue
            for name in os.listdir(subdir):
                p = os.path.join(subdir, name)
                if os.path.isfile(p):
                    count += 1
                    total += os.path.getsize(p)
    return count, total


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def _load(args):
    from .sync import find_trace_file
    from .trace import load_trace
    tf = find_trace_file(args)
    return tf, load_trace(tf)


def cmd_put(args):
    with open(args.path, "rb") as f:
        ref = put_bytes(f.read(), args.objects_dir)
    print(ref)
    return 0


def cmd_get(args):
    data = get_bytes(args.ref, args.objects_dir)
    if data is None:
        print(f"Error: object not found: {args.ref}", flush=True)
        return 1
    os.write(1, data)
    return 0


def cmd_externalize(args):
    from .trace import save_trace
    tf, trace = _load(args)
    n = externalize(trace, args.objects_dir)
    save_trace(tf, trace)
    print(f"Externalized {n} inline blob(s) into the object store.")
    return 0


def cmd_inline(args):
    from .trace import save_trace
    tf, trace = _load(args)
    n = hydrate_trace(trace, args.objects_dir)
    save_trace(tf, trace)
    print(f"Rehydrated {n} blob(s) inline from the object store.")
    return 0


def cmd_gc(args):
    _, trace = _load(args)
    n = gc(trace, args.objects_dir)
    print(f"Removed {n} unreferenced object(s).")
    return 0


def cmd_stat(_args):
    count, total = store_stats(_args.objects_dir)
    print(f"objects: {count}  size: {total} bytes  dir: {_args.objects_dir or default_objects_dir()}")
    return 0


def register(subparsers):
    objects = subparsers.add_parser("objects", help="Content-addressed object store (content_ref blobs)")
    sub = objects.add_subparsers(dest="objects_command", required=True)

    def _common(p, need_file=False):
        p.add_argument("--objects-dir", default=None,
                       help="Object store dir (default: $PONENS_OBJECTS_DIR or .ponens/objects)")
        if need_file:
            p.add_argument("--file", help="Path to the trace JSON (default: .ponens/<trace>.json)")

    p = sub.add_parser("put", help="Store a file's bytes; print its content_ref")
    p.add_argument("path")
    _common(p)
    p.set_defaults(func=cmd_put)

    p = sub.add_parser("get", help="Write an object's bytes to stdout")
    p.add_argument("ref")
    _common(p)
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("externalize", help="Move inline trace blobs into the store, replacing with refs")
    _common(p, need_file=True)
    p.set_defaults(func=cmd_externalize)

    p = sub.add_parser("inline", help="Rehydrate externalized blobs back inline from the store")
    _common(p, need_file=True)
    p.set_defaults(func=cmd_inline)

    p = sub.add_parser("gc", help="Delete objects not referenced by the trace")
    _common(p, need_file=True)
    p.set_defaults(func=cmd_gc)

    p = sub.add_parser("stat", help="Show object count / total size")
    _common(p)
    p.set_defaults(func=cmd_stat)

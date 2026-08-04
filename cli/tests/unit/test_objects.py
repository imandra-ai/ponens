"""Content-addressed object store (spec §7 content_ref; Gap 2): put/get dedup, the sharded layout,
externalize↔resolve round-trip, referenced-set, and gc."""
from ponens import objects as ob


def test_put_get_roundtrip_and_dedup(tmp_path):
    root = str(tmp_path)
    ref = ob.put_text("let f x = x", root)
    assert ref.startswith("sha256:")
    assert ob.get_text(ref, root) == "let f x = x"
    assert ob.has(ref, root)
    # Identical content → identical ref, stored once (dedup).
    assert ob.put_text("let f x = x", root) == ref
    # Different content → different ref.
    assert ob.put_text("let f x = x + 1", root) != ref


def test_sharded_layout(tmp_path):
    root = str(tmp_path)
    ref = ob.put_text("hello", root)
    p = ob.object_path(ref, root)
    digest = ref.split(":", 1)[1]
    # <root>/sha256/<ab>/<rest>
    assert p.endswith(f"sha256/{digest[:2]}/{digest[2:]}")
    import os
    assert os.path.exists(p)


def test_get_missing_is_none(tmp_path):
    assert ob.get_text("sha256:" + "0" * 64, str(tmp_path)) is None
    assert not ob.has("sha256:" + "0" * 64, str(tmp_path))


def _trace_with_inline():
    return {
        "trace_id": "t1",
        "artifacts": [
            {"artifact_id": "m1", "artifact_type": "IMLModel",
             "payload": {"src_code": "def f(x): return x", "formal_code": "let f x = x", "symbols": ["f"]}},
            {"artifact_id": "s1", "artifact_type": "SourceCode", "payload": {}},
        ],
    }


def test_externalize_then_resolve_roundtrip(tmp_path):
    root = str(tmp_path)
    trace = _trace_with_inline()
    n = ob.externalize(trace, root)
    assert n == 2  # src_code + formal_code
    payload = trace["artifacts"][0]["payload"]
    # Inline dropped, refs added.
    assert "src_code" not in payload and "formal_code" not in payload
    assert ob.is_ref(payload["src_code_ref"]) and ob.is_ref(payload["formal_code_ref"])
    # Resolve brings the content back.
    resolved = ob.resolve_payload(payload, root)
    assert resolved["src_code"] == "def f(x): return x"
    assert resolved["formal_code"] == "let f x = x"


def test_referenced_refs_covers_common_and_payload(tmp_path):
    trace = _trace_with_inline()
    ob.externalize(trace, str(tmp_path))
    trace["artifacts"][1]["content_ref"] = "sha256:" + "a" * 64  # artifact_common ref too
    refs = ob.referenced_refs(trace)
    assert "sha256:" + "a" * 64 in refs
    assert len([r for r in refs if ob.is_ref(r)]) == 3  # 2 payload refs + 1 common ref


def test_externalize_inline_roundtrip_including_iml_code(tmp_path):
    root = str(tmp_path)
    trace = {"trace_id": "t", "artifacts": [
        {"artifact_id": "m1", "artifact_type": "IMLModel",
         "payload": {"src_code": "def f(): ...", "iml_code": "let f = ()", "symbols": ["f"]}},
    ]}
    n = ob.externalize(trace, root)
    assert n == 2  # src_code + iml_code (the extension's model field is now covered)
    payload = trace["artifacts"][0]["payload"]
    assert "iml_code" not in payload and ob.is_ref(payload["iml_code_ref"])
    # Rehydrate: refs → inline, and the _ref is dropped (clean round-trip back to a self-contained file).
    m = ob.hydrate_trace(trace, root)
    assert m == 2
    assert payload["iml_code"] == "let f = ()" and "iml_code_ref" not in payload
    assert payload["src_code"] == "def f(): ..." and "src_code_ref" not in payload


def test_hydrate_leaves_missing_objects_as_refs(tmp_path):
    trace = {"trace_id": "t", "artifacts": [
        {"artifact_id": "m1", "artifact_type": "IMLModel",
         "payload": {"iml_code_ref": "sha256:" + "b" * 64}},  # object not in the store
    ]}
    assert ob.hydrate_trace(trace, str(tmp_path)) == 0
    assert trace["artifacts"][0]["payload"]["iml_code_ref"].startswith("sha256:")  # left intact


def test_normalize_resolves_externalized_model(tmp_path, monkeypatch):
    """A bound (externalized) trace still yields inline formalization to policy eval — normalize_trace
    resolves the blob from the store (found via $PONENS_OBJECTS_DIR)."""
    from ponens.trace import normalize_trace
    objdir = tmp_path / "obj"
    monkeypatch.setenv("PONENS_OBJECTS_DIR", str(objdir))
    trace = {
        "trace_id": "t",
        "actions": [{"id": 1, "type": "Formalize", "outputs": ["m1"]}],
        "artifacts": [{"artifact_id": "m1", "artifact_type": "IMLModel",
                       "payload": {"iml_code": "let f x = x", "symbols": ["f"]}}],
    }
    ob.externalize(trace, str(objdir))  # iml_code → iml_code_ref (inline dropped)
    assert "iml_code" not in trace["artifacts"][0]["payload"]
    normalize_trace(trace)
    assert trace["actions"][0]["formalization"]["iml_code"] == "let f x = x"  # resolved for policy eval


def test_gc_prunes_unreferenced(tmp_path):
    root = str(tmp_path)
    keep = ob.put_text("keep me", root)
    ob.put_text("orphan", root)  # not referenced by the trace
    trace = {"trace_id": "t", "artifacts": [
        {"artifact_id": "a", "artifact_type": "X", "payload": {"src_code_ref": keep}},
    ]}
    removed = ob.gc(trace, root)
    assert removed == 1
    assert ob.has(keep, root)          # referenced object survives
    count, _ = ob.store_stats(root)
    assert count == 1

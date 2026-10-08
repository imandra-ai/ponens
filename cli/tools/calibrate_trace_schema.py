"""Calibrate the trace wire schema on real traces: what fails it, and what producers add beyond it.

Every JSON file given (globs allowed) is searched for traces - an object with `trace_id`, `actions`,
`artifacts` and a trace envelope (`spec_version` or `trigger`) - at any depth, so a dump that embeds traces
works as well as a trace file. Traces are deduplicated by `trace_id`.

Reports, grouped by where they occur (array indices collapsed; an artifact by its type):
  - WIRE errors: each is either a schema mistake or a producer's non-conformance;
  - STRICT extras: the fields a producer writes that the spec does not define (tools/strict_schema.py).

    python3 tools/calibrate_trace_schema.py '<glob>' ['<glob>' ...] [--json]
"""

import collections
import glob
import json
import os
import pathlib
import sys

import jsonschema

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from strict_schema import WIRE, strict  # noqa: E402


def traces_in(x):
    if isinstance(x, dict):
        if ("trace_id" in x and isinstance(x.get("actions"), list) and isinstance(x.get("artifacts"), list)
                and ("spec_version" in x or "trigger" in x)):
            yield x
            return
        for v in x.values():
            yield from traces_in(v)
    elif isinstance(x, list):
        for v in x:
            yield from traces_in(v)


def load(patterns):
    seen, out = set(), []
    for pat in patterns:
        for f in sorted(glob.glob(os.path.expanduser(pat), recursive=True)):
            try:
                doc = json.loads(pathlib.Path(f).read_text())
            except (OSError, ValueError):
                continue
            for t in traces_in(doc):
                if t["trace_id"] not in seen:
                    seen.add(t["trace_id"])
                    out.append((f, t))
    return out


def where(trace, path):
    """A path with indices collapsed - and an artifact named by its type, so findings group by kind."""
    parts, node = [], trace
    for p in path:
        if isinstance(p, int):
            if parts and parts[-1] == "artifacts" and isinstance(node, list) and p < len(node) and isinstance(node[p], dict):
                parts[-1] = f"artifacts[{node[p].get('artifact_type', '?')}]"
            else:
                parts[-1] = parts[-1] + "[]" if parts else "[]"
        else:
            parts.append(str(p))
        try:
            node = node[p]
        except (KeyError, IndexError, TypeError):
            node = None
    return ".".join(parts) or "(trace)"


def leaves(err):
    """The errors that say what is wrong: through an `option` (anyOf with null), the non-null branch's."""
    if err.context:
        inner = [e for e in err.context if not (e.validator == "type" and e.validator_value == "null")]
        if inner:
            return [x for e in inner for x in leaves(e)]
    return [err]


def calibrate(patterns):
    traces = load(patterns)
    wire_schema = json.loads(WIRE.read_text())
    wire = jsonschema.Draft202012Validator(wire_schema)
    strict_v = jsonschema.Draft202012Validator(strict(wire_schema))
    errors, extras, failing = collections.Counter(), collections.Counter(), set()
    examples = {}
    for f, t in traces:
        for e in wire.iter_errors(t):
            for leaf in leaves(e):
                key = (where(t, leaf.absolute_path), leaf.message[:160])
                errors[key] += 1
                examples.setdefault(key, t["trace_id"])
                failing.add(t["trace_id"])
        for e in strict_v.iter_errors(t):
            for leaf in leaves(e):
                if leaf.validator == "additionalProperties":
                    extra = set(leaf.instance) - set(leaf.schema.get("properties", {}))
                    for k in extra:
                        extras[f"{where(t, leaf.absolute_path)}.{k}"] += 1
    return {"traces": len(traces), "failing": len(failing),
            "wire_errors": [{"where": w, "message": m, "count": n, "example": examples[(w, m)]} for (w, m), n in errors.most_common()],
            "strict_extras": [{"field": k, "count": n} for k, n in sorted(extras.items(), key=lambda x: (-x[1], x[0]))]}


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    r = calibrate(args)
    if "--json" in sys.argv:
        print(json.dumps(r, indent=1))
        sys.exit(0)
    print(f"{r['traces']} traces, {r['failing']} failing the wire schema, "
          f"{sum(e['count'] for e in r['wire_errors'])} errors in {len(r['wire_errors'])} kinds\n")
    for e in r["wire_errors"]:
        print(f"{e['count']:6}  {e['where']}  |  {e['message']}   (e.g. {e['example']})")
    print(f"\nfields beyond the spec (strict): {len(r['strict_extras'])}")
    for x in r["strict_extras"]:
        print(f"{x['count']:6}  {x['field']}")

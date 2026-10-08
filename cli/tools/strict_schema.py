"""The STRICT variant of the trace wire schema: every object that names its properties forbids others.

An audit tool, not a validity bar. The wire schema allows extra properties - an interchange format must not
reject a producer's additions - so it cannot say what a producer adds beyond the spec. Validating against
this variant lists exactly that: each `additionalProperties` error is one field the spec does not define.

Objects that name no properties (an open payload, `metadata`, `task`) stay open: they are open by design.

    python3 tools/strict_schema.py [schema.json] > strict.json
"""

import copy
import json
import pathlib
import sys

WIRE = pathlib.Path(__file__).resolve().parent.parent / "ponens" / "schema" / "trace.v1_15.json"


def strict(schema):
    out = copy.deepcopy(schema)

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node and "additionalProperties" not in node:
                node["additionalProperties"] = False
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(out)
    return out


if __name__ == "__main__":
    src = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else WIRE
    print(json.dumps(strict(json.loads(src.read_text())), indent=1, ensure_ascii=False))

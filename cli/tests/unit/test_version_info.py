"""`ponens version --json`: what a consumer needs to decide whether this ponens can judge a record."""

import io
import json
import os
import re
from contextlib import redirect_stdout

from ponens.cli import build_parser
from ponens.trace import TRACE_SPEC_VERSION


def test_version_json_reports_the_package_and_the_spec():
    args = build_parser().parse_args(["version", "--json"])
    out = io.StringIO()
    with redirect_stdout(out):
        assert args.func(args) == 0
    info = json.loads(out.getvalue())
    assert info["trace_spec"] == TRACE_SPEC_VERSION
    assert info["version"]


def test_the_declared_spec_is_the_newest_spec_document():
    # The constant must move with the spec: a ponens that reads 1.15 but says 1.14 makes consumers
    # refuse records it could read; one that says 1.15 while reading 1.14 is worse.
    spec_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "spec")
    found = [tuple(int(x) for x in m.groups()) for f in os.listdir(spec_dir)
             if (m := re.fullmatch(r"TRACE_SPEC_v(\d+)_(\d+)\.md", f))]
    assert ".".join(map(str, max(found))) == TRACE_SPEC_VERSION

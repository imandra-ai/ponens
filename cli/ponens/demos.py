"""Bundled sample traces — `ponens demos`.

The repo-root ``examples/`` directory is the single source of truth for the demo set. At package
build time the manifest's samples are copied into ``ponens/demos/`` (see ``cli/Makefile``) so they
ship with the wheel; in an editable/dev checkout they're read straight from ``../../examples/``.
Either way ``ponens demos get`` writes a real, checkable trace to disk so a reader can immediately
run ``ponens trace check`` against it.
"""

import json
import os
import shutil
import sys

from .formatting import heading, table, cyan, gray, green


def _demos_dir():
    """The demo-trace directory: the packaged copy first, else the repo ``examples/`` (dev checkout)."""
    here = os.path.dirname(os.path.abspath(__file__))
    packaged = os.path.join(here, "demos")
    if os.path.isfile(os.path.join(packaged, "manifest.json")):
        return packaged
    repo_examples = os.path.abspath(os.path.join(here, "..", "..", "examples"))
    if os.path.isfile(os.path.join(repo_examples, "manifest.json")):
        return repo_examples
    return packaged  # may not exist; callers surface a friendly error


def _load_manifest():
    d = _demos_dir()
    try:
        with open(os.path.join(d, "manifest.json")) as f:
            return d, json.load(f).get("samples", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return d, []


def _resolve(samples, ref):
    """Match a demo by file name (with or without .json) or by display name (case-insensitive)."""
    ref_l = ref.lower()
    for s in samples:
        stem = s["file"][:-5] if s["file"].endswith(".json") else s["file"]
        if ref_l in (s["file"].lower(), stem.lower(), s.get("name", "").lower()):
            return s
    return None


def _clip(text, n=54):
    return text if len(text) <= n else text[: n - 1] + "…"


def cmd_demos_list(args):
    d, samples = _load_manifest()
    if not samples:
        print(gray("No bundled demos found."))
        return 0
    if getattr(args, "json", False):
        print(json.dumps(samples, indent=2, ensure_ascii=False))
        return 0
    heading(f"Demo traces ({len(samples)})")
    table(samples, [
        {"label": "Name", "get": lambda s: s.get("name", ""), "color": cyan},
        {"label": "File", "get": lambda s: s["file"]},
        {"label": "Spec", "get": lambda s: s.get("spec", "")},
        {"label": "Summary", "get": lambda s: _clip(s.get("summary", ""))},
    ])
    first = samples[0]["file"]
    print(gray(f"\n  Get one:  ponens demos get {first} -o trace.json"))
    print(gray(f"  Check it: ponens trace check trace.json --json"))
    return 0


def cmd_demos_get(args):
    d, samples = _load_manifest()
    s = _resolve(samples, args.name)
    if not s:
        print(f"unknown demo '{args.name}' — run `ponens demos list`.", file=sys.stderr)
        return 1
    src = os.path.join(d, s["file"])
    if not os.path.isfile(src):
        print(f"demo file missing: {src}", file=sys.stderr)
        return 1
    if args.output in (None, "-"):
        with open(src) as f:
            sys.stdout.write(f.read())
        return 0
    shutil.copy(src, args.output)
    print(green(f"wrote {args.output}") + gray(f"  ({s.get('name', '')})"))
    return 0


def register(subparsers):
    demos = subparsers.add_parser("demos", help="Bundled sample traces you can check locally")
    sub = demos.add_subparsers(dest="demos_command", required=True)

    p = sub.add_parser("list", aliases=["ls"], help="List the bundled demo traces")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.set_defaults(func=cmd_demos_list)

    p = sub.add_parser("get", help="Write a demo trace to a file (default: stdout)")
    p.add_argument("name", help="Demo file or name (see `ponens demos list`)")
    p.add_argument("-o", "--output", default=None, help="Output path; '-' or omitted = stdout")
    p.set_defaults(func=cmd_demos_get)

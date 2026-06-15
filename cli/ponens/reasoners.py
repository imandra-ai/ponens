"""`ponens reasoners` — search and inspect the reasoner registry.

A *reasoner* is an automated-reasoning tool (CodeLogician, ImandraX, a model checker,
an SMT solver) that produces a trace's verification artifacts and that policies can
*require* (the policy `reasoner` field). Parallel to `ponens policies`, but a single
registry (gallery/reasoners), not the multi-source policy machinery.

Source: PONENS_REASONER_URL (a https gallery or a local dir / file:// path);
defaults to the public gallery. Remote catalogs are cached under the registry cache.
"""
import json
import os

from .formatting import heading, table, gray, cyan, blue, magenta, underline
from .registry import _base_cache, _fetch

DEFAULT_REASONER_URL = "https://ponens.dev/gallery/reasoners"


def _reasoner_url():
    return os.environ.get("PONENS_REASONER_URL", DEFAULT_REASONER_URL).rstrip("/")


def _local_dir(url):
    if url.startswith("file://"):
        url = url[len("file://"):]
    return url if os.path.isdir(url) else None


def _cache_path():
    d = os.path.join(_base_cache(), "_reasoners")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "_catalog.json")


def load_catalog(refresh=False):
    url = _reasoner_url()
    local = _local_dir(url)
    if local:
        with open(os.path.join(local, "_catalog.json")) as f:
            return json.load(f)
    cache = _cache_path()
    if not refresh and os.path.exists(cache):
        with open(cache) as f:
            return json.load(f)
    text = _fetch(url + "/_catalog.json")
    with open(cache, "w") as f:
        f.write(text)
    return json.loads(text)


def load_reasoner(rid):
    url = _reasoner_url()
    local = _local_dir(url)
    if local:
        with open(os.path.join(local, f"{rid}.json")) as f:
            return json.load(f)
    return json.loads(_fetch(f"{url}/{rid}.json"))


def _matches(e, query, args):
    if getattr(args, "kind", None) and e.get("kind") != args.kind:
        return False
    if getattr(args, "status", None) and e.get("status") != args.status:
        return False
    if not query:
        return True
    hay = " ".join([str(e.get(k, "")) for k in ("id", "name", "description", "vendor", "kind")]
                   + (e.get("tags") or []) + (e.get("produces") or [])).lower()
    return query.lower() in hay


def cmd_reasoners_search(args):
    try:
        cat = load_catalog(refresh=getattr(args, "refresh", False))
    except Exception as ex:
        print(gray(f"  could not load the reasoner registry: {ex}"))
        return 1
    rows = [e for e in cat.get("reasoners", []) if _matches(e, getattr(args, "query", "") or "", args)]
    if getattr(args, "json", False):
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0
    heading(f"Reasoners ({len(rows)})")
    if not rows:
        print(gray("  no matches — broaden the query"))
        return 0
    table(rows, [
        {"label": "ID", "get": lambda e: e["id"], "color": cyan},
        {"label": "Name", "get": lambda e: e.get("name", "")},
        {"label": "Kind", "get": lambda e: (e.get("kind") or "").replace("_", " "), "color": magenta},
        {"label": "Vendor", "get": lambda e: e.get("vendor", "")},
        {"label": "Status", "get": lambda e: e.get("status", ""), "color": blue},
    ])
    print(gray("\n  ponens reasoners show <id>     # a reasoner's full definition"))
    return 0


def cmd_reasoners_show(args):
    try:
        r = load_reasoner(args.reasoner_id)
    except Exception as ex:
        print(gray(f"  could not load reasoner '{args.reasoner_id}': {ex}"))
        return 1
    if getattr(args, "json", False):
        print(json.dumps(r, indent=2, ensure_ascii=False))
        return 0
    heading(r.get("name", args.reasoner_id))
    print(f"  {gray('id')}            {cyan(r['id'])}")
    print(f"  {gray('kind')}          {magenta((r.get('kind') or '').replace('_', ' '))}")
    if r.get("vendor"):
        print(f"  {gray('vendor')}        {r['vendor']}")
    print(f"  {gray('status')}        {blue(r.get('status', ''))}")
    if r.get("description"):
        print(f"\n  {r['description']}")
    if r.get("produces"):
        print(f"\n  {gray('produces')}      {', '.join(r['produces'])}")
    if r.get("capabilities"):
        print(f"  {gray('capabilities')}  {', '.join(r['capabilities'])}")
    if r.get("domains"):
        print(f"  {gray('domains')}       {', '.join(r['domains'])}")
    if r.get("url"):
        print(f"\n  {underline(r['url'])}")
    return 0


def cmd_reasoners_list(args):
    args.query = ""
    return cmd_reasoners_search(args)


def register(subparsers):
    rp = subparsers.add_parser("reasoners",
                              help="Search the reasoner registry (tools policies can require)")
    sub = rp.add_subparsers(dest="reasoners_command", required=True)

    p = sub.add_parser("search", help="Search reasoners")
    p.add_argument("query", nargs="?", default="")
    p.add_argument("--kind", help="Filter by kind (formal_verification, smt, model_checking, …)")
    p.add_argument("--status", help="Filter by status (available, community, …)")
    p.add_argument("--refresh", action="store_true", help="Force-refresh the cached catalog")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_reasoners_search)

    p = sub.add_parser("list", aliases=["ls"], help="List all reasoners")
    p.add_argument("--kind")
    p.add_argument("--status")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_reasoners_list)

    p = sub.add_parser("show", help="Show a reasoner's full definition")
    p.add_argument("reasoner_id")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_reasoners_show)

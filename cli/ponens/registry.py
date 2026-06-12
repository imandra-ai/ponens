"""Policy registry client — search and load community policies from the public
ponens policy gallery (https://ponens.dev).

The gallery publishes a denormalized, content-hashed ``_catalog.json`` to a static
URL. ``registry update`` caches that catalog locally; ``policies search`` filters it
offline; ``policies show`` / ``policies add`` fetch individual policy files and (for
``add``) materialize them into a local trace so ``ponens trace check`` can run them.
"""

import json
import os
import sys
import urllib.request
import urllib.error

from .formatting import (
    bold, gray, red, green, yellow, cyan, magenta, underline, table, heading,
)

DEFAULT_REGISTRY = "https://ponens.dev/gallery/policies"


def registry_url() -> str:
    return os.environ.get("PONENS_REGISTRY_URL", DEFAULT_REGISTRY).rstrip("/")


def cache_dir() -> str:
    base = os.environ.get(
        "PONENS_REGISTRY_CACHE",
        os.path.join(os.path.expanduser("~"), ".ponens", "registry"),
    )
    os.makedirs(os.path.join(base, "policies"), exist_ok=True)
    return base


def catalog_path() -> str:
    return os.path.join(cache_dir(), "_catalog.json")


# ----------------------------------------------------------------------------
# Fetching
# ----------------------------------------------------------------------------

def _fetch(path: str) -> str:
    url = f"{registry_url()}/{path}"
    try:
        with urllib.request.urlopen(url) as resp:
            return resp.read().decode()
    except urllib.error.URLError as e:
        raise RuntimeError(f"could not fetch {url}: {e}") from None


def load_catalog() -> dict:
    path = catalog_path()
    if not os.path.exists(path):
        print(red("No cached policy catalog."), file=sys.stderr)
        print(gray("Run: ponens registry update"), file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def fetch_policy(policy_id: str) -> dict:
    """Return the full policy JSON, preferring the local cache, then the network."""
    cached = os.path.join(cache_dir(), "policies", f"{policy_id}.json")
    if os.path.exists(cached):
        with open(cached) as f:
            return json.load(f)
    text = _fetch(f"{policy_id}.json")
    policy = json.loads(text)
    with open(cached, "w") as f:
        f.write(text)
    return policy


# ----------------------------------------------------------------------------
# Schema adapter: gallery policy -> trace-embedded policy (compiler shape)
# ----------------------------------------------------------------------------

def gallery_to_trace_policy(gp: dict, entry: dict | None = None) -> dict:
    """Adapt a gallery policy into the shape the local policy checker expects.

    The snake_case ``id`` becomes ``name`` (so structural policies match the
    compiler's registry), and ``scope`` / ``kind`` are defaulted — the gallery
    schema omits them but ``check_policy`` requires them.
    """
    formula = gp.get("formula") or gp.get("ltl_formula") or ""
    policy = {
        "policy_id": gp["id"],
        "name": gp["id"],
        "display_name": gp.get("name"),
        "description": gp.get("description", ""),
        "severity": gp.get("severity", "warning"),
        "scope": gp.get("scope", "trace"),
        "kind": gp.get("kind", "trace_invariant"),
        "formula": formula,
    }
    if gp.get("applies_when"):
        policy["applies_when"] = gp["applies_when"]
    source = {"registry": "reasoning-policies", "id": gp["id"],
              "version": gp.get("version", "1.0.0")}
    if entry and entry.get("hash"):
        source["hash"] = entry["hash"]
    policy["source"] = source
    return policy


# ----------------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------------

def cmd_registry_update(_args):
    text = _fetch("_catalog.json")
    catalog = json.loads(text)
    with open(catalog_path(), "w") as f:
        f.write(text)
    n = catalog.get("policy_count", len(catalog.get("policies", [])))
    print(f"{green('Updated')} policy catalog: {bold(str(n))} policies "
          f"from {underline(registry_url())}")
    domains = catalog.get("domains", {})
    if domains:
        print(gray("  domains: " + ", ".join(sorted(domains.keys()))))
    print(gray("  cache: " + catalog_path()))


def _matches(entry: dict, query: str, args) -> bool:
    if args.category and entry.get("category") != args.category:
        return False
    if args.severity and entry.get("severity") != args.severity:
        return False
    if args.domain and entry.get("domain") != args.domain:
        return False
    if args.tag and args.tag not in (entry.get("tags") or []):
        return False
    if query:
        hay = " ".join([
            entry.get("id", ""), entry.get("name", ""),
            entry.get("description", ""), entry.get("domain", ""),
            " ".join(entry.get("tags") or []),
        ]).lower()
        if query.lower() not in hay:
            return False
    return True


def cmd_policies_search(args):
    catalog = load_catalog()
    query = args.query or ""
    results = [e for e in catalog.get("policies", []) if _matches(e, query, args)]

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    heading(f"Policies ({len(results)} of {catalog.get('policy_count', '?')})")
    if not results:
        print(gray("  no matches — try `ponens registry update` or broaden the query"))
        return

    sev_color = {"error": red, "warning": yellow, "info": gray}

    def compat(e):
        rc = e.get("reference_compiler")
        return green("ok") if rc == "ok" else yellow(rc or "?")

    table(results, [
        {"label": "ID", "get": lambda e: e["id"], "color": cyan},
        {"label": "Name", "get": lambda e: e.get("name", "")},
        {"label": "Domain", "get": lambda e: e.get("domain", ""), "color": magenta},
        {"label": "Severity", "get": lambda e: sev_color.get(e.get("severity"), gray)(e.get("severity", ""))},
        {"label": "Compiler", "get": compat},
    ])
    print(gray("\n  ponens policies show <id>     # full policy"))
    print(gray("  ponens policies add <id> --into <trace.json>"))


def cmd_policies_show(args):
    catalog = load_catalog()
    entry = next((e for e in catalog.get("policies", []) if e["id"] == args.policy_id), None)
    policy = fetch_policy(args.policy_id)

    if args.json:
        print(json.dumps(policy, indent=2, ensure_ascii=False))
        return

    heading(policy.get("name", args.policy_id))
    print(f"  {gray('id')}          {cyan(policy['id'])}")
    print(f"  {gray('category')}    {policy.get('category', '')}")
    print(f"  {gray('domain')}      {magenta(policy.get('domain', ''))}")
    print(f"  {gray('severity')}    {policy.get('severity', '')}")
    print(f"  {gray('level')}       {policy.get('language_level', '')}")
    if policy.get("tags"):
        print(f"  {gray('tags')}        {', '.join(policy['tags'])}")
    if entry:
        rc = entry.get("reference_compiler")
        rc_s = green("ok") if rc == "ok" else yellow(rc or "?")
        print(f"  {gray('compiler')}    {rc_s}    {gray(entry.get('hash', ''))}")
    print()
    print(f"  {bold('Formula')}")
    print(f"    {policy.get('formula', '')}")
    print()
    print(f"  {bold('Description')}")
    print(f"    {policy.get('description', '')}")
    if policy.get("rationale"):
        print(f"\n  {bold('Rationale')}\n    {policy['rationale']}")
    ex = policy.get("examples") or {}
    if ex:
        print(f"\n  {bold('Examples')}")
        if ex.get("passes"):
            print(f"    {green('passes')}  {ex['passes']}")
        if ex.get("fails"):
            print(f"    {red('fails')}   {ex['fails']}")
    print()


def cmd_policies_add(args):
    path = args.into
    if not os.path.exists(path):
        print(red(f"Trace file not found: {path}"), file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        trace = json.load(f)

    catalog = load_catalog()
    entry = next((e for e in catalog.get("policies", []) if e["id"] == args.policy_id), None)
    gp = fetch_policy(args.policy_id)
    policy = gallery_to_trace_policy(gp, entry)

    policies = trace.setdefault("policies", [])
    if any(p.get("policy_id") == policy["policy_id"] for p in policies):
        print(yellow(f"Policy '{policy['policy_id']}' is already attached to this trace."))
        return
    policies.append(policy)

    with open(path, "w") as f:
        json.dump(trace, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"{green('Added')} policy {cyan(policy['policy_id'])} to {path}")
    if entry and entry.get("reference_compiler") == "unsupported":
        print(yellow("  note: this policy needs a newer reference compiler; "
                     "`trace check` may not evaluate it."))
    print(gray(f"  run: ponens trace check {path}"))


# ----------------------------------------------------------------------------
# Argparse registration
# ----------------------------------------------------------------------------

def register(subparsers):
    """Register the 'registry' and 'policies' command groups."""
    reg = subparsers.add_parser("registry", help="Manage the policy registry cache")
    reg_sub = reg.add_subparsers(dest="registry_command", required=True)
    p = reg_sub.add_parser("update", help="Fetch/refresh the policy catalog from the public registry")
    p.set_defaults(func=cmd_registry_update)

    pol = subparsers.add_parser("policies", help="Search and load community policies from the registry")
    pol_sub = pol.add_subparsers(dest="policies_command", required=True)

    p = pol_sub.add_parser("search", help="Search the policy catalog")
    p.add_argument("query", nargs="?", default="", help="Free-text query (id, name, description, tags)")
    p.add_argument("--category", help="Filter by category")
    p.add_argument("--severity", choices=["info", "warning", "error"], help="Filter by severity")
    p.add_argument("--domain", help="Filter by domain")
    p.add_argument("--tag", help="Filter by tag")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.set_defaults(func=cmd_policies_search)

    p = pol_sub.add_parser("show", help="Show a policy's full definition")
    p.add_argument("policy_id")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.set_defaults(func=cmd_policies_show)

    p = pol_sub.add_parser("add", help="Add a registry policy into a local trace file")
    p.add_argument("policy_id")
    p.add_argument("--into", required=True, help="Path to the trace JSON file")
    p.set_defaults(func=cmd_policies_add)

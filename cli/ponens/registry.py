"""Policy registry client — resolve, search, and load policies from one or more
**sources**: the public gallery, a corporate hub (future), or a local directory
of your own policies.

Sources are declared in ``sources.toml`` (user-global ``~/.ponens/sources.toml`` and
per-project ``.ponens/sources.toml``); with none configured, a single ``community``
gallery source is used. Policies are referenced by id, optionally qualified by source
(``community/tests_before_commit``); unqualified ids resolve by source order and error
on ambiguity. Each gallery source keeps its own hash-verified cache.
"""

import glob
import hashlib
import json
import os
import sys
import tomllib
import urllib.request
import urllib.error

from .formatting import (
    bold, gray, red, green, yellow, blue, cyan, magenta, underline, table, heading,
)

DEFAULT_GALLERY_URL = "https://ponens.dev/gallery/policies"


def _err(msg):
    print(red(f"Error: {msg}"), file=sys.stderr)
    sys.exit(1)


# ----------------------------------------------------------------------------
# Sources configuration (layered: user then project)
# ----------------------------------------------------------------------------

def _user_sources_path():
    return os.path.join(os.path.expanduser("~"), ".ponens", "sources.toml")


def _project_sources_path():
    """Nearest .ponens/sources.toml walking up from the cwd, or None."""
    d = os.path.abspath(os.getcwd())
    while True:
        c = os.path.join(d, ".ponens", "sources.toml")
        if os.path.exists(c):
            return c
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def _read_sources_file(path):
    if not path or not os.path.exists(path):
        return []
    with open(path, "rb") as f:
        return tomllib.load(f).get("source", [])


def load_sources():
    """Return the ordered list of configured sources (user, then project additions).

    With no config, a single built-in ``community`` gallery source is used (its URL
    honours the ``PONENS_REGISTRY_URL`` env override for back-compat)."""
    merged, by_name = [], {}
    for s in _read_sources_file(_user_sources_path()) + _read_sources_file(_project_sources_path()):
        name = s.get("name")
        if not name:
            continue
        if name in by_name:
            by_name[name].update(s)
        else:
            by_name[name] = dict(s)
            merged.append(by_name[name])

    if not merged:
        merged = [{"name": "community", "type": "gallery",
                   "url": os.environ.get("PONENS_REGISTRY_URL", DEFAULT_GALLERY_URL)}]

    for s in merged:
        if s.get("type") == "gallery" and s.get("url"):
            s["url"] = s["url"].rstrip("/")
    return merged


def get_source(name):
    for s in load_sources():
        if s.get("name") == name:
            return s
    _err(f"unknown source '{name}' — see `ponens sources list` or add it to .ponens/sources.toml")


def default_source():
    return load_sources()[0]


# ----------------------------------------------------------------------------
# Cache + fetch
# ----------------------------------------------------------------------------

def _base_cache():
    return os.environ.get("PONENS_REGISTRY_CACHE",
                          os.path.join(os.path.expanduser("~"), ".ponens", "registry"))


def _gallery_cache_dir(name):
    d = os.path.join(_base_cache(), name)
    os.makedirs(os.path.join(d, "policies"), exist_ok=True)
    return d


def _fetch(url):
    try:
        with urllib.request.urlopen(url) as resp:
            return resp.read().decode()
    except urllib.error.URLError as e:
        raise RuntimeError(f"could not fetch {url}: {e}") from None


def _policy_hash(policy: dict) -> str:
    """Content hash of a policy, matching the gallery catalog builder
    (scripts/build_index.py): sha256 over canonical JSON, excluding 'downloads'."""
    stable = {k: v for k, v in policy.items() if k != "downloads"}
    canon = json.dumps(stable, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _entry_from_policy(p):
    return {
        "id": p.get("id"), "name": p.get("name"), "category": p.get("category"),
        "severity": p.get("severity"), "domain": p.get("domain"),
        "tags": sorted(p.get("tags", [])), "language_level": p.get("language_level"),
        "description": p.get("description"), "version": p.get("version", "1.0.0"),
        "hash": _policy_hash(p),
    }


def _local_catalog(source):
    d = os.path.abspath(source.get("path", ""))
    if not os.path.isdir(d):
        raise FileNotFoundError(f"local source '{source['name']}' path not found: {d}")
    entries = []
    for f in sorted(glob.glob(os.path.join(d, "*.json"))):
        if os.path.basename(f).startswith("_"):
            continue
        with open(f) as fh:
            entries.append(_entry_from_policy(json.load(fh)))
    return {"policies": entries, "policy_count": len(entries)}


def _gallery_catalog(source):
    path = os.path.join(_gallery_cache_dir(source["name"]), "_catalog.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"source '{source['name']}' not cached")
    with open(path) as f:
        return json.load(f)


def source_catalog(source):
    """The catalog for a source: scanned live for ``local``, cached for ``gallery``."""
    if source.get("type") == "local":
        return _local_catalog(source)
    return _gallery_catalog(source)


def fetch_policy_from(source, policy_id, expected_hash=None, refresh=False):
    """Return the full policy JSON for ``policy_id`` from ``source``.

    Local sources read the file directly. Gallery sources are cache-first and
    hash-verified: a cached copy is reused only if its hash matches ``expected_hash``,
    otherwise it is re-fetched (self-healing). ``refresh=True`` forces a re-fetch."""
    if source.get("type") == "local":
        f = os.path.join(os.path.abspath(source["path"]), f"{policy_id}.json")
        if not os.path.exists(f):
            _err(f"policy '{policy_id}' not found in local source '{source['name']}'")
        with open(f) as fh:
            return json.load(fh)

    cached = os.path.join(_gallery_cache_dir(source["name"]), "policies", f"{policy_id}.json")
    if not refresh and os.path.exists(cached):
        with open(cached) as fh:
            policy = json.load(fh)
        if expected_hash is None or _policy_hash(policy) == expected_hash:
            return policy

    text = _fetch(f"{source['url']}/{policy_id}.json")
    policy = json.loads(text)
    with open(cached, "w") as fh:
        fh.write(text)
    return policy


# ----------------------------------------------------------------------------
# Reference resolution (qualified `source/id` or bare `id`)
# ----------------------------------------------------------------------------

def split_ref(ref):
    if "/" in ref:
        name, pid = ref.split("/", 1)
        return name, pid
    return None, ref


def resolve(ref):
    """Resolve a policy reference to ``(source, catalog_entry)``."""
    name, pid = split_ref(ref)
    if name:
        src = get_source(name)
        try:
            cat = source_catalog(src)
        except FileNotFoundError:
            _err(f"source '{name}' not available — run: ponens registry update --source {name}")
        entry = next((e for e in cat["policies"] if e["id"] == pid), None)
        if not entry:
            _err(f"policy '{pid}' not found in source '{name}'")
        return src, entry

    hits = []
    for s in load_sources():
        try:
            cat = source_catalog(s)
        except (FileNotFoundError, RuntimeError):
            continue  # uncached/unavailable source — skip during unqualified search
        entry = next((e for e in cat["policies"] if e["id"] == pid), None)
        if entry:
            hits.append((s, entry))
    if not hits:
        _err(f"policy '{pid}' not found in any configured source")
    if len(hits) > 1:
        opts = ", ".join(f"{s['name']}/{pid}" for s, _ in hits)
        _err(f"'{pid}' is ambiguous across sources — qualify it: {opts}")
    return hits[0]


# ----------------------------------------------------------------------------
# Schema adapter: gallery policy -> trace-embedded policy (compiler shape)
# ----------------------------------------------------------------------------

def gallery_to_trace_policy(gp: dict, source_name: str | None = None, entry: dict | None = None) -> dict:
    """Adapt a gallery policy into the shape the local policy checker expects,
    stamping its provenance (which source it came from) for audit."""
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
    source = {"source": source_name or "community", "id": gp["id"],
              "version": gp.get("version", "1.0.0")}
    if entry and entry.get("hash"):
        source["hash"] = entry["hash"]
    policy["source"] = source
    return policy


# ----------------------------------------------------------------------------
# Search filter
# ----------------------------------------------------------------------------

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
            entry.get("description", "") or "", entry.get("domain", "") or "",
            " ".join(entry.get("tags") or []),
        ]).lower()
        if query.lower() not in hay:
            return False
    return True


# ----------------------------------------------------------------------------
# Commands — sources
# ----------------------------------------------------------------------------

def cmd_sources_list(_args):
    heading("Policy sources")
    for s in load_sources():
        t = s.get("type", "?")
        loc = s.get("url") if t == "gallery" else s.get("path", "")
        if t == "gallery":
            cached = os.path.exists(os.path.join(_base_cache(), s["name"], "_catalog.json"))
            state = green("cached") if cached else gray("not cached")
        elif t == "local":
            state = green("live") if os.path.isdir(os.path.abspath(loc)) else red("missing")
        else:
            state = gray(t)
        print(f"  {bold(s['name']):24} {gray(t.ljust(8))} {loc}  {state}")
    print(gray("\n  config: ~/.ponens/sources.toml and ./.ponens/sources.toml"))


def cmd_sources_add(args):
    cfg = os.path.join(os.getcwd(), ".ponens", "sources.toml")
    os.makedirs(os.path.dirname(cfg), exist_ok=True)
    lines = ["", "[[source]]", f'name = "{args.name}"', f'type = "{args.type}"']
    if args.type == "gallery":
        if not args.url:
            _err("--url is required for a gallery source")
        lines.append(f'url = "{args.url.rstrip("/")}"')
    else:  # local
        if not args.path:
            _err("--path is required for a local source")
        lines.append(f'path = "{args.path}"')
    with open(cfg, "a") as f:
        f.write("\n".join(lines) + "\n")
    print(f"{green('Added')} source {cyan(args.name)} ({args.type}) → {cfg}")


# ----------------------------------------------------------------------------
# Commands — registry update
# ----------------------------------------------------------------------------

def cmd_registry_update(args):
    target = getattr(args, "source", None)
    sources = [get_source(target)] if target else load_sources()
    updated = 0
    for s in sources:
        if s.get("type") != "gallery":
            if target:
                print(gray(f"source '{s['name']}' is type '{s.get('type')}' — read live, nothing to cache"))
            continue
        text = _fetch(f"{s['url']}/_catalog.json")
        with open(os.path.join(_gallery_cache_dir(s["name"]), "_catalog.json"), "w") as f:
            f.write(text)
        cat = json.loads(text)
        n = cat.get("policy_count", len(cat.get("policies", [])))
        print(f"{green('Updated')} {cyan(s['name'])}: {bold(str(n))} policies from {underline(s['url'])}")
        updated += 1
    if not updated and not target:
        print(gray("No gallery sources to update."))


# ----------------------------------------------------------------------------
# Commands — policies
# ----------------------------------------------------------------------------

def cmd_policies_search(args):
    only = getattr(args, "source", None)
    sources = [get_source(only)] if only else load_sources()
    query = args.query or ""
    rows = []
    for s in sources:
        try:
            cat = source_catalog(s)
        except (FileNotFoundError, RuntimeError):
            if only:
                _err(f"source '{s['name']}' not available — run: ponens registry update --source {s['name']}")
            continue
        for e in cat.get("policies", []):
            if _matches(e, query, args):
                rows.append({**e, "_source": s["name"]})

    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return

    heading(f"Policies ({len(rows)})")
    if not rows:
        print(gray("  no matches — try `ponens registry update` or broaden the query"))
        return

    sev_color = {"error": red, "warning": yellow, "info": gray}
    table(rows, [
        {"label": "Source", "get": lambda e: e["_source"], "color": blue},
        {"label": "ID", "get": lambda e: e["id"], "color": cyan},
        {"label": "Name", "get": lambda e: e.get("name", "")},
        {"label": "Domain", "get": lambda e: e.get("domain", ""), "color": magenta},
        {"label": "Severity", "get": lambda e: sev_color.get(e.get("severity"), gray)(e.get("severity", ""))},
    ])
    print(gray("\n  ponens policies show <source/id>     # full policy"))
    print(gray("  ponens policies add <source/id> --into <trace.json>"))


def cmd_policies_show(args):
    source, entry = resolve(args.policy_id)
    policy = fetch_policy_from(source, entry["id"], entry.get("hash"),
                               refresh=getattr(args, "refresh", False))

    if args.json:
        print(json.dumps(policy, indent=2, ensure_ascii=False))
        return

    heading(policy.get("name", entry["id"]))
    print(f"  {gray('id')}          {cyan(policy['id'])}")
    print(f"  {gray('source')}      {blue(source['name'])}")
    print(f"  {gray('category')}    {policy.get('category', '')}")
    print(f"  {gray('domain')}      {magenta(policy.get('domain', ''))}")
    print(f"  {gray('severity')}    {policy.get('severity', '')}")
    print(f"  {gray('level')}       {policy.get('language_level', '')}")
    if policy.get("tags"):
        print(f"  {gray('tags')}        {', '.join(policy['tags'])}")
    print()
    print(f"  {bold('Formula')}\n    {policy.get('formula', '')}")
    print()
    print(f"  {bold('Description')}\n    {policy.get('description', '')}")
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
        _err(f"trace file not found: {path}")
    with open(path) as f:
        trace = json.load(f)

    source, entry = resolve(args.policy_id)
    gp = fetch_policy_from(source, entry["id"], entry.get("hash"),
                           refresh=getattr(args, "refresh", False))
    policy = gallery_to_trace_policy(gp, source["name"], entry)

    policies = trace.setdefault("policies", [])
    if any(p.get("policy_id") == policy["policy_id"] for p in policies):
        print(yellow(f"Policy '{policy['policy_id']}' is already attached to this trace."))
        return
    policies.append(policy)

    with open(path, "w") as f:
        json.dump(trace, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"{green('Added')} policy {cyan(policy['policy_id'])} from {blue(source['name'])} to {path}")
    if entry.get("reference_compiler") == "unsupported":
        print(yellow("  note: this policy needs a newer reference compiler; "
                     "`trace check` may not evaluate it."))
    print(gray(f"  run: ponens trace check {path}"))


# ----------------------------------------------------------------------------
# Commands — unified search (policies, packs, organizations)
# ----------------------------------------------------------------------------

def _q_in(query, *vals):
    if not query:
        return True
    hay = " ".join(str(v or "") for v in vals).lower()
    return query.lower() in hay


def _packs_of(cat):
    """A source's packs: from the catalog if present (gallery), else derived
    from policy `pack` membership (local sources carry no pack manifests)."""
    packs = cat.get("packs")
    if packs is not None:
        return packs
    counts = {}
    for e in cat.get("policies", []):
        if e.get("pack"):
            counts[e["pack"]] = counts.get(e["pack"], 0) + 1
    return [{"id": k, "name": k, "policy_count": v} for k, v in sorted(counts.items())]


def cmd_search(args):
    """Search policies, packs, and organizations across configured sources."""
    only = getattr(args, "source", None)
    sources = [get_source(only)] if only else load_sources()
    q = args.query or ""
    want = getattr(args, "type", None)  # None | policy | pack | org
    orgs, packs, pols = [], [], []
    for s in sources:
        try:
            cat = source_catalog(s)
        except (FileNotFoundError, RuntimeError):
            if only:
                _err(f"source '{s['name']}' not available — run: ponens registry update --source {s['name']}")
            continue
        sn = s["name"]
        if want in (None, "org"):
            for o in cat.get("organizations", []):
                if _q_in(q, o.get("id"), o.get("name"), o.get("full_name"), o.get("description")):
                    orgs.append({**o, "_source": sn})
        if want in (None, "pack"):
            for p in _packs_of(cat):
                if _q_in(q, p.get("id"), p.get("name"), p.get("summary"),
                         p.get("description"), p.get("org"), p.get("domain")):
                    packs.append({**p, "_source": sn})
        if want in (None, "policy"):
            for e in cat.get("policies", []):
                if _matches(e, q, args):
                    pols.append({**e, "_source": sn})

    if args.json:
        print(json.dumps({"organizations": orgs, "packs": packs, "policies": pols},
                         indent=2, ensure_ascii=False))
        return

    def _count_pack(pack):
        return pack.get("policy_count", sum(1 for e in pols if e.get("pack") == pack["id"]))

    if want in (None, "org"):
        heading(f"Organizations ({len(orgs)})")
        if orgs:
            table(orgs, [
                {"label": "Source", "get": lambda o: o["_source"], "color": blue},
                {"label": "ID", "get": lambda o: o["id"], "color": cyan},
                {"label": "Name", "get": lambda o: o.get("full_name") or o.get("name", "")},
                {"label": "Packs", "get": lambda o: str(len(o.get("packs") or []))},
            ])
        else:
            print(gray("  none"))
    if want in (None, "pack"):
        heading(f"Packs ({len(packs)})")
        if packs:
            table(packs, [
                {"label": "Source", "get": lambda p: p["_source"], "color": blue},
                {"label": "ID", "get": lambda p: p["id"], "color": cyan},
                {"label": "Name", "get": lambda p: p.get("name", "")},
                {"label": "Org", "get": lambda p: p.get("org", ""), "color": magenta},
                {"label": "Policies", "get": lambda p: str(_count_pack(p))},
            ])
        else:
            print(gray("  none"))
    if want in (None, "policy"):
        sev_color = {"error": red, "warning": yellow, "info": gray}
        heading(f"Policies ({len(pols)})")
        if pols:
            table(pols, [
                {"label": "Source", "get": lambda e: e["_source"], "color": blue},
                {"label": "ID", "get": lambda e: e["id"], "color": cyan},
                {"label": "Name", "get": lambda e: e.get("name", "")},
                {"label": "Pack", "get": lambda e: e.get("pack", ""), "color": magenta},
                {"label": "Severity", "get": lambda e: sev_color.get(e.get("severity"), gray)(e.get("severity", ""))},
            ])
        else:
            print(gray("  none"))
    if not args.json and not (orgs or packs or pols):
        print(gray("\n  no matches — try `ponens registry update` or broaden the query"))
    else:
        print(gray("\n  ponens policies show <source/id>     # a policy's full definition"))


# ----------------------------------------------------------------------------
# Argparse registration
# ----------------------------------------------------------------------------

def register(subparsers):
    """Register the 'search', 'sources', 'registry', and 'policies' command groups."""
    se = subparsers.add_parser("search", help="Search policies, packs, and organizations")
    se.add_argument("query", nargs="?", default="", help="Free-text query (id, name, description, tags)")
    se.add_argument("--type", choices=["policy", "pack", "org"],
                    help="Limit results to one kind (default: all three)")
    se.add_argument("--source", help="Limit to one source")
    se.add_argument("--category", help="Filter policies by category")
    se.add_argument("--severity", choices=["info", "warning", "error"], help="Filter policies by severity")
    se.add_argument("--domain", help="Filter policies by domain")
    se.add_argument("--tag", help="Filter policies by tag")
    se.add_argument("--json", action="store_true", help="Output raw JSON")
    se.set_defaults(func=cmd_search)

    src = subparsers.add_parser("sources", help="Manage policy sources")
    src_sub = src.add_subparsers(dest="sources_command", required=True)
    src_sub.add_parser("list", help="List configured policy sources").set_defaults(func=cmd_sources_list)
    p = src_sub.add_parser("add", help="Add a policy source to ./.ponens/sources.toml")
    p.add_argument("name")
    p.add_argument("--type", choices=["gallery", "local"], required=True)
    p.add_argument("--url", help="Gallery catalog URL (for --type gallery)")
    p.add_argument("--path", help="Directory of policy JSON (for --type local)")
    p.set_defaults(func=cmd_sources_add)

    reg = subparsers.add_parser("registry", help="Manage the policy registry cache")
    reg_sub = reg.add_subparsers(dest="registry_command", required=True)
    p = reg_sub.add_parser("update", help="Fetch/refresh gallery catalogs")
    p.add_argument("--source", help="Update only this source (default: all gallery sources)")
    p.set_defaults(func=cmd_registry_update)

    pol = subparsers.add_parser("policies", help="Search and load policies from configured sources")
    pol_sub = pol.add_subparsers(dest="policies_command", required=True)

    p = pol_sub.add_parser("search", help="Search policies across sources")
    p.add_argument("query", nargs="?", default="", help="Free-text query (id, name, description, tags)")
    p.add_argument("--source", help="Limit to one source")
    p.add_argument("--category", help="Filter by category")
    p.add_argument("--severity", choices=["info", "warning", "error"], help="Filter by severity")
    p.add_argument("--domain", help="Filter by domain")
    p.add_argument("--tag", help="Filter by tag")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.set_defaults(func=cmd_policies_search)

    p = pol_sub.add_parser("show", help="Show a policy's full definition (id or source/id)")
    p.add_argument("policy_id")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.add_argument("--refresh", action="store_true", help="Force re-fetch, bypassing the cache")
    p.set_defaults(func=cmd_policies_show)

    p = pol_sub.add_parser("add", help="Add a policy (id or source/id) into a local trace file")
    p.add_argument("policy_id")
    p.add_argument("--into", required=True, help="Path to the trace JSON file")
    p.add_argument("--refresh", action="store_true", help="Force re-fetch, bypassing the cache")
    p.set_defaults(func=cmd_policies_add)

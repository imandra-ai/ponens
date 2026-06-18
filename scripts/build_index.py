#!/usr/bin/env python3
"""Build the denormalized, content-hashed policy catalog for the gallery.

The gallery stores one JSON file per policy in ``gallery/policies/`` plus a
hand-curated ``_index.json`` (the id list + domain metadata the website reads).

This script produces ``gallery/policies/_catalog.json``: a single denormalized,
content-hashed catalog that downstream tooling (e.g. the ``ponens`` CLI) can
fetch once and search/pin locally — without fetching every policy file.

Usage:
    python3 scripts/build_index.py           # regenerate _catalog.json
    python3 scripts/build_index.py --check    # validate only; fail if stale (CI)

The script is pure-stdlib. If the ``ponens`` policy compiler happens to be
importable, each formula is additionally compiled as a stronger check; otherwise
a lightweight structural lint (balanced delimiters, non-empty) is used.
"""

import argparse
import glob
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
POLICY_DIR = os.path.join(ROOT, "gallery", "policies")
PACKS_DIR = os.path.join(ROOT, "gallery", "packs")
ORGS_DIR = os.path.join(ROOT, "gallery", "organizations")
INDEX_PATH = os.path.join(POLICY_DIR, "_index.json")
CATALOG_PATH = os.path.join(POLICY_DIR, "_catalog.json")
REASONER_INDEX = os.path.join(ROOT, "gallery", "reasoners", "_index.json")


def load_reasoner_ids():
    """Known reasoner ids, so a policy's `reasoner` reference can be checked
    against the reasoner registry. Empty (check skipped) if the registry is absent."""
    try:
        with open(REASONER_INDEX) as f:
            return set(json.load(f).get("reasoners", []))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

CATALOG_SCHEMA_VERSION = "1.0"

REQUIRED_FIELDS = ("id", "name", "category", "severity", "description", "formula", "domain")
VALID_SEVERITIES = {"info", "warning", "error"}
VALID_CATEGORIES = {
    "auditability", "communication", "conformance", "reasoning",
    "safety", "security", "structural", "workflow",
}
# Fields excluded from the content hash because they mutate independently of the
# policy's meaning (usage metrics), which would otherwise break version pinning.
HASH_EXCLUDE = {"downloads"}


# ----------------------------------------------------------------------------
# Hashing
# ----------------------------------------------------------------------------

def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def policy_hash(policy: dict) -> str:
    stable = {k: v for k, v in policy.items() if k not in HASH_EXCLUDE}
    digest = hashlib.sha256(canonical(stable).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


# ----------------------------------------------------------------------------
# Formula validation
# ----------------------------------------------------------------------------

def _to_trace_policy(policy: dict) -> dict:
    """Adapt a gallery policy to the shape the ponens compiler expects.

    Mirrors the adapter in the ponens CLI: the snake_case ``id`` becomes
    ``name`` (so structural policies match) and ``scope``/``kind`` are defaulted.
    """
    return {
        "policy_id": policy.get("id", ""),
        "name": policy.get("id", ""),
        "severity": policy.get("severity", "warning"),
        "scope": policy.get("scope", "trace"),
        "kind": policy.get("kind", "trace_invariant"),
        "formula": policy.get("formula", ""),
    }


def compiler_status(policy: dict):
    """Compatibility of this formula with the reference (ponens) compiler.

    Returns (status, message) where status is one of:
      - "ok":          the reference compiler parses and accepts the formula
      - "unsupported": the compiler is available but cannot evaluate it (e.g. the
                       formula uses predicates beyond this compiler version) —
                       informational, not a build failure
      - "unknown":     the compiler is not importable in this environment

    The gallery is intentionally broader than any single compiler version, so an
    "unsupported" result is recorded as catalog metadata rather than blocking.
    """
    try:
        from ponens.policy_compiler import check_policy  # type: ignore
    except Exception:
        return "unknown", None
    _, errors, _warnings = check_policy(_to_trace_policy(policy))
    if errors:
        return "unsupported", "; ".join(e.message for e in errors)
    return "ok", None


def _lint_formula(formula: str):
    """Lightweight fallback lint when the compiler is unavailable."""
    errors = []
    if not formula or not formula.strip():
        errors.append("empty formula")
        return errors
    depth = 0
    for ch in formula:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                errors.append("unbalanced ')' in formula")
                break
    if depth > 0:
        errors.append("unbalanced '(' in formula")
    return errors


# ----------------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------------

def validate_policy(policy: dict, filename: str, valid_domains: set, valid_reasoners: set):
    """Return a list of human-readable error strings for one policy file."""
    errors = []
    pid = policy.get("id", "")
    stem = os.path.splitext(os.path.basename(filename))[0]

    for field in REQUIRED_FIELDS:
        if not policy.get(field):
            errors.append(f"missing required field '{field}'")

    if pid and pid != stem:
        errors.append(f"id '{pid}' does not match filename '{stem}.json'")

    sev = policy.get("severity")
    if sev and sev not in VALID_SEVERITIES:
        errors.append(f"invalid severity '{sev}' (must be info/warning/error)")

    cat = policy.get("category")
    if cat and cat not in VALID_CATEGORIES:
        errors.append(f"invalid category '{cat}'")

    dom = policy.get("domain")
    if dom and valid_domains and dom not in valid_domains:
        errors.append(f"unknown domain '{dom}' (not in _index.json domains)")

    ex = policy.get("examples") or {}
    if not (ex.get("passes") and ex.get("fails")):
        errors.append("examples must include both 'passes' and 'fails'")

    # Hard lint: genuinely malformed formulas fail the build regardless of the
    # compiler. Compiler-version compatibility is recorded separately (metadata).
    errors.extend(f"formula: {m}" for m in _lint_formula(policy.get("formula", "")))

    # Cross-registry: a referenced reasoner must exist in the reasoner registry.
    ref = policy.get("reasoner")
    if ref and valid_reasoners and ref not in valid_reasoners:
        errors.append(f"unknown reasoner '{ref}' (not in gallery/reasoners/_index.json)")

    return errors


# ----------------------------------------------------------------------------
# Catalog construction
# ----------------------------------------------------------------------------

def load_policies():
    paths = sorted(
        p for p in glob.glob(os.path.join(POLICY_DIR, "*.json"))
        if not os.path.basename(p).startswith("_")
    )
    policies = []
    for path in paths:
        with open(path) as f:
            policies.append((path, json.load(f)))
    return policies


def load_manifests(directory):
    """Load standalone JSON manifests (one object per file) from a directory,
    sorted by id. Returns [] if the directory is absent (legacy layout)."""
    if not os.path.isdir(directory):
        return []
    out = []
    for path in sorted(glob.glob(os.path.join(directory, "*.json"))):
        with open(path) as f:
            out.append(json.load(f))
    return sorted(out, key=lambda m: m.get("id", ""))


def build_catalog(policies, index):
    # Packs and organizations are first-class JSON manifests under gallery/.
    # Fall back to inline _index.json arrays for the legacy layout.
    packs = load_manifests(PACKS_DIR) or index.get("packs", [])
    organizations = load_manifests(ORGS_DIR) or index.get("organizations", [])
    entries = []
    for _path, p in sorted(policies, key=lambda x: x[1].get("id", "")):
        status, _msg = compiler_status(p)
        entries.append({
            "id": p.get("id"),
            "name": p.get("name"),
            "category": p.get("category"),
            "severity": p.get("severity"),
            "domain": p.get("domain"),
            "tags": sorted(p.get("tags", [])),
            "language_level": p.get("language_level"),
            "reasoner": p.get("reasoner"),
            "description": p.get("description"),
            "formula": p.get("formula", ""),
            "version": p.get("version", "1.0.0"),
            "reference_compiler": status,
            "hash": policy_hash(p),
            "file": f"{p.get('id')}.json",
            # Pack membership (optional) — lets the gallery group/filter by pack
            # and lets organization pages list a pack's policies. `group` is the
            # pack's sub-grouping key (accepts the legacy `fix_domain` name).
            **({"pack": p["pack"]} if p.get("pack") else {}),
            **({"group": p.get("group") or p.get("fix_domain")}
               if (p.get("group") or p.get("fix_domain")) else {}),
            **({"tier": p["tier"]} if p.get("tier") else {}),
        })
    categories = sorted({e["category"] for e in entries if e["category"]})
    tags = sorted({t for e in entries for t in (e["tags"] or [])})
    # Stamp each pack with its policy membership count (derived from the policy
    # files, so the manifest never drifts from the actual policies).
    counts = {}
    for e in entries:
        if e.get("pack"):
            counts[e["pack"]] = counts.get(e["pack"], 0) + 1
    packs = [{**p, "policy_count": counts.get(p.get("id"), 0)} for p in packs]
    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "source": "gallery/policies",
        "policy_count": len(entries),
        "policies": entries,
        "categories": categories,
        "tags": tags,
        "domains": index.get("domains", {}),
        "organizations": organizations,
        "packs": packs,
    }


def serialize(catalog: dict) -> str:
    return json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"


def have_compiler() -> bool:
    try:
        import ponens.policy_compiler  # type: ignore  # noqa: F401
        return True
    except Exception:
        return False


def _without_compat(catalog: dict) -> dict:
    """Catalog copy with the environment-dependent compat field removed, so a
    staleness check stays valid in environments where the compiler is absent."""
    clone = dict(catalog)
    clone["policies"] = [
        {k: v for k, v in e.items() if k != "reference_compiler"}
        for e in catalog["policies"]
    ]
    return clone


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Build the gallery policy catalog.")
    ap.add_argument("--check", action="store_true",
                    help="Validate and fail if the committed catalog is stale (for CI).")
    args = ap.parse_args()

    with open(INDEX_PATH) as f:
        index = json.load(f)
    valid_domains = set(index.get("domains", {}).keys())
    valid_reasoners = load_reasoner_ids()
    indexed_ids = set(index.get("policies", []))

    policies = load_policies()
    file_ids = {p.get("id") for _path, p in policies}

    # Per-policy validation
    all_ok = True
    for path, policy in policies:
        errors = validate_policy(policy, path, valid_domains, valid_reasoners)
        if errors:
            all_ok = False
            print(f"FAIL  {os.path.basename(path)}")
            for e in errors:
                print(f"      {e}")

    # _index.json <-> files consistency
    missing_from_index = file_ids - indexed_ids
    missing_files = indexed_ids - file_ids
    if missing_from_index:
        all_ok = False
        print(f"FAIL  ids present as files but missing from _index.json: "
              f"{sorted(missing_from_index)}")
    if missing_files:
        all_ok = False
        print(f"FAIL  ids in _index.json with no policy file: {sorted(missing_files)}")

    # Pack / organization manifest integrity
    packs = load_manifests(PACKS_DIR)
    orgs = load_manifests(ORGS_DIR)
    pack_ids = {p.get("id") for p in packs}
    org_ids = {o.get("id") for o in orgs}
    for p in packs:
        if p.get("org") and p["org"] not in org_ids:
            all_ok = False
            print(f"FAIL  pack '{p.get('id')}' references unknown org '{p['org']}'")
    for _path, policy in policies:
        pk = policy.get("pack")
        if pk and pk not in pack_ids:
            all_ok = False
            print(f"FAIL  policy '{policy.get('id')}' references unknown pack '{pk}'")

    if not all_ok:
        print("\nValidation failed.")
        return 1

    catalog = build_catalog(policies, index)
    rendered = serialize(catalog)

    # Surface (but do not fail on) policies the reference compiler can't evaluate.
    unsupported = [e["id"] for e in catalog["policies"]
                   if e["reference_compiler"] == "unsupported"]
    unknown = any(e["reference_compiler"] == "unknown" for e in catalog["policies"])
    if unknown:
        print("note: ponens compiler not importable — reference_compiler=unknown "
              "(install ponens for full formula checks).")
    elif unsupported:
        print(f"note: {len(unsupported)} policies need a newer reference compiler: "
              f"{sorted(unsupported)}")

    if args.check:
        if not os.path.exists(CATALOG_PATH):
            print("FAIL  _catalog.json does not exist; run scripts/build_index.py")
            return 1
        with open(CATALOG_PATH) as f:
            committed = json.load(f)
        if have_compiler():
            stale = committed != catalog
        else:
            # Compiler unavailable: the reference_compiler field can't be
            # recomputed, so compare everything else and skip that field.
            stale = _without_compat(committed) != _without_compat(catalog)
        if stale:
            print("FAIL  _catalog.json is stale; run scripts/build_index.py and commit.")
            return 1
        print(f"OK    {catalog['policy_count']} policies validated; catalog up to date.")
        return 0

    with open(CATALOG_PATH, "w") as f:
        f.write(rendered)
    print(f"Wrote {os.path.relpath(CATALOG_PATH, ROOT)} "
          f"({catalog['policy_count']} policies).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

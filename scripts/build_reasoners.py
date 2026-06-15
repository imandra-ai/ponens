#!/usr/bin/env python3
"""Build the reasoner registry catalog (mirrors build_index.py for policies).

The registry stores one JSON file per reasoner in ``gallery/reasoners/`` plus a
hand-curated ``_index.json`` (the id list + kind metadata). This script validates
each reasoner and produces ``gallery/reasoners/_catalog.json`` — the denormalized,
content-hashed catalog the website and tooling read.

A *reasoner* is an automated-reasoning tool (e.g. Imandra CodeLogician, ImandraX)
that produces a trace's verification artifacts and that policies can *require*.

Usage:
    python3 scripts/build_reasoners.py            # regenerate _catalog.json
    python3 scripts/build_reasoners.py --check    # validate; fail if stale (CI)
"""
import argparse
import glob
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DIR = os.path.join(ROOT, "gallery", "reasoners")
INDEX_PATH = os.path.join(DIR, "_index.json")
CATALOG_PATH = os.path.join(DIR, "_catalog.json")

CATALOG_SCHEMA_VERSION = "1.0"
REQUIRED = ("id", "name", "kind", "description", "status")
VALID_STATUS = {"available", "experimental", "community", "planned"}


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def reasoner_hash(r):
    return "sha256:" + hashlib.sha256(canonical(r).encode("utf-8")).hexdigest()


def validate(r, filename, valid_kinds):
    errors = []
    stem = os.path.splitext(os.path.basename(filename))[0]
    for field in REQUIRED:
        if not r.get(field):
            errors.append(f"missing required field '{field}'")
    if r.get("id") and r["id"] != stem:
        errors.append(f"id '{r['id']}' does not match filename '{stem}.json'")
    if r.get("status") and r["status"] not in VALID_STATUS:
        errors.append(f"invalid status '{r['status']}' (one of {', '.join(sorted(VALID_STATUS))})")
    if r.get("kind") and valid_kinds and r["kind"] not in valid_kinds:
        errors.append(f"unknown kind '{r['kind']}' (not in _index.json kinds)")
    return errors


def load():
    out = []
    for p in sorted(glob.glob(os.path.join(DIR, "*.json"))):
        if os.path.basename(p).startswith("_"):
            continue
        with open(p) as f:
            out.append((p, json.load(f)))
    return out


def build_catalog(reasoners, index):
    entries = []
    for _p, r in sorted(reasoners, key=lambda x: x[1].get("id", "")):
        entries.append({
            "id": r.get("id"), "name": r.get("name"), "kind": r.get("kind"),
            "vendor": r.get("vendor"), "status": r.get("status"),
            "description": r.get("description"), "produces": r.get("produces", []),
            "domains": r.get("domains", []), "tags": sorted(r.get("tags", [])),
            "url": r.get("url"), "hash": reasoner_hash(r), "file": f"{r.get('id')}.json",
        })
    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "source": "gallery/reasoners",
        "reasoner_count": len(entries),
        "reasoners": entries,
        "kinds": index.get("kinds", {}),
        "statuses": sorted({e["status"] for e in entries if e["status"]}),
    }


def main():
    ap = argparse.ArgumentParser(description="Build the reasoner registry catalog.")
    ap.add_argument("--check", action="store_true", help="Fail if the committed catalog is stale (CI).")
    args = ap.parse_args()

    with open(INDEX_PATH) as f:
        index = json.load(f)
    valid_kinds = set(index.get("kinds", {}).keys())
    indexed = set(index.get("reasoners", []))

    reasoners = load()
    file_ids = {r.get("id") for _p, r in reasoners}

    ok = True
    for path, r in reasoners:
        errs = validate(r, path, valid_kinds)
        if errs:
            ok = False
            print(f"FAIL  {os.path.basename(path)}")
            for e in errs:
                print(f"      {e}")
    missing = indexed - file_ids
    extra = file_ids - indexed
    if missing:
        ok = False; print(f"FAIL  _index.json lists ids with no file: {sorted(missing)}")
    if extra:
        ok = False; print(f"FAIL  reasoner files not in _index.json: {sorted(extra)}")
    if not ok:
        sys.exit(1)

    catalog = build_catalog(reasoners, index)
    serialized = json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"

    if args.check:
        current = open(CATALOG_PATH).read() if os.path.exists(CATALOG_PATH) else ""
        if current != serialized:
            print("FAIL  _catalog.json is stale — run `python3 scripts/build_reasoners.py`")
            sys.exit(1)
        print(f"OK    {len(catalog['reasoners'])} reasoners; catalog up to date.")
        return

    with open(CATALOG_PATH, "w") as f:
        f.write(serialized)
    print(f"Wrote {CATALOG_PATH} ({len(catalog['reasoners'])} reasoners).")


if __name__ == "__main__":
    main()

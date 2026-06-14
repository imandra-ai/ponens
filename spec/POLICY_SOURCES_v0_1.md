# Policy Sources Specification

## Version

**Version:** 0.1
**Status:** Draft
**Format:** CLI/tooling specification with config and resolution semantics
**Positioning:** Companion to the Policy Specification and the CLI Sync Model

---

# 1. Purpose

Policies come from more than one place. A team uses the **public gallery** for community
standards, writes **its own** policies, and pulls **corporate-specific** policies and packs from a
a private **hub**. This specification defines how the `ponens` CLI organizes several *sources*
of policies so they can coexist, be searched together, be referenced unambiguously, and carry their
provenance into the traces they govern.

> **Policy sources are to ponens what registries are to a package manager and remotes are to git:** named, typed, layered, cached, and referenced by a qualified name.

---

# 2. Relationship to the Other Specifications

- the **Policy Specification** defines what a policy *is* (its object model and DSL);
- the **CLI Sync Model** defines how the CLI moves traces between the working tree, git, and a hub;
- this **Policy Sources Specification** defines where the CLI *gets policies from*, and how it
  records which source a policy came from.

A policy's identity and content are unchanged by where it lives; sources are a *distribution and
trust* layer, not a semantic one.

---

# 3. The Sources Model

A **source** is a named, typed origin of policies (and packs). Three types:

| Type | What it is | Backing |
|---|---|---|
| `gallery` | a published static catalog (`_catalog.json` + per-policy JSON) over HTTP — the public gallery, or any hosted one | hash-verified per-source cache |
| `local` | a directory of policy JSON files on disk — your own / a team's, committed in-repo | read live, no cache |
| `hub` *(future)* | an authenticated **the hub** backend — corporate-specific policies and packs | the hub API + token (§10) |

Every source has a unique **name** within the resolved configuration. `gallery` sources carry a
`url`; `local` sources carry a `path`; `hub` sources carry a `url` (+ credentials).

---

# 4. Configuration

Sources are declared in **`sources.toml`**, layered like `.gitconfig` / `.npmrc`:

- **user-global** — `~/.ponens/sources.toml`
- **project** — the nearest `.ponens/sources.toml` walking up from the working directory (committed, team-shared)

```toml
[[source]]
name = "community"          # the public gallery
type = "gallery"
url  = "https://ponens.dev/gallery/policies"

[[source]]
name = "acme"               # corporate, from the hub (future)
type = "hub"
url  = "https://hub.acme.com"

[[source]]
name = "team"               # our own policies, in the repo
type = "local"
path = ".ponens/policies"
```

## 4.1 Resolution and order

The resolved source list is the user sources followed by the project sources; a project entry
with the same `name` **overrides** the user entry in place. With **no** config at all, a single
built-in `community` gallery source is used (its URL honours the `PONENS_REGISTRY_URL` environment
override for back-compatibility).

The list **order is the precedence** used to resolve unqualified references (§5).

---

# 5. References and Resolution

A policy is referenced by id, optionally **qualified by source** with a `/`:

```
community/tests_before_commit      # explicit source
acme/pci_review
team/my_rule
tests_before_commit                # unqualified — resolved by source order
```

Resolution rules:

- a **qualified** reference resolves to exactly that source (error if the source or id is absent);
- an **unqualified** reference is searched across all sources in order:
  - **0 matches** → error;
  - **1 match** → resolved;
  - **>1 match** → **error**, listing the qualified options — the CLI never silently shadows one source with another.

> **Qualify to be precise; rely on order only when an id is unique across your sources.**

---

# 6. Cache and Integrity

Each **gallery** source has its **own** cache namespace under `~/.ponens/registry/<name>/`
(`_catalog.json` + `policies/`). `ponens registry update [--source X]` refreshes the catalog(s).
**Local** sources are read live and are never cached.

A cached policy body is reused only if its content hash matches the catalog entry's `hash`
(`sha256` over canonical JSON, excluding the `downloads` metric — identical to the gallery builder).
On mismatch — staleness or tampering — it is **re-fetched** (self-healing cache + integrity check);
`--refresh` forces a re-fetch. This is the same mechanism per source.

---

# 7. Provenance

When a policy is materialized into a trace (`policies add`), the CLI stamps **which source it came
from** onto the embedded policy:

```json
"source": { "source": "acme", "id": "pci_review", "version": "3.0.0", "hash": "sha256:…" }
```

A trace therefore records the provenance of every policy it was checked against — exactly what a
compliance or audit reviewer needs ("governed by Acme's PCI policy v3, hash …"). Combined with the
trace's own `content_hash` and snapshots, this closes the loop from *source → policy → trace →
sign-off*.

Local (`type = "local"`) policies should be validated through the reference compiler on `add` (the
same checks the gallery builder applies), so a malformed hand-written policy is caught immediately.

---

# 8. Command Surface

```bash
ponens sources list                                  # configured sources + cache state
ponens sources add team --type local --path .ponens/policies
ponens sources add acme --type gallery --url https://…/gallery/policies

ponens registry update [--source acme]               # refresh gallery catalog(s)

ponens policies search pci [--source acme]           # across all sources; shows a Source column
ponens policies show  acme/pci_review                # qualified
ponens policies add   acme/pci_review --into trace.json
```

Packs (a named list of policy ids distributed by a source, especially `hub`) follow the same
reference grammar (`source/pack`) and materialize all their policies into the trace; see the
Policy Specification for the pack object.

---

# 9. Trust and Precedence

- **No silent shadowing.** Ambiguous unqualified ids are an error, not a coin flip (§5).
- **Provenance is mandatory on materialization.** A governed trace always records its policies'
  sources (§7).
- **Integrity is verified.** Cached bodies are hash-checked against the catalog (§6).
- **Local-first.** `search` and resolution run offline against caches and local directories; only
  `registry update` and a cache-miss fetch touch the network.
- **Project pins, user extends.** Teams commit `.ponens/sources.toml` to pin the sources a repo
  trusts; individuals add personal sources in `~/.ponens/sources.toml`.

---

# 10. Open Questions / Future

- **The `hub` source type** — authenticated corporate policies and packs from the hub. Depends on
  the headless **token model** (`PONENS_HUB_TOKEN`), already an open question in the CLI Sync Model.
  It reuses the hub API and the scoped-pack model the hub already exposes.
- **Cross-source packs** — a pack listing policies from several sources (`community/tests_before_commit`
  + `acme/pci_review`). The reference grammar supports it; resolution per-entry follows §5.
- **Signed sources** — provenance currently records source + content hash; signing a source's
  catalog (Sigstore-style) would let the CLI verify *authenticity*, not only integrity.
- **Source pinning** — pinning a source to a catalog version/hash in `sources.toml` for fully
  reproducible policy resolution.

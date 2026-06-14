# CLI Sync Model Specification

## Version

**Version:** 0.1  
**Status:** Draft  
**Format:** Canonical workflow specification with command-surface and git-binding notes  
**Positioning:** Companion specification to the Trace, Policy, and Review-Case Specifications

---

# 1. Purpose

The **CLI sync model** defines how the `ponens` command-line interface keeps three
artifacts consistent over the lifetime of a piece of agent work:

- a **local trace file** in the working tree,
- a **git commit** (anchored on GitHub or any git remote), and
- a **hub record** (status, comments, review items, snapshots, policy runs).

A trace captures *what reasoning happened*. A commit captures *which version of the code it
happened against*. The hub captures *what people and policies decided about it*. No single
layer owns all three facts. The CLI is the tool that binds them and keeps them in sync.

A good one-line summary is:

> **The CLI makes the hub a git remote for reasoning: traces are pushed, pulled, and bound to commits the same way code is.**

---

# 2. Relationship to the Other Specifications

This specification is intended to be used together with:

- the **trace specification** — defines the object model of a single trace,
- the **policy specification** — defines policies as formulas interpreted over traces,
- the **review-case specification** — defines the workflow container above traces.

The split is:

- the **trace specification** defines trace *content*,
- the **policy specification** defines the *gate* evaluated over that content,
- the **review-case specification** defines the *workflow object* that governs traces over time,
- the **CLI sync model** (this document) defines how trace content is *moved and bound* between
  the local working tree, git, and the hub.

This specification does **not** redefine trace structure, the policy DSL, or the review-case
workflow. It defines only the synchronization layer that connects them to git and to the hub.

---

# 3. Three Layers and Their Ownership

```text
   WORKING TREE                 GIT / GITHUB                 HUB
 ┌───────────────┐           ┌─────────────────┐         ┌──────────────────┐
 │ trace.json    │  bind     │ commit  abc123  │  push   │ trace-… (record) │
 │ (the agent    │◀────────▶ │  + trailer:     │◀──────▶ │  status, comments│
 │  writes it as │           │  Trace-Id: …    │  pull   │  reviews, packs, │
 │  it works)    │           │  (or git note)  │         │  snapshots       │
 └───────────────┘           └─────────────────┘         └──────────────────┘
   canonical for CONTENT       canonical for VERSION        canonical for
   (immutable, hashed)         (which code state)           DECISIONS / state
```

| Layer | Owns | Identity field |
|---|---|---|
| **Local file** | the *content* of the reasoning — immutable, content-hashed | `content_hash = sha256(canonical(trace))` |
| **Git commit** | the *version anchor* — which code state the reasoning was about | `commit_sha` |
| **The hub** | *collaboration + governance* — status, comments, reviews, snapshots, policy runs | `trace_id` |

The local file is canonical for content; git is canonical for version; the hub is canonical for
decisions. The CLI never lets these silently diverge — `ponens status` exists to surface
divergence explicitly.

---

# 4. Design Principles

1. **The local file is canonical for content.**
   Trace content is authored locally (by the agent, as it works) and is immutable once hashed.
   The hub stores a copy plus collaboration state; it does not mutate trace content.

2. **Git is canonical for version.**
   Every trace is bound to exactly one commit. The commit, not a timestamp, answers "which
   version of the code does this reasoning explain?"

3. **The hub is canonical for decisions.**
   Status, comments, review items, approvals, and snapshots live on the hub. `pull` brings them
   down read-only; it never edits the working tree.

4. **One trace, one commit.**
   The binding is **1:1** (see §6). Iteration produces a *new commit* and a *new trace* that
   `supersedes` the prior one. The supersedes chain runs parallel to the git history.

5. **Sync is explicit and git-shaped.**
   The verbs are `bind`, `push`, `pull`, `status`, `check` — chosen to match a developer's
   existing git mental model. There is no hidden background sync.

6. **Immutability is preserved on push.**
   If trace content changed since the last push, `push` does not overwrite the prior record. It
   creates a successor trace and links it `supersedes` (see §7.2).

---

# 5. The Trace–Commit Binding

The binding is **bidirectional**, so it can be resolved starting from either side.

### 5.1 Trace → commit

The trace JSON embeds the git context (these fields already exist in the trace schema):

- `repo` — the `org/repo` slug, derived from the git remote URL,
- `branch` — the current branch,
- `commit_sha` — `HEAD` at bind time.

The CLI fills these automatically from the local git repository. They are **not** hand-passed.

### 5.2 Commit → trace

`ponens bind` writes the trace identity back into git so the trace is discoverable from the
commit (e.g. in a GitHub PR view). Two mechanisms are supported:

- a **commit trailer** — `Trace-Id: trace-<id>` appended to the commit message, or
- a **git note** — `refs/notes/ponens` carrying the `trace_id`, for cases where the commit
  message must not be modified (e.g. after the commit already exists).

Either mechanism makes the relationship resolvable in both directions:
`commit_sha ⇄ trace_id`.

### 5.3 Content hash

`content_hash` is computed over a canonical serialization of the trace content (stable key
order, normalized whitespace), **excluding** mutable transport fields such as the top-level
`timestamp`. It is the integrity check that detects "the file changed but was not re-pushed,"
and the key that `push` uses to decide *update vs. successor* (§7.2).

---

# 6. The 1:1 Mapping (Normative)

A trace is bound to **exactly one** commit, and a commit has **at most one** active trace.

This yields three invariants the CLI enforces:

1. **No second trace per commit.**
   `push` rejects creating a new trace for a `commit_sha` that already has one. A content change
   must come from a new commit, which produces a successor trace.

2. **Stale-binding detection.**
   If `HEAD` has moved past `commit_sha`, `ponens status` reports the trace as *stale* and
   instructs the user to re-`bind` and `push` a successor.

3. **Unambiguous approval.**
   Because each commit has one trace and each trace one commit, "which trace was approved" is
   always unambiguous, and the supersedes chain is one-to-one with the relevant commit history.

> **A trace shows one run; a commit pins one version; the 1:1 binding keeps "which reasoning explains which code" unambiguous.**

---

# 7. Command Surface

All commands operate on the trace bound to the current working tree / `HEAD` unless given an
explicit target. All read commands accept `--json`.

> **Status.** All verbs below are implemented in the CLI: the gate (`ponens trace check`), the
> registry verbs (`registry update`, `policies search/show/add`), and the sync verbs (`bind`, `push`,
> `pull`, `status`). `bind` and `status` work fully offline against local git; `push` and `pull`
> require a reachable hub backend. By default `bind` records the binding as a **git note**
> (`refs/notes/ponens`, non-mutating; §5.2), and the local↔hub mapping is kept in a `.sync` sidecar
> beside the trace file.

### 7.1 `ponens bind`

Stamp the local trace with `repo` / `branch` / `commit_sha` from git, and write the
`Trace-Id` trailer or git note back onto the commit. Idempotent: re-binding the same commit is a
no-op; binding after `HEAD` moved updates the stamp to the new commit (and, per §6, will produce
a successor on the next `push`).

### 7.2 `ponens push`

1. Compute `content_hash` of the local file.
2. If no hub record exists for this `commit_sha` → **create** the trace record, attach
   `commit_sha`, `content_hash`, and any `--policy-pack` attachments.
3. If a record exists with the **same** `content_hash` → no-op (already pushed).
4. If a record exists for a **different** commit and the content changed → **create a successor**
   trace and link it `supersedes` the prior trace (preserving immutability).
5. Push is **non-interactive and idempotent** — safe to run from a hook or CI, retry-safe.

### 7.3 `ponens pull`

Fetch hub-side collaboration and governance state for the bound trace: `status`, comments,
review items, snapshots, and policy-run results. **Read-only with respect to the working tree** —
`pull` never edits `trace.json` or git.

### 7.4 `ponens status`

Show divergence across the three layers:

- local file vs. last pushed record (`content_hash` match?),
- bound `commit_sha` vs. `HEAD` (stale binding?),
- hub `status` and any open blocking review items.

This is the primary "where do things stand" command and the safety net against silent
divergence.

### 7.5 `ponens check`

Run the policies **resolved locally** — those embedded in the trace, supplied via `--policy-file`,
or materialized from the registry cache (`policies add` / `pull`) — against the local trace using
the built-in policy compiler, and return an **exit code**. Advisory in interactive use; a hard gate
in autonomous use (§8). Policy *pack attachment* is a hub concept; the offline gate never requires
the hub.

---

# 8. Use Cases

The command surface is identical across use cases. What differs is **who closes the loop** and
**whether the policy gate is advisory or blocking.**

### 8.1 AI coding — human in the loop

```text
agent reasons ──▶ writes trace.json ──▶ developer commits
                                          │  (post-commit hook)
                                          ▼
                              ponens bind && ponens push   → status: shared
                                          │
                  reviewers comment on PR ◀┘ (trace linked from commit trailer)
                                          │
                  developer: ponens pull ──▶ sees review items ──▶ iterates
                                          │
                       new commit ──▶ successor trace supersedes ──▶ approve → snapshot
```

- **Sync is explicit; `check` is advisory.** The human is the gate and the decision-maker.
- Identity is the **developer** (interactive user identity).
- The hub is the **review surface** alongside the PR.

### 8.2 Autonomous agent — no human in the loop

```text
agent produces code + trace
        │
        ▼
ponens check  ──FAIL──▶ no commit / PR opened as needs_attention      ← HARD GATE
        │ PASS
        ▼
git commit ──▶ ponens bind && push   (headless, machine token)
        │
        ▼
PR opened, trace attached  ──▶  reviewer agent or compliance pulls
                                review items and acts asynchronously
```

- **The policy gate is blocking.** `ponens check`'s exit code is the merge gate; failed
  policies drive the trace to `needs_attention` and block merge.
- Identity is a **service / agent token**, not an interactive user switch. `push` must be
  headless, deterministic, and retry-safe.
- Status transitions are **policy-driven**, not click-driven. The loop is closed by another
  agent or by compliance pulling review items rather than reading a UI.

The unifying idea:

> **In AI coding the human is the gate; in autonomous mode the policy pack is the gate — and the hub is where that gate's verdict becomes an auditable, signed-off record either way.**

---

# 9. Git as a Collaboration Channel

The hub deliberately uses git as a **collaboration substrate**, not merely as a metadata field.
This section defines how far that goes and — equally importantly — where it stops, so that git,
the git platform (GitHub/GitLab), and the hub each carry only what they are best at.

### 9.1 What lives in git

Git carries two things and only two things:

- the **trace itself**, committed in-repo (e.g. `.ponens/<trace>.json`), so the reasoning
  change appears in the same diff / pull request as the code change, and
- the **commit ⇄ trace binding** (the `Trace-Id` trailer or git note from §5.2), so the commit is
  the bidirectional anchor between code and reasoning.

Because the trace is part of the reviewable diff, a reviewer — human or agent — sees the
reasoning alongside the code in the pull request, with no hub required.

### 9.2 What does *not* live in git

Review threads, review items, approvals, and snapshots are **not** stored in git (neither as
committed files nor as git notes). Git is built to snapshot code, not to host mutable,
multi-writer, append-heavy conversation. Storing review state in git would mean:

- fighting the data model — git notes do not merge cleanly, and committed review files conflict
  on every parallel comment;
- reinventing notifications, identity, and blocking-merge semantics the platform already
  provides; and
- creating a **third** place review lives (PR thread + committed review state + hub), which then
  drifts out of sync.

Git therefore carries the trace and the binding, never the review threads.

### 9.3 Three substrates, one anchor

Review-related concerns are split across three layers by what each does best. They overlap
near-zero when scoped cleanly, because they govern **different objects**:

| Concern | Home | Why it is not a duplicate |
|---|---|---|
| Human discussion of the **code diff** | **git platform (PR)** | Reviewers comment on lines; mature and already in use. |
| Review of the **reasoning** — a counterexample, proof, artifact, or policy result | **The hub** | These are not lines in a diff; a PR cannot target "artifact a5's counterexample" or "policy p11's evaluation." |
| **Computable** governance — blocking gates, policy-tied review items | **The hub** | A PR "Approved" is a social signal, not an object a policy can be evaluated over. |
| **Frozen audit record** — this trace content + these policy results, signed | **hub snapshot** | A PR approval does not freeze the trace's `content_hash` + policy run for a later auditor. |
| Governance across a **chain of traces** (the review case) | **The hub** | A PR is scoped to one diff/branch; the review case spans the supersedes chain over time. |

The pull request reviews the **change**; the hub reviews the **reasoning behind the change** and
freezes it for audit. The **commit** is the shared anchor that connects them.

### 9.4 Integration, not duplication

The git platform's review workflow is **reused, not reimplemented**. The connection runs through
the commit binding:

- the `Trace-Id` trailer lets a PR reviewer jump to the reasoning, and vice versa;
- PR approval may **feed** the trace's status as one input — it does not re-implement review; and
- policy results **post back** to the PR as a status check or comment.

The only review-layer concern with **no equivalent** on the git platform is the **snapshot** —
the frozen, policy-bound, portable audit artifact. That is the part the hub layer uniquely earns,
and the reason the hub remains necessary even when pull requests exist.

> **Let the git platform own human review of the diff. Let the hub own computable governance and audit over the reasoning. Connect them through the commit — do not reimplement either inside the other.**

This is the **binding-only** decision: git carries the trace and the link; the platform carries
human diff review; the hub carries computable governance and snapshots. Fully git-native review
(review state committed into git) is explicitly rejected for the reasons in §9.2, and noted as a
revisitable question in §11.

---

# 10. Synchronization State

At any moment the bound trace is in one of the following sync states, reported by
`ponens status`:

| State | Meaning | Resolution |
|---|---|---|
| `unbound` | local trace has no `commit_sha` | `ponens bind` |
| `bound, unpushed` | bound to a commit, not yet on the hub | `ponens push` |
| `synced` | local `content_hash` matches the pushed record, binding current | none |
| `stale` | `HEAD` has moved past the bound commit | re-`bind`, then `push` (successor) |
| `dirty` | local content changed vs. pushed record on the same commit | commit the change → successor trace |
| `behind` | hub has new collaboration state (comments / status) | `ponens pull` |

`synced` is the only steady state. Every other state names a concrete next command, so the model
never leaves the user guessing.

---

# 11. Example Workflows

These tutorials use the **existing** local verbs (`trace init / check / status / view`) and hub
verbs (`traces`, `comments`, `ri`, `packs`, `snap`), together with the **sync verbs** defined in
§7 (`bind`, `push`, `pull`, `status`, `check`). Where a verb operates on "the trace bound to the
working tree," no path is needed; otherwise the trace file or `trace_id` is given explicitly. The
running example throughout is the Stripe payment-flow trace (`demo-traces/stripe_v1_1.json`).

Autonomous examples assume a headless machine identity via `PONENS_HUB_TOKEN`; interactive examples
use the current user.

### 11.1 Author and share a trace (AI coding, human in the loop)

The agent records its reasoning as it works, the developer commits code and trace together, and
the trace lands in the pull request for review.

```bash
# 1. The agent authors the trace as it reasons (init, then append actions/artifacts).
ponens trace init .ponens/stripe.json --title "Add 3DS + high-risk approvals"
#    … agent appends actions, artifacts, proofs, the decomposition, tests …
ponens trace complete .ponens/stripe.json

# 2. Materialize the org pack locally, then gate (advisory in interactive use).
ponens pull --pack pack_org_payments_v3      # cache the pack for an offline-faithful check
ponens check .ponens/stripe.json           # exit 0 = clean; warnings are advisory here

# 3. Commit code + trace together, bind, push.
git add . && git commit -m "Add 3DS + high-risk approvals"
ponens bind                                  # stamp repo/branch/commit; write Trace-Id trailer
ponens push                                  # create hub record → status: shared

# 4. Open the PR. Reviewers see the trace in the diff and reach it from the commit trailer.
```

Leaves the trace **synced** (§10), bound 1:1 to the commit, discoverable from both the PR diff and
the commit trailer.

### 11.2 Respond to review and iterate (the supersedes chain)

Review feedback comes back; the fix produces a *new commit*, which under the 1:1 rule produces a
*successor trace*.

```bash
ponens pull                                  # fetch comments + review items
ponens status                                # was 'behind' → now synced; lists blocking items
#    … agent/dev addresses the issue and re-runs the reasoning …
ponens check .ponens/stripe.json
git commit -am "Reset amount_refunded on re-capture; re-prove invariant"
ponens bind && ponens push                 # new commit → successor trace, supersedes prior
ponens ri resolve trace-stripe-… <item_id> -n "Fixed; amount invariant re-proved"
```

The successor trace links `supersedes` the prior one automatically (§7.2); the supersedes chain
now mirrors the two commits one-to-one.

### 11.3 Autonomous agent with a blocking gate (no human in the loop)

Run unattended in CI or an agent loop. The policy gate is a **hard** merge gate, and the loop is
closed by reading review items back, not by a UI.

```bash
# Gate BEFORE committing — nonzero exit means no commit, no PR.
ponens check .ponens/stripe.json || { echo "policy gate failed"; exit 1; }

git commit -am "Add 3DS + high-risk approvals"
ponens bind && ponens push                 # headless, idempotent, retry-safe

# Poll for a verdict and branch on it.
ponens status --json                         # → status, open blocking items
#   if needs_attention:
ponens ri ls trace-stripe-… --json           # read blocking items → self-correct → loop (11.2)
#   if approved:  a separate reviewer agent or compliance signs off (do not self-approve)
```

The producing agent never approves its own work — §11.4 shows the reviewer side. The entire
**gate** (`check`) runs offline (§ local-first); only `push` / `status` need the hub.

### 11.4 Review a trace via git (reviewer side)

A reviewer — human or a dedicated reviewer agent — picks up the change from the PR, reviews the
*reasoning* on the hub, and freezes a snapshot for audit.

```bash
git checkout pr-branch
git log -1                                      # the commit carries the Trace-Id trailer
ponens pull                                   # refresh the hub record bound to this commit
ponens trace view .ponens/stripe.json       # open the embedded visualizer (flow, proofs, regions)

# Comment on the reasoning, not the diff lines.
ponens comments add trace-stripe-… "Counterexample at a5 must be addressed" \
  --target-type artifact --target-id a5
ponens ri add trace-stripe-… "Re-prove amount invariant after fix" --blocking

# When satisfied: freeze + sign off, then advance hub status.
ponens snap create trace-stripe-…
ponens snap approve <snapshot_id> -n "14 properties proved; 84/84 regions tested"
ponens traces status trace-stripe-… approved
```

The **snapshot** is the audit artifact with no git-platform equivalent (§9.4): it freezes the
exact `content_hash` + policy results that were approved.

### 11.5 Offline / air-gapped, reconcile later

No server reachable. Authoring and the gate are fully local; binding writes into git with no
network; publishing happens when connectivity returns.

```bash
# No hub. Author and gate against a local pack file.
ponens trace init .ponens/stripe.json --title "Add 3DS + high-risk approvals"
#    … append reasoning …
ponens trace complete .ponens/stripe.json
ponens check .ponens/stripe.json --policy-file packs/payments_v3.json
ponens trace status .ponens/stripe.json

git commit -am "Add 3DS + high-risk approvals"
ponens bind                                   # writes Trace-Id trailer into the commit; offline

# Later, with connectivity:
ponens push                                   # publish trace + binding; reconcile with the hub
```

Demonstrates the core local-first property: the **gate is offline by design**, and the hub is only
needed to *share* the verdict.

---

# 12. Open Questions

- **Fully git-native review.** Whether review items / approvals should ever be representable in
  git itself (for true no-hub, two-party collaboration), accepting the merge, identity, and
  drift costs in §9.2. Rejected by default in v0.1; revisit only if a hub-less collaboration
  requirement emerges that the git platform's PR review cannot satisfy.
- **Squash / rebase.** When several working commits collapse into one squashed commit, which
  commit anchors the trace? Default: the final merged commit; the intermediate traces become a
  superseded chain. To be confirmed against real squash-merge workflows.
- **Multi-repo / monorepo paths.** Whether `repo` should carry a sub-path for monorepos, or
  whether the commit slug is sufficient.
- **Trailer vs. note default.** Whether `bind` should default to a commit trailer (visible,
  mutates message) or a git note (invisible, non-mutating) — likely policy-pack configurable.
- **Token model.** The exact shape of the headless machine token for autonomous `push`, and how
  it maps to an org / service identity on the hub.

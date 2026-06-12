# Trace Review Handoff Specification

## Version

**Version:** 0.1
**Status:** Draft
**Format:** Reasoner-agnostic protocol specification
**Positioning:** Companion to the Trace, Policy, and Review-Case Specifications

---

# 1. Purpose

A trace is produced by one agent and consumed by another. Increasingly, the producer is a
**coding agent** and the consumer is a **reviewing agent** — and they do not share a session,
a vendor, or a memory. Between them sits the diff, which is a *lossy* interface: it shows what
changed, not what the producer tried, ruled out, verified, assumed, or left undone.

This specification defines the **review handoff contract**: how a reviewing agent should ingest
a trace so that review becomes **targeted and evidence-grounded** rather than a blind
re-derivation from the diff. The trace's **residual surface** (Trace Spec §13) is the spine of
the protocol — it is the producer's declared negative space, and it tells the consumer where to
point.

> **A producing agent declares its gaps; a reviewing agent verifies the claims and hunts the undeclared ones.**

This document is reasoner-agnostic. It defines a *protocol*, not an implementation, and applies
whether the reviewer is an autonomous agent, a human, or a human assisted by an agent.

---

# 2. Relationship to the Other Specifications

- the **Trace Specification** defines the object being handed off, including the residual surface;
- the **Policy Specification** defines the *mechanical gate* — requirements evaluated over a trace;
- the **Review-Case Specification** defines the *workflow container* that accumulates verdicts across a chain of traces;
- this **Review Handoff Specification** defines the *consumption protocol* a reviewer runs over a single trace.

Policies are the gate; the review handoff is the judgment layer. Both operate over the same
trace. A policy says *whether a rule holds*; the handoff protocol says *how a reviewer reads the
trace, what it may rely on, and what it must independently check*.

---

# 3. The Handoff Contract

## 3.1 Producer obligations

A trace offered for review should:

- record the **positive space** — actions, artifacts, and results — with consequential claims
  **backed by checkable artifacts** wherever possible (proofs, test/command results,
  decompositions, conformance results), not by prose alone;
- declare an honest **residual surface** (Trace Spec §13): the assumptions, unverified claims,
  out-of-scope items, limitations, and open questions, each with a `target` and `severity`.

## 3.2 Consumer reliances

A reviewing agent ingesting such a trace:

- **may treat a verifiable artifact as checkable** — and should re-check the consequential ones
  rather than trust them;
- **must not treat an unbacked claim as established** — a rationale or summary is *attention
  routing*, not evidence;
- **must treat the residual surface as the producer's declared gaps**, and **must treat the
  absence of residuals as itself reviewable**, not as proof of completeness.

## 3.3 The trust principle

> **Targeted verification, not trust.** The trace tells the reviewer *where to look* and *what was claimed*; the reviewer establishes *what is true*.

The value of the handoff is not that the reviewer trusts the producer — it is that the reviewer
stops re-deriving everything from the diff and instead spends its effort verifying the
consequential claims and hunting the gaps.

---

# 4. Classifying Trace Content by Checkability

The reviewer's first move is to sort the trace's content into three buckets, because each is
consumed differently:

| Bucket | Examples | How the reviewer treats it |
|---|---|---|
| **Independently checkable** | `VerificationResult` (proved/refuted), `CommandResult` (test runs), `StateSpaceAnalysisResult`, `ConformanceResult` | Evidence — but **re-verify** the consequential ones; a proof travels and re-checks. |
| **Asserted / unbacked** | `rationale`, `observation`, `outcome.summary`, free-text notes | **Attention routing only.** Tells the reviewer where the producer focused or was unsure; never counts as established. |
| **Declared negative space** | the `residuals` surface | The **review work-list** — triaged per §6. |

The single most important consequence: **a claim of "verified" with no backing checkable artifact
is treated as `Unverified`.** Prose that says "I tested this" is not a `CommandResult`.

---

# 5. The Consumption Procedure

A reviewing agent should run the following protocol over a trace. Steps are ordered; later
steps depend on earlier ones.

### Step 1 — Orient

Read `trigger` (the intent), `outcome` (the claimed result), `files_modified` (the surface), and
`trace_lineage` / `trace_links`. If this is a **successor trace** (`Supersedes`), retrieve which
residuals its predecessors left open — those are the gaps this trace was supposed to close.

### Step 2 — Verify the positive space, proportionally

Identify the **checkable artifacts** (§4) on the changed and high-stakes surface and re-check the
consequential ones, rather than re-deriving the whole trace. Re-run proofs and tests where that
is cheap. Any claim of validation with no backing artifact is downgraded to an undeclared
`Unverified` residual (Step 4).

### Step 3 — Ingest the declared negative space

Iterate `residuals` **in descending `severity`**. For each: follow `target` to locate where it
bites, read `suggested_check`, and triage it per §6. This is where the residual surface earns its
keep — the reviewer's attention goes straight to the producer's own declared weak points.

### Step 4 — Hunt the *undeclared* negative space

Compare the changed surface (`files_modified`, the diff) against what Step 2 verified and what the
residual surface declares. **Anything the change touches that is neither verified nor declared is
an undeclared residual** — the reviewer adds it (`source = ReviewerAdded`). This step is the
reason independent review exists; the declared residual surface makes it *tractable* by shrinking
the space the reviewer has to discover from scratch.

### Step 5 — Emit the verdict

Convert the triaged residuals into outputs (§7): review items, comments, residual status updates,
and an overall disposition. A successor trace is requested for the gaps that must close before
approval.

---

# 6. Residual Triage

For each residual, the action is a function of `kind` and `severity`.

**By kind:**

| Kind | Reviewer action |
|---|---|
| `Assumption` | Locate via `target`. If it underpins a high-stakes path, independently check the premise or require backing evidence. If it cannot be checked, promote to a review item (blocking when consequential). |
| `Unverified` | Re-verify if cheap (run the `suggested_check`). Otherwise promote to a review item carrying `suggested_check` as the task; block on high-stakes paths. |
| `OutOfScope` | Confirm the exclusion is acceptable for *this* change. If the diff actually depends on the excluded thing, the work is mis-scoped — escalate. |
| `Limitation` | Record it and ensure it is propagated to downstream consumers. Block only if the change will be used outside the limitation's stated bounds. |
| `OpenQuestion` | Route to a **human**. Open questions are decisions, not verifications; do not auto-approve over one. |

**Severity overlay** (applied on top of kind):

- `Critical` / `High` + `ResidualOpen` → **blocking** by default;
- `Medium` → review item; blocking only on a high-stakes path;
- `Low` / `Info` → comment or acknowledge.

---

# 7. What the Reviewer Emits

The reviewing agent writes back into the trace's collaboration surface (Trace Spec §14) and the
review case:

- **review items** (§14.3) — for residuals that must be tracked; `target` carried through, `blocking` set per §6;
- **comments** (§14.2) — targeted feedback on specific actions, artifacts, or residuals;
- **residual status updates** — `ResidualAcknowledged` for accepted known gaps, `ResidualWaived` for explicit, auditable acceptance;
- **a successor-trace request** — the set of `residual_id`s that must be closed, to be addressed by a `Supersedes` successor (traces are immutable);
- **an overall disposition** — `approve`, `request-changes`, or `escalate-to-human` — which can drive the trace status (`approved` / `needs_attention`) and the review case.

The disposition rule of thumb:

> Approve only when no `ResidualOpen` residual is blocking, every consequential checkable claim has been **re-verified**, and Step 4 surfaced no undeclared high-severity gap.

---

# 8. Recommended Reviewing-Agent Procedure (prompt-ready)

A compact operational form of §5–§7, suitable as the core of a reviewing-agent system prompt:

```
You are reviewing a change by reading its reasoning trace, not just its diff.

1. Orient: read the intent (trigger), the claimed result (outcome), the changed files,
   and the lineage. If this supersedes an earlier trace, note which gaps it was meant to close.
2. Trust nothing unbacked: treat proofs, test results, and analyses as evidence ONLY after
   re-checking the consequential ones. Treat rationale and summaries as hints about where to
   look, never as proof. A "verified" claim with no artifact behind it is unverified.
3. Work the residual surface, highest severity first: for each declared gap, jump to its
   target, run its suggested check if cheap, and decide — verify, block, or route to a human
   (open questions are human decisions).
4. Hunt undeclared gaps: anything the change touches that is neither verified nor declared is a
   gap YOU must raise.
5. Emit: file review items (block the critical ones), update residual status, request a
   successor trace for what must close, and give a verdict. Approve only when nothing blocking
   remains open, the consequential claims re-verified, and you found no undeclared high-severity gap.
```

---

# 9. Anti-Patterns

- **Trusting the producer's claims.** A trace is not a testimonial; re-verify the consequential, checkable claims.
- **Approving on an empty residual surface.** No declared gaps is not proof of no gaps — Step 4 is mandatory.
- **Treating prose as evidence.** Rationale routes attention; only checkable artifacts establish facts.
- **Auto-resolving open questions.** `OpenQuestion` residuals are decisions for a human, not checks for an agent.
- **Mutating the trace to "fix" a gap.** Traces are immutable; gaps close in a successor trace via `Supersedes`.

---

# 10. Summary

The residual surface turns the coding-agent → reviewing-agent handoff from a blind re-derivation
into a bounded, evidence-grounded protocol: the producer declares its gaps; the consumer
re-verifies the consequential claims, triages the declared gaps by severity, and — crucially —
hunts the undeclared ones. The reviewer trusts nothing it cannot check, and the trace's job is to
make checking *targeted* instead of exhaustive.

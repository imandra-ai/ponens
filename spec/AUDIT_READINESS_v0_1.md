# Audit Readiness

## Header

**Version:** 0.1
**Status:** Draft
**Purpose:** State plainly what makes a ponens trace credible to an **auditor or regulator**, which of
those properties the specs already deliver, and the honest gap-list from *"presentable"* to *"relied
upon as evidence."* A roadmap and a scoping discipline, not a compliance claim.

---

## 1. The core claim: evidence, not attestation

Most "AI governance" tooling produces **attestation** — checklists and self-reported claims. A ponens
trace is **evidence**: an immutable, lineage-linked record where every "done" resolves to a specific
artifact ([`TRACE_SPEC_v1_9.md`](TRACE_SPEC_v1_9.md) §18) and every verdict comes from a formal engine
an auditor can **re-run** (§12). That is the difference between *"we assert we did X"* and *"here is X,
here is the proof, re-check it yourself."* Everything below follows from holding that line: the trace's
value is that it is checkable, not that it is signed off.

---

## 2. Credibility axes — what an auditor probes, and where the specs answer

| What an auditor asks | ponens answer | Where |
|---|---|---|
| Is the record **unaltered**? | Canonical `content_hash` (sha256); 1:1 bind to a git commit via git notes | `CLI_SYNC_MODEL_v0_1.md`; `ponens bind` |
| Who **approved** it, provably, and **when**? | Cryptographic signatures over `content_hash` (`ponens trace sign`), verified with the public key + an allowed-signers roster; optional **RFC-3161 trusted timestamp** (`--tsa`) for a TSA-attested "when" | `ponens trace sign`/`verify`; `signing.py` |
| Is "done" **real or self-reported**? | Acceptance resolves *deterministically from evidence* (typed artifact in the component's lineage), never from prose | TRACE §18.2–18.3 |
| Are the **gaps disclosed**? | The residual surface — assumptions, unverified, out-of-scope, limitations, open questions | TRACE §13 |
| Is there **counter-evidence**? | First-class `Defeater` residuals (rebuts / undermines / undercuts) that *block* a contested claim | TRACE §13, §18.2 |
| Is the evidence **current**? | Derived freshness (`Fresh`/`Stale`/`Detached`) from a dependency-closure fingerprint; a goal never resolves done over stale/detached evidence | TRACE §18.3 |
| Can a third party **re-check** it? | Reproducibility (entrypoints, environments, replay) + re-runnable formal verdicts | TRACE §12; `ponens trace reproduce` |
| Does it speak a **standard vocabulary**? | Export to W3C PROV (Entity/Activity/Agent + derivation) | `PROV_INTERCHANGE_v0_1.md` |
| Does it map to a **named regime**? | Policy packs encoding DO-178C / MISRA / NIST AI RMF / MiFID / IOSCO / … as machine-checkable rules | `POLICY_SPEC_v0_2.md`, the `*_PACK.md` files |
| Was there **independent review**? | Review-case: comments, review items, dispositions, snapshots, and third-party goal *certification* (a non-doer) | `REVIEW_CASE_SPEC_v0_2.md`; `ponens trace goal certify --by reviewer` |

This is already ahead of the checklist category: the record is grounded, discloses its own negative
space, keeps its evidence current, and is re-checkable in a standard vocabulary.

---

## 3. The gap-list: from "presentable" to "relied upon"

To move from *"we can show this to an auditor"* to *"an auditor/regulator will rely on it as
evidence,"* ranked by impact:

1. **Integrity → non-repudiation.** `content_hash` proves *unaltered*; **cryptographic signing** now
   adds *by whom*. `ponens trace sign` signs the `content_hash` with an SSH private key (an audit
   sign-off carries `--role`/`--disposition`); `ponens trace verify` checks each signature with the
   public key and reports **valid** (key in the allowed-signers roster) / **untrusted** (crypto-valid,
   unknown key) / **invalid** / **tampered** — gating on failure (`--require-trusted` to require the
   roster). Signatures live in `signatures[]`, excluded from `content_hash`, so parties co-sign the
   same content. **Trusted timestamp**: `sign --tsa <url>` attaches an **RFC-3161** timestamp over the
   signature (a TSA-signed "existed by <time>"); `verify --tsa-ca <cert>` checks it **offline** against
   the TSA certificate — so *when* is TSA-attested, not machine-clock-asserted. *Status: **shipped** —
   SSH signatures + RFC-3161 timestamps, both offline-verifiable. Follow-on: GPG / sigstore backends
   alongside SSH; a rekor transparency-log option.*
2. **Tool trust / qualification.** A verdict is only as trustworthy as the engine + checker that
   produced it. For certification *credit* (DO-178C-class), the verification tool itself must be
   qualified; for finance / AI-governance (MiFID, NIST AI RMF), reproducibility usually suffices.
   Record engine + `engine_version` on every result (already carried in the reasoning fingerprint,
   §10.4a) so the toolchain is auditable. *Status: engine/version recorded; formal qualification out
   of scope.*
3. **Validated, maintained framework mappings.** The policy packs must be authored/reviewed against
   the actual regulatory text (ideally by someone credentialed) and **versioned as the standard
   changes**, with provenance. *Status: `POLICY_SOURCES_v0_1.md` supports provenance; packs are
   self-authored drafts, not yet auditor-grade.*
4. **Named human accountability.** Regulators want an accountable person, not an agent. The review-case
   already models approvals/certification by a named non-doer — make a **human sign-off a required
   gate** at the compliance boundary (snapshot `signoff_state`). *Status: modelled; make it mandatory
   in the governing profile.*
5. **Claim-scoping discipline.** Be precise about *what* is certified: **proved ≠ fidelity-checked ≠
   certified.** Never let "proved" read as "the system is correct." The trace already separates
   *proved* (engine verdict), *fidelity/conformance* (model ↔ code), and *certified* (a reviewer
   confirmed the criteria were right); the discipline is to **never collapse them** in any report or
   summary. *Status: separable in the model; enforce in reporting.*

---

## 4. Positioning

The defensible claim is narrow and strong: *"an immutable, standards-aligned, formally-grounded record
of what an AI agent did — what it changed, what it verified, what it assumed, and what remains
contested — that an independent party can re-check."* This is the **work-auditor** framing. Do **not**
overreach into "we certify the AI is correct": the moat is the *auditable record + re-checkable
verdicts*, and the nearer market is finance / AI-governance (where reproducibility, not full tool
qualification, is the bar) rather than safety-certification credit.

---

## 5. References

- Integrity / bind: [`CLI_SYNC_MODEL_v0_1.md`](CLI_SYNC_MODEL_v0_1.md)
- Grounded resolution, freshness, defeaters: [`TRACE_SPEC_v1_9.md`](TRACE_SPEC_v1_9.md) §12, §13, §18
- Policy / governance: [`POLICY_SPEC_v0_2.md`](POLICY_SPEC_v0_2.md), [`POLICY_SOURCES_v0_1.md`](POLICY_SOURCES_v0_1.md), the `*_PACK.md` files
- Review / certification: [`REVIEW_CASE_SPEC_v0_2.md`](REVIEW_CASE_SPEC_v0_2.md), [`GOAL_FAITHFULNESS_v0_1.md`](GOAL_FAITHFULNESS_v0_1.md)
- Interoperability: [`PROV_INTERCHANGE_v0_1.md`](PROV_INTERCHANGE_v0_1.md)
- Prior-art rationale: [`PRIOR_ART_ALIGNMENT_v0_1.md`](PRIOR_ART_ALIGNMENT_v0_1.md)

# Review Case Specification

## Version

**Version:** 0.2  
**Status:** Draft  
**Format:** Canonical typed specification with OCaml / IML-oriented model and JSON/Pydantic projection notes  
**Positioning:** Companion specification to the Trace Specification and Policy Specification

---

# 1. Purpose

A **review case** is the higher-level workflow object that governs a change, investigation, or decision across one or more traces.

A trace captures **one concrete run** of an agent or workflow.  
A review case captures:

- the **original problem** being solved
- the **current workflow state**
- the **active trace** under review
- the **chain of prior traces**
- **review items, comments, approvals, and audit state**
- whether current work remains **explained by the original problem formulation**

The review case is therefore the **governance and workflow container** above individual traces.

---

# 2. Relationship to the Trace and Policy Specifications

This specification is intended to be used together with:

- the **trace specification**
- the **policy specification**

The split is:

- the **trace specification** defines the object model and semantics of a single trace
- the **policy specification** defines policies as formulas interpreted over traces and, optionally, review-case context
- the **review case specification** defines the workflow object that manages one or more traces over time

A review case should never duplicate the full internal structure of a trace.  
Instead, it should reference traces by identity and summarize their role in the overall workflow.

A good one-line summary is:

> **A trace shows one run; a review case shows where the overall change stands.**

---

# 3. Scope

This specification focuses on:

- a **single review case**
- its relationship to **multiple traces**
- its workflow, approval, audit, explanation, and synchronization state
- its role as the unit of governed solving in local-first and hosted workflows

This specification does **not** define:
- the full internal structure of traces
- the full syntax of the policy DSL
- the full schema of snapshots beyond case-level references

Those are defined in companion specifications.

---

# 4. Design Principles

The review case model is built around seven core principles:

1. **Problem-centered governance**  
   Every meaningful change should be rooted in an explicit problem statement.

2. **Multi-trace evolution**  
   A review case may contain multiple traces over time as work is refined, rerun, repaired, or rechecked.

3. **One usually active trace**  
   A review case should normally designate one active trace representing the best current governed state.

4. **Workflow-level control**  
   Review, approval, audit, and explanation state belong at the review-case layer, not only at the trace layer.

5. **Local-first operation**  
   Review cases should work locally without a hosted service.

6. **Remote synchronization as projection**  
   Hosted systems, sync state, PR linkage, and collaboration are extensions of the same canonical model.

7. **Canonical typed semantics first**  
   The authoritative model is a strict typed model suitable for OCaml / IML reasoning; JSON/Pydantic is derived from it.

---

# 5. What a Review Case Is Semantically

A review case is rooted in an explicit problem statement and evolves through a chain of traces.

Semantically, a review case contains:

- a **problem formulation**
- a set of **linked traces**
- one usually **active trace**
- review and approval metadata
- snapshot and audit metadata
- workflow state over time
- optional repository / task / PR anchoring
- optional remote publication and sync metadata

## 5.1 Governing principle

The core invariant is:

> **All meaningful current modifications should retrace to the original problem formulation through the review-case graph, and all steps used to reach them should remain within policy.**

This makes the review case more than a ticket or container.  
It is a **governed solving context**.

## 5.2 Formal role

Informally:
- traces are execution records
- policies are constraints over those records
- review cases organize governed work across traces over time

More formally:
- let `C` be the set of valid review cases
- let `T` be the set of valid traces
- each review case `c ∈ C` references one or more traces `τ ∈ T`
- a review case maintains workflow state over those traces
- trace-level and case-level policies may be evaluated relative to that structure

A review case is therefore a **workflow-level semantic object** built over trace-level semantic objects.

---

# 6. Canonical Model vs Interchange Model

This specification distinguishes between two layers:

## 6.1 Canonical model

The **canonical model** is the semantic source of truth.

It is:
- strongly typed
- algebraic where appropriate
- suitable for OCaml / IML modeling
- the model against which workflow invariants are defined

## 6.2 Interchange model

The **interchange model** is a JSON-friendly representation derived from the canonical model.

It exists to support:
- persistence
- transport
- API boundaries
- UI/TUI integration
- Pydantic model generation

## 6.3 Design rule

> **Specify the strongest semantic model first; derive the wire format from it, not the other way around.**

The canonical model is authoritative.  
JSON and Pydantic schemas are projections of that model.

---

# 7. Canonical Top-Level Structure

The canonical review case is a typed record.

```ocaml
type review_case =
  { review_case_id : string
  ; spec_version : string
  ; title : string
  ; description : string option
  ; status : review_case_status
  ; audit_status : audit_status option
  ; problem_statement : problem_statement
  ; acceptance_criteria : string list
  ; active_trace_id : string option
  ; trace_ids : string list
  ; trace_links : review_case_trace_link list
  ; latest_snapshot_id : string option
  ; snapshot_ids : string list
  ; comments : case_comment list
  ; review_items : case_review_item list
  ; approvals : approval_record list
  ; audits : audit_record list
  ; anchor : case_anchor option
  ; repo_context : case_repo_context option
  ; explanation_status : explanation_status option
  ; summary : review_case_summary option
  ; remote : remote_linkage option
  ; sync_state : sync_state option
  ; created_at : string
  ; updated_at : string
  }
```

Canonical list fields are normalized as empty lists rather than omitted fields.

---

# 8. Problem Statement

A review case must be rooted in an explicit problem statement.

## 8.1 Canonical model

```ocaml
type problem_statement =
  { problem_id : string
  ; title : string
  ; description : string
  ; acceptance_criteria : string list
  ; scope_hints : string list
  ; created_by : string option
  ; created_at : string option
  }
```

## 8.2 Semantics

The problem statement is the root of the governed solving process.

It should describe:
- what is being changed, analyzed, or answered
- what counts as success
- any critical scope restrictions or explicit non-goals

The problem statement is semantically important because:
- traces should be explainable relative to it
- policy requirements may depend on it
- approvals and auditability are judged relative to it

---

# 9. Workflow Status

## 9.1 Review case status

```ocaml
type review_case_status =
  | Draft
  | UnderReview
  | ChangesRequired
  | ReadyForApproval
  | Approved
  | Rejected
  | Archived
```

### Meanings

- `Draft` — case created but not yet actively reviewed
- `UnderReview` — active review is in progress
- `ChangesRequired` — blockers or findings require another trace or revision
- `ReadyForApproval` — current active trace satisfies review requirements pending approval
- `Approved` — case approved
- `Rejected` — case explicitly rejected
- `Archived` — case closed and no longer active

## 9.2 Audit status

```ocaml
type audit_status =
  | NotAuditable
  | Auditable
  | AuditPending
  | Audited
  | AuditFailed
```

### Meanings

- `NotAuditable` — insufficient evidence to support audit
- `Auditable` — enough evidence exists for audit/replay
- `AuditPending` — audit requested but not completed
- `Audited` — audit completed successfully
- `AuditFailed` — audit completed and failed

---

# 10. Trace Membership and Active Trace

A review case may contain multiple traces over time.

## 10.1 Core rules

1. A review case must contain at least one trace once active work begins.
2. A review case may contain multiple traces representing reruns, fixes, rechecks, or branch variants.
3. A review case should usually have **at most one active trace** at a time.
4. The active trace is the trace that currently represents the best known governed solution state for the review case.

## 10.2 Canonical trace link summary

```ocaml
type review_case_trace_relationship =
  | RcSupersedes
  | RcReruns
  | RcDerivedFrom
  | RcPolicyRecheckOf
  | RcConformanceRecheckOf
  | RcForkedFrom
  | RcRelatedTo

type review_case_trace_link =
  { from_trace_id : string
  ; to_trace_id : string
  ; relationship : review_case_trace_relationship
  ; note : string option
  }
```

These may mirror or summarize trace-level links, but the case-level view exists for workflow convenience.

---

# 11. Snapshots

A review case may include snapshots that freeze evidence at important points.

## 11.1 Purpose

Snapshots are useful for:
- approval candidates
- audit handoff
- reproducibility checkpoints
- significant governance milestones

## 11.2 Canonical representation

This specification assumes snapshots are separate objects, but the review case tracks:
- `latest_snapshot_id`
- `snapshot_ids`

A future dedicated snapshot specification may define their full internal structure.

---

# 12. Review and Collaboration Objects

A review case may carry comments and review items at the case level.

These are distinct from trace-level comments and review items because they apply to the **overall governed workflow**, not necessarily to one trace object.

## 12.1 Comment targets

```ocaml
type case_target_type =
  | ReviewCaseTarget
  | TraceTarget
  | SnapshotTarget
  | ApprovalTarget
  | AuditTarget

type case_target_ref =
  { target_type : case_target_type
  ; target_id : string option
  }
```

## 12.2 Case comments

```ocaml
type case_comment_status =
  | CommentOpen
  | CommentResolved

type case_comment =
  { comment_id : string
  ; author : string
  ; created_at : string
  ; body : string
  ; target : case_target_ref
  ; thread_parent_id : string option
  ; status : case_comment_status option
  ; resolved_at : string option
  ; tags : string list
  }
```

## 12.3 Case review items

```ocaml
type case_review_item_status =
  | ItemOpen
  | ItemAcknowledged
  | ItemResolved
  | ItemWaived

type case_review_item =
  { review_item_id : string
  ; author : string
  ; created_at : string
  ; title : string
  ; body : string option
  ; target : case_target_ref
  ; assignee : string option
  ; status : case_review_item_status
  ; blocking : bool option
  ; acknowledged_at : string option
  ; acknowledged_by : string option
  ; resolved_at : string option
  ; resolved_by : string option
  ; resolution_note : string option
  ; tags : string list
  }
```

## 12.4 Semantics

- `blocking = true` means the review case should not progress to approval until the item is resolved or waived.
- Review items may apply to the case as a whole or to a particular trace/snapshot/approval.
- Case-level review items should be used for workflow requirements, not low-level trace commentary.

---

# 13. Approval and Audit Records

## 13.1 Approval records

```ocaml
type approval_status =
  | ApprovalApproved
  | ApprovalRejected
  | ApprovalRescinded

type approval_target_type =
  | ApprovalReviewCaseTarget
  | ApprovalSnapshotTarget
  | ApprovalTraceTarget

type approval_record =
  { approval_id : string
  ; approved_by : string
  ; approved_at : string
  ; status : approval_status
  ; target_type : approval_target_type
  ; target_id : string
  ; note : string option
  }
```

## 13.2 Audit records

```ocaml
type audit_record_status =
  | AuditPassed
  | AuditFailed
  | AuditPartial

type audit_target_type =
  | AuditReviewCaseTarget
  | AuditSnapshotTarget
  | AuditTraceTarget

type audit_record =
  { audit_id : string
  ; audited_by : string
  ; audited_at : string
  ; status : audit_record_status
  ; target_type : audit_target_type
  ; target_id : string
  ; note : string option
  ; evidence_snapshot_id : string option
  }
```

---

# 14. Anchoring to External Workflow Objects

A review case may be anchored to external workflow context such as a repository branch, PR, task, or ticket.

## 14.1 Case anchor

```ocaml
type case_anchor_type =
  | PrRef
  | TaskRef
  | BranchRef
  | TicketRef
  | Standalone

type case_anchor =
  { typ : case_anchor_type
  ; key : string
  ; provider : string option
  ; url : string option
  }
```

## 14.2 Repository context

```ocaml
type case_repo_context =
  { vcs : string option
  ; repo_name : string option
  ; repo_root : string option
  ; base_branch : string option
  ; head_branch : string option
  ; head_commit_sha : string option
  ; base_commit_sha : string option
  ; merge_base_sha : string option
  }
```

## 14.3 Semantics

The anchor identifies the external object this case corresponds to.  
The repo context identifies the codebase context within which traces are being generated and reviewed.

A review case may exist without any external anchor.

---

# 15. Explanation Status

One of the key roles of a review case is to track whether the current work is still explained by the original problem statement.

## 15.1 Canonical model

```ocaml
type explanation_state =
  | Explained
  | PartiallyExplained
  | Stale
  | Diverged
  | NoReviewCase

type explanation_status =
  { status : explanation_state
  ; trace_id : string option
  ; head_commit_sha : string option
  ; trace_head_commit_sha : string option
  ; explained_files : string list
  ; unexplained_files : string list
  ; note : string option
  }
```

## 15.2 Meanings

- `Explained` — current code or workflow state remains justified by the case and active trace
- `PartiallyExplained` — some current changes are justified, some are not
- `Stale` — the active trace explains an older state but current work has moved on
- `Diverged` — current work no longer cleanly belongs to the same governed solving effort
- `NoReviewCase` — no case exists for the current workflow context

---

# 16. Summary Fields

A review case may include a summary cache for fast UI / CLI display.

## 16.1 Canonical model

```ocaml
type review_case_summary =
  { counterexample_count : int option
  ; proof_count : int option
  ; state_space_analysis_count : int option
  ; generated_test_count : int option
  ; policy_status : string option
  ; open_review_item_count : int option
  ; open_blocking_review_item_count : int option
  ; approval_ready : bool option
  }
```

These fields are convenience summaries, not the authoritative source of truth.

---

# 17. Local-First and Remote-Connected Modes

A review case is designed to support both:

- **local-first workflows**
- **remote/shared workflows**

## 17.1 Remote linkage

```ocaml
type remote_linkage =
  { remote_name : string option
  ; remote_review_case_id : string option
  ; published : bool option
  ; remote_url : string option
  ; last_pushed_at : string option
  ; last_pulled_at : string option
  }
```

## 17.2 Sync state

```ocaml
type review_case_sync_status =
  | LocalOnly
  | AheadLocal
  | AheadRemote
  | SyncDiverged
  | InSync

type sync_state =
  { review_case_sync_status : review_case_sync_status option
  ; active_trace_sync_status : string option
  ; snapshot_sync_status : string option
  ; note : string option
  }
```

## 17.3 Semantics

A review case may exist entirely locally.  
Publishing or syncing does not change its conceptual role; it only changes storage and collaboration mode.

---

# 18. Formal View

The review case sits above traces and may be referenced by policies.

A compact formal framing is:

- let `C` be the set of valid review cases
- let `T` be the set of valid traces
- each `c ∈ C` contains identifiers of one or more `τ ∈ T`
- a review case maintains workflow state across those traces
- policies may constrain:
  - a single trace
  - the active trace of a review case
  - or review-case-level workflow conditions

This makes the review case the natural semantic object for:
- approvals
- blockers
- audit state
- local/remote synchronization
- explanation of current work relative to the original problem statement

---

# 19. IML-Oriented View

The canonical review-case model should be representable in IML as algebraic datatypes and records.

A sketch of the main shape in IML-style notation would be:

```ocaml
type review_case_status =
  | Draft
  | UnderReview
  | ChangesRequired
  | ReadyForApproval
  | Approved
  | Rejected
  | Archived

type audit_status =
  | NotAuditable
  | Auditable
  | AuditPending
  | Audited
  | AuditFailed

type problem_statement =
  { problem_id : string
  ; title : string
  ; description : string
  ; acceptance_criteria : string list
  ; scope_hints : string list
  ; created_by : string option
  ; created_at : string option
  }

type review_case_trace_relationship =
  | RcSupersedes
  | RcReruns
  | RcDerivedFrom
  | RcPolicyRecheckOf
  | RcConformanceRecheckOf
  | RcForkedFrom
  | RcRelatedTo

type review_case_trace_link =
  { from_trace_id : string
  ; to_trace_id : string
  ; relationship : review_case_trace_relationship
  ; note : string option
  }

type explanation_state =
  | Explained
  | PartiallyExplained
  | Stale
  | Diverged
  | NoReviewCase

type explanation_status =
  { status : explanation_state
  ; trace_id : string option
  ; head_commit_sha : string option
  ; trace_head_commit_sha : string option
  ; explained_files : string list
  ; unexplained_files : string list
  ; note : string option
  }

type review_case =
  { review_case_id : string
  ; spec_version : string
  ; title : string
  ; description : string option
  ; status : review_case_status
  ; audit_status : audit_status option
  ; problem_statement : problem_statement
  ; acceptance_criteria : string list
  ; active_trace_id : string option
  ; trace_ids : string list
  ; trace_links : review_case_trace_link list
  ; latest_snapshot_id : string option
  ; snapshot_ids : string list
  ; comments : case_comment list
  ; review_items : case_review_item list
  ; approvals : approval_record list
  ; audits : audit_record list
  ; anchor : case_anchor option
  ; repo_context : case_repo_context option
  ; explanation_status : explanation_status option
  ; summary : review_case_summary option
  ; remote : remote_linkage option
  ; sync_state : sync_state option
  ; created_at : string
  ; updated_at : string
  }
```

This defines the **canonical abstract structure**. It does not itself define the operational algorithms for explanation checking, sync resolution, or approval gating.

---

# 20. Invariants and Recommended Rules

The following invariants are recommended for valid review cases:

1. If `status <> Draft`, then `trace_ids` should not be empty.
2. `active_trace_id`, when present, should be a member of `trace_ids`.
3. There should usually be **at most one active trace**.
4. `latest_snapshot_id`, when present, should be a member of `snapshot_ids`.
5. Blocking review items should normally prevent transition to `ReadyForApproval` unless resolved or waived.
6. `Approved` status should normally imply there is sufficient evidence to justify `Auditable` or `Audited`.
7. Explanation status should be derived from the active trace and current workspace/repo context, not edited arbitrarily.

These are normative intent rules even if some implementations choose to enforce only a subset mechanically.

---

# 21. Interchange Projection Notes

The canonical model above is authoritative.

For interchange, a JSON/Pydantic projection may be derived from it.

## 21.1 General rule

Each closed algebraic variant must be serialized using an explicit discriminator or a stable string form.

Examples:
- `status`
- `audit_status`
- `relationship`
- `target_type`
- `anchor.type`

## 21.2 Review case projection

A strict value like:

```ocaml
{ review_case_id = "rc_001"; status = UnderReview; ... }
```

may be projected into JSON as:

```json
{
  "review_case_id": "rc_001",
  "spec_version": "0.2",
  "title": "FIX session handling update",
  "status": "under_review",
  "audit_status": "auditable",
  "problem_statement": { "...": "..." },
  "active_trace_id": "trace-fix-002",
  "trace_ids": ["trace-fix-001", "trace-fix-002"],
  "trace_links": [ { "...": "..." } ],
  "snapshot_ids": [],
  "comments": [],
  "review_items": [],
  "approvals": [],
  "audits": [],
  "created_at": "2026-04-20T10:00:00Z",
  "updated_at": "2026-04-20T12:05:00Z"
}
```

## 21.3 Pydantic generation notes

Reference Pydantic models should be generated from the strict model as:
- standard `BaseModel` records
- string-discriminated enums for statuses and kinds
- nested models for problem statements, review items, approvals, audit records, anchors, repo context, explanation status, and sync state

Decoding must reconstruct the canonical strict model and reject structurally invalid combinations.

## 21.4 Serialization boundary rule

> **JSON and Pydantic are interchange formats. The strict typed model remains the semantic source of truth.**

---

# 22. Recommended Implementation Strategy

## 22.1 Internal model
Use the canonical review-case types in:
- OCaml
- IML
- workflow reasoning tooling
- TUI/CLI state machines
- hosted governance services

## 22.2 Serialization layer
Generate:
- JSON schema
- Pydantic models
- encoders/decoders

from the strict model, not the reverse.

## 22.3 Validation strategy
Validation should occur at two levels:

1. **wire validation**  
   ensure JSON/Pydantic payloads are structurally well-formed

2. **semantic decoding**  
   ensure the payload can inhabit the canonical review-case model

## 22.4 Derived-state strategy
Some fields are naturally primary; others are derived.

Usually primary:
- problem statement
- trace membership
- review items
- approvals
- audits
- remote linkage

Usually derived or recomputable:
- explanation status
- summary fields
- some sync-state summaries

Implementations should clearly distinguish source-of-truth fields from derived caches.

---

# 23. Minimal Example

```json
{
  "review_case_id": "rc_local_001",
  "spec_version": "0.2",
  "title": "FIX session handling update for trading gateway",
  "description": "Governed review case for a FIX connection change.",
  "status": "under_review",
  "audit_status": "auditable",

  "problem_statement": {
    "problem_id": "prob_001",
    "title": "Modify FIX session handling",
    "description": "Update the FIX connection flow to support the revised session lifecycle and preserve protocol invariants.",
    "acceptance_criteria": [
      "updated FIX session flow conforms to approved reference model",
      "critical protocol invariants remain valid",
      "results are reproducible and audit-ready"
    ]
  },

  "acceptance_criteria": [
    "updated FIX session flow conforms to approved reference model",
    "critical protocol invariants remain valid",
    "results are reproducible and audit-ready"
  ],

  "active_trace_id": "trace-fix-002",
  "trace_ids": ["trace-fix-001", "trace-fix-002"],

  "trace_links": [
    {
      "from_trace_id": "trace-fix-002",
      "to_trace_id": "trace-fix-001",
      "relationship": "supersedes",
      "note": "Second run after fixing conformance mismatch"
    }
  ],

  "review_items": [
    {
      "review_item_id": "r1",
      "author": "reviewer@example.com",
      "created_at": "2026-04-20T12:00:00Z",
      "title": "Rerun under stricter FIX policy pack",
      "target_type": "review_case",
      "assignee": "denis",
      "status": "open",
      "blocking": true
    }
  ],

  "anchor": {
    "type": "pr_ref",
    "key": "381",
    "provider": "github"
  },

  "repo_context": {
    "vcs": "git",
    "repo_name": "trading-gateway",
    "base_branch": "main",
    "head_branch": "feature/fix-session-update"
  },

  "explanation_status": {
    "status": "partially_explained",
    "trace_id": "trace-fix-002",
    "explained_files": ["fix/session.py"],
    "unexplained_files": ["gateway/router.py"],
    "note": "Router change is not yet justified by the active trace"
  },

  "summary": {
    "counterexample_count": 1,
    "proof_count": 4,
    "state_space_analysis_count": 1,
    "generated_test_count": 12,
    "policy_status": "passed",
    "open_review_item_count": 1,
    "open_blocking_review_item_count": 1,
    "approval_ready": false
  },

  "remote": {
    "remote_name": "origin",
    "remote_review_case_id": "rc_381",
    "published": true
  },

  "sync_state": {
    "review_case_sync_status": "ahead_local"
  },

  "created_at": "2026-04-20T10:00:00Z",
  "updated_at": "2026-04-20T12:05:00Z"
}
```

---

# 24. Intended Outcomes

The intended outcomes of this review-case specification are:

- **problem-centered governance**
- **workflow-level control above traces**
- **multi-trace iteration**
- **local-first usability**
- **enterprise collaboration**
- **stronger audit and approval semantics**
- **explicit explainability of current work relative to the original problem**
- **OCaml / IML-friendly semantic modeling**
- **clean projection to JSON and Pydantic**

---

# 25. Summary

The clean conceptual distinction is:

- a **trace** is a typed execution structure with formal semantics
- a **policy** is a formula interpreted over traces (and optionally review-case context)
- a **review case** is the workflow object that governs one or more traces over time

Or, in one sentence:

> **Traces capture runs, policies constrain them, and review cases govern the broader solving process over time.**

# Goal Faithfulness — the definition of done, done right (v0.1)

**Status:** design spec. Refines [Trace Spec §18 (Goals & Acceptance)](TRACE_SPEC_v1_12.md) — additive,
backward-compatible. Driven by the concrete goal use case in CodeLogician Desktop (the
`declare_goal` tool → per-session active goal → `ponens trace enrich` resolution loop).

## 1. Motivation — the unguarded seam

§18 makes a goal's *acceptance* rigorous: each acceptance item **binds** to real evidence (a
`Diff`, a `VerificationResult`, a `policy_evaluation`, a residual) and **resolves** deterministically,
so progress is grounded, not self-reported. That is airtight for one question and silent on another:

> Grounding proves **"is this criterion satisfied?"**. It says nothing about **"is this the right
> criterion?"**

In the real workflow the **same agent authors the definition of done and then meets it**, and reports
success — a textbook **principal–agent / specification-gaming** setup. An agent can be perfectly
honest at resolution (never fakes an artifact) and still "succeed" by choosing a **weak or incomplete**
definition of done. The entire edifice of §18 sits downstream of an unguarded seam:

```
  user intent  ──(agent formalizes)──▶  acceptance items  ──(resolves from evidence)──▶  "done"
       ▲                                       ▲                                            ▲
   human, loose                         agent-authored                              §18: rigorous
   (what I meant)                       (the spec)                                   (grounded)
                                        └──────────── THE SEAM (unguarded) ──────────┘
```

This is the formal-methods **"wrong spec / vacuous proof"** problem: proving a theorem is mechanical;
*stating the theorem you actually care about* is the hard part. Acceptance items **are** the spec, and
"you proved it, but is it the right property?" applies verbatim.

## 2. The core distinction: *right* vs *met*

Faithfulness cannot be decided mechanically — whether a formal acceptance faithfully captures an
informal intent is the **formalization gap**, and "intent" lives in a human's head. So this spec does
not try to *verify* faithfulness. It makes the seam **visible, reviewed by a different principal,
coverage-checked, and hard to retrofit** (evidence rigor is the [governed axis](GOAL_CONTRACT_v0_2.md),
not a faithfulness signal) — by separating two questions the current model conflates:

| Question | Mechanism | Principal | Status |
| --- | --- | --- | --- |
| Is the definition of done **met**? | resolution (§18) | (the doer's evidence) | exists, deterministic |
| Is the definition of done **right**? | **criteria review** (this spec) | a party **≠ the doer** | new |

The single normative rule of this spec:

> **The party that meets a goal must not be the sole party that decides its definition of done.**

## 3. Faithfulness failure modes

| Failure | What it looks like | Defense (§ below) |
| --- | --- | --- |
| **Incomplete** | a clause of the intent has no acceptance item ("3DS *and* 2-approval"; acceptance covers only 3DS → all green, intent unmet) | §5 coverage (`covers` + critic) |
| **Weak evidence** | a `Diff` where a proof was needed ("add 2-approval" backed only by "an edit landed") | the [governed axis](GOAL_CONTRACT_v0_2.md) — a policy, not faithfulness (§6 superseded) |
| **Vacuous** | a `Property` proved but trivially true (holds for *any* implementation) | §5 criteria review + refutation-bite |
| **Adjacent** | proves something near but not the intent ("amount ≥ 0" when the user meant "captured ≤ authorized") | §5 criteria approval by the intent's author |
| **Retrofitted** | acceptance authored *after* the evidence that resolves it (goalposts moved to match the work) | §7 temporal anchoring + append-only |

A criterion that **bites** is a faithful one: a `Property` that is *refuted with a counterexample* is
stronger evidence of faithfulness than a green `Change`. A goal whose every item is a green `Change`
should be treated as **more** suspect than one carrying a red `Property`.

## 4. Model additions

All additive to §18. Authorship reuses the shape of `residual_source` (§13).

```ocaml
type authorship =
  | Human          (* a person stated / approved this *)
  | Agent          (* the working agent authored it *)
  | Reviewer       (* a reviewing agent or person (≠ the doer) authored/approved it *)

(* §18 acceptance_item, extended *)
type acceptance_item =
  { acceptance_id : string
  ; kind          : acceptance_kind
  ; label         : string
  ; binding       : acceptance_binding option
  ; status        : acceptance_status option
  ; required      : bool option          (* NEW — reached = all *required* items done (desktop already ships this) *)
  ; author        : authorship option    (* NEW — who authored this criterion *)
  ; covers        : string list          (* NEW — the intent clause(s) this item addresses (§5) *)
  ; authored_at   : int option           (* NEW — ms; enables the retrofit check (§7) *)
  ; detail        : string option        (* NEW — counterexample / residual text (desktop ships this) *)
  }

(* an explicit sign-off on the DEFINITION, distinct from meeting it *)
type criteria_review =
  { reviewed_by   : authorship           (* MUST be Human or Reviewer — never the doer Agent *)
  ; at            : int
  ; verdict       : Approved | ChangesRequested
  ; note          : string option
  }

(* §18 goal, extended *)
type goal =
  { goal_id       : string
  ; intent        : string
  ; intent_author : authorship option    (* NEW — who stated the intent (usually Human) *)
  ; intent_clauses: string list          (* NEW, optional — intent split into checkable clauses (§5) *)
  ; scope         : string list
  ; acceptance    : acceptance_item list
  ; criteria_review : criteria_review option   (* NEW — the "is it right?" sign-off (§5) *)
  ; status        : goal_status option
  ; meta_action_id: string option
  }
```

Every field traces to a real need: `required` and `detail` are already in the desktop; `author` /
`intent_author` make the seam visible; `covers` / `intent_clauses` make coverage checkable;
`authored_at` enables the retrofit check; `criteria_review` is the "right" sign-off.

## 5. Coverage and criteria review (the "right" mechanism)

**`covers`.** Each acceptance item names the intent clause(s) it addresses — either a substring quote of
`intent`, or an id into the optional `intent_clauses`. This makes completeness a **checkable
projection** rather than a judgement call:

- An `intent_clauses` entry with **no** covering acceptance item → an **uncovered clause**.
- An uncovered clause surfaces as a **`GoalDerived` residual** (mirroring `PolicyDerived`, §13):
  *"intent clause ⟨X⟩ has no acceptance item"* — so the gap lands in the same negative-space surface a
  reviewer already reads.

**Criteria review.** A `criteria_review` record signs off the acceptance *set* — *"this is what done
means"* — **before** it starts counting, by a principal that is **not the doer**. Two paths, composable:

1. **Human sign-off** — the person who authored the intent confirms the agent's acceptance. The
   desktop's `sendGoalToAgent → declare_goal` two-step is exactly where this belongs (user states
   intent; agent proposes acceptance; user approves the *definition*).
2. **Reviewer critique** — a *reviewing agent* (`ponens agent --review`, a different principal than the
   doer) reads the intent and the proposed acceptance and either `Approved` or `ChangesRequested`,
   filing coverage residuals for what it flags. This is the independent-auditor pattern,
   pointed at the **criteria** instead of the execution.

`ChangesRequested` (or an *absent* review on a high-stakes goal) is itself a residual — the goal is
"met" perhaps, but not **certified right**.

## 6. Acceptance strength — SUPERSEDED by the governed axis

> **Superseded (Goal Contract v0.1).** This section originally graded evidence *strength* here and
> emitted a `weakly_specified` flag. That overlapped with policy: "is a diff enough, or do you need a
> proof?" is a **rigor** question, and rigor is the [Goal Contract](GOAL_CONTRACT_v0_2.md) **governed
> axis** (policies over the goal's cone), not a faithfulness signal. To avoid two mechanisms answering
> one question, `faithfulness_of` **no longer computes `weakly_specified`** and `certified` no longer
> depends on it. The historical design is kept below for reference.

Under the goal contract, evidence is just an artifact (met = it exists); *whether it is strong enough*
is a policy. For example, `apply_formal_methods` carries `reasoning_required_for_high_stakes` ("a
high-stakes edit must have a proof or a decomposition in its lineage") and
`refuted_results_must_be_reproved` ("a result offered as evidence must actually be proved"). A goal
whose high-stakes component rests only on a `Diff` is now caught as **ungoverned**, not *weakly
specified* — same guarantee, one mechanism.

<details><summary>Historical: the strength order this section defined</summary>

```
  Change  ≺  Gap  ≺  Obligation  ≺  Property
```
A `weakly-specified` goal was one whose high-stakes scope was backed by no `Property`/`Obligation`
item. This is now expressed as policy over lineage (above).
</details>

## 7. Temporal integrity (anti-retrofit)

Acceptance is a claim about intent; intent precedes the work. So:

- `authored_at` on each item, and the acceptance list is **append-only** (edits are new versions, not
  overwrites — consistent with the desktop's "goal is a directed, append-only record").
- **Retrofit check (derived):** an item whose `authored_at` is **later** than the timestamp of the
  evidence that resolves it is flagged — the goalpost moved to meet the ball. Surfaced as a residual.
- A `criteria_review` with `at` **after** substantial resolution is likewise weaker than one before.

## 8. Semantics summary

- **met** (unchanged, §18): a goal is *reached* when all `required` items resolve `AcceptDone`.
- **right** (new): a goal is *certified* when it carries a `criteria_review` with `verdict = Approved`
  by a non-doer principal and has **no uncovered `intent_clauses`**. (Evidence strength is no longer a
  certification condition — it is the [governed axis](GOAL_CONTRACT_v0_2.md), §6 superseded.)
- The two are **orthogonal**: a goal may be met-but-uncertified (green, but the definition was never
  reviewed) or certified-but-unmet (the right target, work in progress). The desktop should show both
  axes — never collapse "met" into "done" without "right".

## 9. Out of scope (v0.1)

- **Mechanically verifying** intent↔acceptance faithfulness (the formalization gap — undecidable).
- **Vacuity detection for properties** (mutation-style "does this property fail on a known-bad
  version?") — a valuable future strengthener of §6, but engine work beyond this spec.
- **Goal supersession / sub-goals** — the other §18 frontier; tracked separately.

"""Every state a ponens trace holds, and what is allowed to move it.

A trace is append-only in principle, but "append-only" is a property of each *transition*, not of the
file. This module is the register of them: one row per stateful thing, saying what its states are, who
moves it, and - the question that matters - whether the move is RECORDED or merely applied.

Three recording modes, in descending order of trust:

  DERIVED    Nothing transitions. The state is computed from the trace every time it is read, so it
             cannot be set, only earned. A verification verdict, a freshness outcome, an acceptance
             item's status. The strongest mode: there is nothing to forge.
  APPENDED   The transition is a decision, and the decision is itself a record - an action plus an
             artifact carrying who, why, when, and against what evidence. The prior state survives.
  APPLIED    The field is written in place and the prior value is gone. Auditable only by diffing two
             copies of the file, which assumes someone kept one.

The register exists because APPLIED rows are invisible until someone enumerates them. Two were found
this way and are now APPENDED: a residual's status (a waived gap was indistinguishable from one never
declared) and a goal's acceptance list (dropping the criteria you have not met took the shipped Stripe
demo from 88% to 100%, with `trace integrity` reporting nothing lost).

SCOPE, and the limit worth stating. This register covers state a TRACE FILE holds and the CLI moves.
It is the wrong frame for an agent: CodeLogician regenerates its trace from `.codelogician/` state on
every export rather than appending to a file, so none of the modes below reach anything its store
overwrites - whatever the store forgets is gone before the record is written. Counting rows here and
calling the result "what the agent can do" was exactly that mistake, and it hid three losses: a second
decision about a residual overwrote the first in the store; re-declaring a goal with fewer criteria
dropped them; "Clear goal" wiped the definition of done. The agent's own register is its store
(`src/core/artifacts/artifact-store.ts`), and the rule there is the same one in a different place:
the store must keep the history, because nothing downstream can reconstruct it.

`test_transitions.py` gates this file in both directions: every state type in the published spec has a
row here, and every row's claim about its recording mode is checked against what the code does.

Copyright 2026 Imandra, Inc.  SPDX-License-Identifier: Apache-2.0
"""

DERIVED, APPENDED, APPLIED = "derived", "appended", "applied"


class T:
    """One stateful thing in a trace."""

    def __init__(self, subject, spec_type, states, mode, moved_by, recorded_as=None, note=""):
        self.subject = subject          # what holds the state, in plain words
        self.spec_type = spec_type      # the spec's type name, or None when the spec has no enum
        self.states = states
        self.mode = mode
        self.moved_by = moved_by        # the command / mechanism that moves it
        self.recorded_as = recorded_as  # the artifact the transition leaves behind (APPENDED only)
        self.note = note


TRANSITIONS = [
    # ── derived: earned, not set ────────────────────────────────────────────────────────────────
    T("a property under a verification goal", "property_status",
      ("pending", "proved", "refuted", "unknown"), DERIVED,
      "the reasoner, at the moment it runs",
      note="A re-run is a NEW VerificationResult artifact, never an edit to the old verdict. The "
           "history of what was believed and when is the sequence of results."),
    T("a verification result", "verification_result_status",
      ("proved", "refuted", "sat", "unknown"), DERIVED, "the reasoner, at the moment it runs"),
    T("a conformance check", "conformance_status",
      ("passed", "failed", "partial", "unknown"), DERIVED, "the oracle, at the moment it runs"),
    T("a co-simulation", "cosimulation_status",
      ("matched", "mismatched", "partial", "error"), DERIVED, "the oracle, at the moment it runs"),
    T("a formalization", "formalization_status",
      ("transparent", "opaque", "failed"), DERIVED, "the translator, at the moment it runs"),
    T("evidence freshness", None,
      ("current", "stale", "detached", "unknown"), DERIVED,
      "`trace enrich` / `check`, from the dependency-closure fingerprint",
      note="§10.4a. Recomputed against the current code every read, so it cannot be asserted - which "
           "is why a stale proof cannot be talked back into being current."),
    T("an acceptance item", "acceptance_status",
      ("todo", "doing", "done", "blocked"), DERIVED,
      "`trace resolve` / `enrich`, from the evidence in the trace",
      note="Derived from whether the required artifact exists, roots in the component, and is "
           "uncontested. `blocked` is what an open Defeater produces (§18.2)."),
    T("a signature", "signature_status",
      ("valid", "untrusted", "invalid", "tampered"), DERIVED,
      "`trace verify`, against the roster", note="Recomputed over content_hash at verify time."),
    T("a trace's policy verdicts", None,
      ("passed", "failed", "warning", "not_applicable"), DERIVED,
      "`trace check`, by evaluating each formula over the trace"),
    T("whether a gap's closure holds", None,
      ("in force", "contested"), DERIVED,
      "an open Defeater targeting the ResidualResolution (§13.2)",
      note="A justification is a claim; the way a claim is attacked here is a defeater, not a "
           "deletion. Bounded iteration, failing AGAINST closure when it does not settle."),

    # ── appended: a decision, and the decision is a record ──────────────────────────────────────
    T("a residual", "residual_status",
      ("open", "acknowledged", "addressed", "waived"), APPENDED,
      "`trace residual resolve`", recorded_as="ResidualResolution",
      note="§13.3a. Was APPLIED until 1.14: a waived gap was indistinguishable from one never "
           "declared. The effective status is now derived from the appended decisions."),
    T("a goal's definition of done", None,
      ("as declared", "item withdrawn", "goal withdrawn", "replaced"), APPENDED,
      "`trace goal drop` / `rm` / `set --reason`", recorded_as="GoalAmendment",
      note="Was APPLIED: `acc.remove(item)`. Dropping the criteria you have not met took the Stripe "
           "demo from 88% to 100%, and integrity - which indexed only already-DONE items - reported "
           "nothing lost. The criterion is now kept verbatim in the record."),
    T("a goal's criteria review", None,
      ("unreviewed", "approved", "changes-requested"), APPENDED,
      "`trace goal certify`", recorded_as="GoalAmendment",
      note="Was APPLIED: a second review overwrote the first, so a `changes-requested` verdict could "
           "be replaced by an `approved` one with nothing to show for it."),

    # ── applied: known edits, each with a reason it is tolerable ────────────────────────────────
    T("the meta-action narrative", "meta_action_status",
      ("completed", "partial", "abandoned"), APPLIED,
      "`trace meta set` / `drop`",
      note="Tolerable because the narrative is a CURATED LAYER over the atomic actions, which stay "
           "ground truth: rewriting a title cannot change what was done, only how it is told. "
           "`trace meta drop` leaves the actions in place, ungrouped."),
    T("a goal's own status", "goal_status",
      ("scratch", "active", "done", "abandoned"), APPLIED,
      "`trace goal set`",
      note="Set at declaration and not otherwise moved by the CLI; `done` is read from progress, not "
           "asserted. Worth an amendment record if it ever becomes settable."),
    T("the trace title and outcome summary", None, ("as written",), APPLIED,
      "`trace retitle`",
      note="Prose about the trace, not a claim within it. A rewritten summary cannot make an "
           "unproved thing proved - every claim it summarises is elsewhere and typed."),

    # ── outside the trace: state a trace does not hold ──────────────────────────────────────────
    T("a review item", "review_item_status",
      ("open", "acknowledged", "resolved", "waived"), APPENDED,
      "the hub, not the CLI", recorded_as="(hub-side)",
      note="Reviewer-side (§14.3), the counterpart to a producer-side residual. Not written by an "
           "agent, so not reachable from here."),
    T("a comment", "comment_status", ("open", "resolved"), APPENDED, "the hub, not the CLI",
      recorded_as="(hub-side)"),
    T("a chain", "chain_status", ("active", "superseded", "archived"), APPENDED,
      "the hub, not the CLI", recorded_as="(hub-side)",
      note="A successor trace supersedes a predecessor (§15.1); the CLI's half of this is "
           "`trace merge`, which appends rather than rewrites."),
]


def by_mode(mode):
    return [t for t in TRANSITIONS if t.mode == mode]


def agent_reachable():
    """The rows an agent can actually move, i.e. everything the CLI drives."""
    return [t for t in TRANSITIONS if "hub" not in t.moved_by]

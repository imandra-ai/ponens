"""`ponens agent` — print the agent workflow guide.

The guide is embedded here (not a repo file) so an agent with only the CLI installed can
self-onboard: `ponens agent` prints how to produce a good trace, `ponens agent --review`
prints the reviewing-agent protocol. The fuller canonical versions live in AGENT_PROMPT.md
and REVIEW_AGENT_PROMPT.md at the repo root.
"""

GUIDE = """\
ponens — agent guide

You produce a reasoning trace: a curated, verifiable record of WHAT you built and WHY —
not a transcript replay. It has two layers, treated differently:
  - Atomic actions          ground-truth evidence (files, commands, results). NEVER rewrite them.
  - Meta-action narrative   the curated story. Seeded from raw directives ("yes", "ok fix it") —
                            YOU rewrite it into clean intent.

Make the reasoning RIGOROUS: separate what you ESTABLISHED (proved / tested / verified, backed by
an artifact) from what you merely ASSERTED (prose). Declare what you did not check, and flag where
formal methods or other verification belong — an unverified, load-bearing claim on a high-stakes
path is exactly such a place.

Workflow — after you finish the work:

  1. EMIT     ponens emit -o trace.json
  2. CURATE   ponens trace meta ls trace.json
              ponens trace meta set trace.json <id> --title "<clean intent>" [--status completed]
              ponens trace meta merge trace.json <into> <id...>     # fold dead-ends / false starts
              ponens trace retitle trace.json --title "..." --outcome "..."
  3. ENRICH   ponens trace artifact trace.json --type <SourceCode|VerificationResult|...> \\
                --name "..." --producer-action-id <n>               # declare artifacts -> lineage
              ponens trace residual add trace.json \\
                --kind <assumption|unverified|out_of_scope|limitation|open_question> \\
                --severity <info|low|medium|high|critical> --statement "..." \\
                [--suggested-check "how a reviewer could close it"]  # declare your gaps
  4. GOAL     ponens trace goal set trace.json --intent "<the user's intent>" \\
                --clause "<piece>" --clause "<piece>"                # the definition of done
              ponens trace goal accept trace.json --kind <property|change|obligation|gap> \\
                --label "..." --symbol <f> --covers "<piece>"        # each item binds to evidence
              # split the intent into clauses; cover every clause; prefer strong `property`/`obligation`
              # items over bare `change` (a goal backed only by edits is flagged weakly specified).
  5. GRADE    ponens trace grade trace.json        # a hygiene floor to CLEAR, not a score to game
  6. GOVERN   ponens registry update
              ponens policies add tests_before_commit --into trace.json   # best-practice policies
              ponens trace check trace.json        # a real gate (exit code); --strict also gates the goal
  7. SHARE    ponens trace view trace.json         # read the reasoning (zoomable)
              ponens bind && ponens push           # bind 1:1 to the commit, publish for review

A trace with NO declared residuals is suspicious, not clean. The value to a reviewer is that you
disclosed what you did NOT establish.

`enrich` grades the goal and `check --strict` gates it: a weakly-specified goal (edits landed, nothing
proved or policy-checked) or an uncovered intent clause FAILS. Set a strong bar — and note you can
only report it MET; a reviewer OTHER than you must CERTIFY it (ponens trace goal certify --by reviewer)
was the right definition. Do not self-certify.

Reviewing a trace instead of producing one?   ponens agent --review
"""

REVIEW_GUIDE = """\
ponens — reviewing-agent guide

Review a change by reading its reasoning TRACE, not just its diff. Targeted verification, not trust.

  ponens trace status    <file>          # orient: intent, outcome, grade
  ponens trace enrich    <file>          # resolve the goal — met vs certified, uncovered clauses
  ponens trace grade     <file>          # where the trace is thin (incl. lineage)
  ponens trace residuals <file>          # the declared gaps, by severity — your work-list
  ponens trace reproduce <file> --run    # re-run the recorded commands; report divergence
  ponens trace check     <file>          # run the attached policies + gate the goal (--strict)

Procedure:
  1. Orient — intent, outcome, changed files, lineage. No artifacts/lineage is itself a
     reviewability gap.
  2. Grade the goal, not just the work — did it MEET its definition of done (enrich resolves each
     criterion from evidence), and does the acceptance FAITHFULLY and FULLY capture the intent? A
     weakly-specified bar (edits only, nothing proved/policy-checked) or an uncovered intent clause
     is a reviewability gap. You CONFIRM what re-derives; certifying the definition of done is the
     human (non-doer) act — never self-certify.
  3. Verify the positive space proportionally — re-check the consequential proofs/tests; downgrade
     any unbacked "verified" claim to an undeclared `unverified` residual.
  4. Work the residual surface, highest severity first — run each suggested_check if cheap.
  5. Hunt the UNDECLARED gaps — anything the change touches that is neither verified nor declared.
  6. Verdict — approve only if no open blocking residual remains and every consequential claim was
     re-verified; else request-changes (list the residual_ids to close) or escalate-to-human.

Never treat prose as evidence. Never auto-resolve an open_question. Traces are immutable — gaps
close in a SUCCESSOR trace, not by editing this one.
"""


def cmd_agent(args):
    print(REVIEW_GUIDE if getattr(args, "review", False) else GUIDE)
    return 0


def register(subparsers):
    p = subparsers.add_parser("agent",
                              help="Print the agent workflow guide (how to produce or review a trace)")
    p.add_argument("--review", action="store_true", help="Print the reviewing-agent guide instead")
    p.set_defaults(func=cmd_agent)

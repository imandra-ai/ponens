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
  4. GRADE    ponens trace grade trace.json        # a hygiene floor to CLEAR, not a score to game
  5. GOVERN   ponens registry update
              ponens policies add tests_before_commit --into trace.json   # best-practice policies
              ponens trace check trace.json        # a real gate (exit code)
  6. SHARE    ponens trace view trace.json         # read the reasoning (zoomable)
              ponens bind && ponens push           # bind 1:1 to the commit, publish for review

A trace with NO declared residuals is suspicious, not clean. The value to a reviewer is that you
disclosed what you did NOT establish.

Reviewing a trace instead of producing one?   ponens agent --review
"""

REVIEW_GUIDE = """\
ponens — reviewing-agent guide

Review a change by reading its reasoning TRACE, not just its diff. Targeted verification, not trust.

  ponens trace status    <file>          # orient: intent, outcome, grade
  ponens trace grade     <file>          # where the trace is thin (incl. lineage)
  ponens trace residuals <file>          # the declared gaps, by severity — your work-list
  ponens trace reproduce <file> --run    # re-run the recorded commands; report divergence
  ponens trace check     <file>          # run the attached policies

Procedure:
  1. Orient — intent, outcome, changed files, lineage. No artifacts/lineage is itself a
     reviewability gap.
  2. Verify the positive space proportionally — re-check the consequential proofs/tests; downgrade
     any unbacked "verified" claim to an undeclared `unverified` residual.
  3. Work the residual surface, highest severity first — run each suggested_check if cheap.
  4. Hunt the UNDECLARED gaps — anything the change touches that is neither verified nor declared.
  5. Verdict — approve only if no open blocking residual remains and every consequential claim was
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

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
                --kind <assumption|unverified|out_of_scope|limitation|open_question|defeater> \\
                --severity <info|low|medium|high|critical> --statement "..." \\
                [--defeater-kind <rebuts|undermines|undercuts> --target-id <result>] \\
                [--suggested-check "how a reviewer could close it"]  # declare your gaps
              # `defeater` = counter-evidence AGAINST a claim (a counterexample, model≠code, a test that
              # doesn't establish the property), not a missing gap. An open defeater BLOCKS the claim it
              # targets (a Property over it reads `blocked`); close it in a successor trace.
  4. GOAL     State the goal as a CONTRACT: accomplish these things, subject to these policies.
              Author it as JSON, then load in one shot (`goal set --json`):
                {
                  "intent": "<the user's intent>",
                  "scope": ["<file/symbol>", "..."],
                  "acceptance": [
                    {"id": "c1", "component": {"function": "<f>"},
                     "evidence": {"artifact": "VerificationResult"}},
                    {"id": "c2", "component": {"function": "<g>"},
                     "evidence": {"artifact": "Tests"}},
                    {"id": "c3", "component": {"function": "<h>"},
                     "evidence": {"artifact": "Diff"}}
                  ],
                  "policies": {"packs": ["apply_formal_methods"], "policies": ["research_before_edit"]}
                }
              ponens trace goal set trace.json --json contract.json
              # A criterion just names the ARTIFACT that must exist in the component's lineage
              # (VerificationResult | Decomp | Tests | Diff | any type) — MET = that artifact is present,
              # resolved by LINEAGE. Whether it is GOOD ENOUGH (proved, autoformalized, tests pass, a
              # proof required on a high-stakes path) is decided by the `policies` block — the rigor bar
              # (GOVERNED axis). PROPOSE the policies; a human SELECTS/approves them.
  5. GRADE    ponens trace grade trace.json        # a hygiene floor to CLEAR, not a score to game
  6. GOVERN   ponens registry update
              ponens trace check trace.json        # the GOVERNED axis: the goal's policies as a real
              # gate (exit code). Policies BLOCK by default; a disable/waiver is recorded on the trace,
              # never silent. --strict also gates the goal (failing governed axis / uncovered clause FAILS).
  7. SHARE    ponens trace view trace.json         # read the reasoning (zoomable)
              ponens bind && ponens push           # bind 1:1 to the commit, publish for review

A trace with NO declared residuals is suspicious, not clean. The value to a reviewer is that you
disclosed what you did NOT establish.

Keep formal results current: a formal-reasoning result — verification (proof), state-space analysis
(decomposition), conformance, co-simulation — is only as current as the model it ran on. ponens
recomputes a dependency-CLOSURE fingerprint of the target symbol, so a later change to that symbol —
or anything it transitively uses — marks the result STALE, and removing the symbol marks it DETACHED;
enrich/check surface these as derived residuals and a goal never resolves done over them. After editing
modelled code, RE-RUN the affected result (a fresh result heals it). For this to work, declare
formal-model artifacts (IMLModel/FormalModel) WITH their source + symbols in step 3, and point each result at its model.

A goal yields three INDEPENDENT verdicts (see `ponens trace enrich`): MET (each component has its
evidence artifact), GOVERNED (its policies held — i.e. the evidence was derived correctly), and
CERTIFIED (a non-doer confirmed the criteria were the RIGHT ones). `enrich` resolves met + governed;
`check --strict` gates a failing governed axis or an uncovered intent clause. You can produce and report
MET and GOVERNED — but you must NOT self-certify: a reviewer OTHER than you runs `ponens trace goal
certify --by reviewer`. Propose the rigor bar; a human picks it.

Reviewing a trace instead of producing one?   ponens agent --review
"""

REVIEW_GUIDE = """\
ponens — reviewing-agent guide

Review a change by reading its reasoning TRACE, not just its diff. Targeted verification, not trust.

  ponens trace status    <file>          # orient: intent, outcome, grade
  ponens trace enrich    <file>          # resolve the goal — met ∧ governed ∧ certified, uncovered clauses
  ponens trace grade     <file>          # where the trace is thin (incl. lineage)
  ponens trace residuals <file>          # the declared gaps, by severity — your work-list
  ponens trace reproduce <file> --run    # re-run the recorded commands; report divergence
  ponens trace check     <file>          # run the attached policies + gate the goal (--strict)

Procedure:
  1. Orient — intent, outcome, changed files, lineage. No artifacts/lineage is itself a
     reviewability gap.
  2. Judge the goal on all three axes, not just the work — is it MET (each component has its evidence
     artifact, resolved by lineage), GOVERNED (its policies held — the evidence was derived correctly:
     proved, autoformalized, tests pass), and does the acceptance FAITHFULLY and FULLY capture the
     intent? An uncovered intent clause is a reviewability gap. You CONFIRM what re-derives; CERTIFYING that the
     definition of done was RIGHT is the third axis — a non-doer's act. If you did not do the work,
     your sign-off (`ponens trace goal certify --by reviewer`) IS that certification; never self-certify
     your own work.
  3. Verify the positive space proportionally — re-check the consequential proofs/tests; downgrade
     any unbacked "verified" claim to an undeclared `unverified` residual. Treat a STALE or DETACHED
     result (a proof, decomposition, conformance, …; a derived residual from enrich) as NOT current —
     the code moved under it; require re-running it against the current model, don't credit the old verdict.
     If you find a claim is actually WRONG (a counterexample, model≠code, evidence that doesn't support
     it), raise a `defeater` (`--defeater-kind rebuts|undermines|undercuts`, `--target-id` the result) —
     counter-evidence BLOCKS the claim, unlike a mere gap.
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

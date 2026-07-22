// Canonical VIEWER-side faithfulness computation (GOAL_FAITHFULNESS_v0_1): is a goal's definition of
// done RIGHT, not just met? Reads snake_case (spec/enrich) or camelCase (desktop) fields. Pure (no
// DOM), so it is a real module with two consumers:
//   1. the viewer  — viewer/build.mjs INLINES this (export stripped) ahead of viewer.js, so the Goals
//                    view calls goalFaithfulnessV() from the same script scope.
//   2. the parity harness — parity/run_faithfulness_js.mjs IMPORTS it, and parity/check_faithfulness_
//                    parity.py asserts it agrees with the Python `faithfulness_of` (cli/ponens/goals.py).
// Keep the logic in lockstep with faithfulness_of() — the parity harness enforces it.
export function goalFaithfulnessV(g) {
  const norm = (s) => String(s || 'todo').toLowerCase().replace(/^accept/, '');
  const acc = g.acceptance || [];
  const required = acc.filter((a) => a.required !== false);
  const reqItems = required.length ? required : acc;
  const met = reqItems.length > 0 && reqItems.every((a) => norm(a.status) === 'done');
  // "Hard" evidence = a proof (property) or a policy (obligation); a goal backed only by `change`
  // edits is weakly specified — "done" the moment edits land, with nothing proved or checked.
  const hasHard = reqItems.some((a) => a.kind === 'property' || a.kind === 'obligation');
  const weak = acc.length > 0 && !hasHard;
  const clauses = g.intent_clauses || g.intentClauses || [];
  const covered = new Set();
  for (const a of acc) for (const c of (a.covers || [])) covered.add(c);
  const uncovered = clauses.filter((c) => !covered.has(c));
  // Certified = a non-doer reviewer approved the definition of done, every clause is covered, and it
  // isn't weakly specified. The party that MEETS a goal must not be the sole party that DEFINES it.
  const review = g.criteria_review || g.criteriaReview;
  const reviewer = review && (review.reviewed_by || review.reviewedBy);
  const doers = new Set(acc.map((a) => a.author).filter(Boolean));
  const nonDoer = reviewer && !doers.has(reviewer);
  const approved = review && review.verdict === 'approved';
  const certified = !!(approved && nonDoer && uncovered.length === 0 && !weak);
  return { met, weak, uncovered, certified, reviewer, intentAuthor: g.intent_author || g.intentAuthor };
}

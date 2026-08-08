// Single source of truth for the Docs hub: the guides list (shared by the guides index and the hub
// sidebar), the hub sections (sidebar + /docs landing grid), and the path test the top nav uses to
// keep "Docs" active anywhere in the hub. Keep URLs here in sync with src/pages/** routing.

export const guides = [
  {
    href: "/guides/set-a-goal-contract",
    title: "Set a goal contract",
    who: "Author",
    desc: "State the goal as a contract — accomplish these things (typed acceptance criteria over your code), subject to these policies (the rigor bar). Then read back met / governed / certified.",
  },
  {
    href: "/guides/capture-and-curate",
    title: "Capture & curate a trace",
    who: "Author",
    desc: "You just finished an agent session — turn it into a clean, honest reasoning record: emit, curate the narrative, declare the gaps.",
  },
  {
    href: "/guides/review-a-pr",
    title: "Review an AI-generated PR",
    who: "Reviewer",
    desc: "Someone handed you an AI-written PR. Confirm the goal was met and governed, then certify the criteria were the right ones — the certified axis is the reviewer's job.",
  },
  {
    href: "/guides/add-to-ci",
    title: "Add ponens to CI / your PRs",
    who: "Maintainer",
    desc: "Wire up the GitHub Action so every PR reads back met / governed / certified, with the governed axis as a blocking PASS/FAIL gate and a one-click viewer.",
  },
  {
    href: "/guides/govern-a-repo",
    title: "Govern a repo with policies",
    who: "Maintainer",
    desc: "Own the governed axis: pull best-practice policies from the gallery, scope them to goals, block by default (disable or waive on the record), and write your own rules in LTLf.",
  },
  {
    href: "/guides/programmatic-use",
    title: "Use ponens programmatically",
    who: "Integrator",
    desc: "Drive the policy checker from your own tool: machine-readable JSON output, the Python evaluator API, and a live per-change compliance loop.",
  },
  {
    href: "/guides/import-observability",
    title: "Import from your observability stack",
    who: "Integrator",
    desc: "Turn your existing OpenTelemetry or Langfuse agent traces into ponens traces — spans/observations → actions + lineage — then check them against policies.",
  },
];

// The Tutorials track — a numbered, sequential course through the whole methodology (produce → govern
// → review → sign). Each lesson carries the same trace forward. `n` drives the sidebar/prev-next order;
// `short` is the sidebar label; `title`/`blurb` feed the /tutorials index and the hub grid.
export const tutorials = [
  {
    href: "/tutorials/first-trace", n: 1, short: "First trace",
    title: "Capture your first trace",
    blurb: "Install ponens and turn your latest agent session into a reasoning trace — the two layers, and how to read it.",
  },
  {
    href: "/tutorials/curate", n: 2, short: "Curate",
    title: "Curate the narrative",
    blurb: "Rewrite the raw session into a clean account of what was built and why — without touching the ground-truth actions underneath.",
  },
  {
    href: "/tutorials/declare", n: 3, short: "Declare gaps",
    title: "Declare the negative space",
    blurb: "Add the two things emission can't derive: the artifacts that make lineage real, and the residual surface — what you did NOT establish.",
  },
  {
    href: "/tutorials/goals", n: 4, short: "Goals & axes",
    title: "Goals & the three axes",
    blurb: "State a goal as a contract and read back met / governed / certified — how ponens decides 'done' from evidence, not prose.",
  },
  {
    href: "/tutorials/govern", n: 5, short: "Govern",
    title: "Govern with policies",
    blurb: "Attach best-practice policies and turn `trace check` into a real gate — Computable Governance, block-by-default, waivers on the record.",
  },
  {
    href: "/tutorials/keep-honest", n: 6, short: "Keep it honest",
    title: "Keep the evidence honest",
    blurb: "Grade the trace, watch proofs go Fresh / Stale / Detached as code changes, and record counter-evidence with defeaters.",
  },
  {
    href: "/tutorials/review-and-sign", n: 7, short: "Review & sign",
    title: "Review and sign off",
    blurb: "Switch to the reviewer's seat: verify the consequential claims, certify the goal, and cryptographically sign the result.",
  },
];

// The hub's sections. Each has a `head` link (the section landing) and `items` (its pages, shown in the
// sidebar when that section is current). `blurb` feeds the /docs landing grid.
export const sections = [
  {
    id: "start",
    label: "Overview",
    href: "/docs",
    blurb: "What ponens is, how the pieces fit, and where to start.",
    items: [],
  },
  {
    id: "tutorials",
    label: "Tutorials",
    href: "/tutorials",
    blurb: "A guided, hands-on course through the whole methodology — produce, govern, review, and sign a trace.",
    items: tutorials.map((t) => ({ href: t.href, label: `${t.n} · ${t.short}` })),
  },
  {
    id: "guides",
    label: "Guides",
    href: "/guides",
    blurb: "Short, copy-pasteable how-tos for real tasks — capture, review, CI, govern.",
    items: [
      ...guides.map((g) => ({ href: g.href, label: g.title })),
      { href: "/docs/writing-policies", label: "Writing policies" },
    ],
  },
  {
    id: "agents",
    label: "For agents",
    href: "/agents",
    blurb: "ponens is agent-first: how an agent produces and reviews its own traces.",
    items: [],   // single page — the section head is the link (no lone sub-item)
  },
  {
    id: "adapters",
    label: "Adapters",
    href: "/docs/adapters",
    blurb: "Capture any coding agent's session — Claude Code, pi, and more — via emit adapters.",
    items: [],   // single page — the section head is the link (no lone sub-item)
  },
  {
    id: "spec",
    label: "Spec",
    href: "/spec",
    blurb: "The open standards — the trace, policy, and review-case models.",
    // The Spec section's items are filled in DocsLayout by globbing every generated spec page (so the
    // list is always complete); this is just the fallback landing link.
    items: [{ href: "/spec", label: "All specifications" }],
  },
];

// True when a path is anywhere in the Docs hub — the top nav uses this to keep "Docs" active across
// /docs, /guides, /agents, and /spec.
export const isDocsPath = (p) =>
  ["/docs", "/tutorials", "/guides", "/agents", "/spec"].some((b) => p === b || p.startsWith(b + "/"));

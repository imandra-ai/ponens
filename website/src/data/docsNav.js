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

// The hub's sections. Each has a `head` link (the section landing) and `items` (its pages, shown in the
// sidebar when that section is current). `blurb` feeds the /docs landing grid.
export const sections = [
  {
    id: "start",
    label: "Getting started",
    href: "/docs",
    blurb: "Install, then the emit → curate → declare → govern → share tour.",
    items: [
      { href: "/docs/writing-policies", label: "Writing policies" },
    ],
  },
  {
    id: "guides",
    label: "Guides",
    href: "/guides",
    blurb: "Short, copy-pasteable how-tos for real tasks — capture, review, CI, govern.",
    items: guides.map((g) => ({ href: g.href, label: g.title })),
  },
  {
    id: "agents",
    label: "For agents",
    href: "/agents",
    blurb: "ponens is agent-first: how an agent produces and reviews its own traces.",
    items: [{ href: "/agents", label: "Agent workflow" }],
  },
  {
    id: "adapters",
    label: "Adapters",
    href: "/docs/adapters",
    blurb: "Capture any coding agent's session — Claude Code, pi, and more — via emit adapters.",
    items: [{ href: "/docs/adapters", label: "Agent adapters" }],
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
  ["/docs", "/guides", "/agents", "/spec"].some((b) => p === b || p.startsWith(b + "/"));

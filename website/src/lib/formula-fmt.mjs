// Presentation helpers for the ponens policy language: syntax highlighting plus
// a hover glossary. Shared by the gallery cards (bundled client script) and the
// policy detail pages (rendered at build time), so both stay in sync.
//
// highlightFormula() returns an HTML string in which every operator, symbol and
// atom is wrapped in a <span class="tok t-…" data-tip="…">. The data-tip is
// surfaced as a floating tooltip by the handler in Layout.astro.

// Temporal / lineage operators ------------------------------------------------
const OP_TIP = {
  G: "Globally — must hold at every step from here onward.",
  F: "Finally — must hold at some future step.",
  X: "Next — must hold at the very next step.",
  P: "Previously — held at some earlier step.",
  H: "Historically — held at every earlier step.",
  U: "Until — the left side holds until the right side becomes true.",
  S: "Since — the left side has held ever since the right side was true.",
  S_last: "Since last — holds since the most recent occurrence of the right side.",
  P_target: "Previously, same target — a matching action occurred earlier on the same target.",
  P_chain: "Previously in lineage — a contextually-related (same causal chain) action occurred earlier.",
  H_target: "Historically, same target — held at every earlier step on the same target.",
  H_chain: "Historically in lineage — held throughout the related causal chain.",
};
const OPS = new Set(Object.keys(OP_TIP));

// Logical, relational and set symbols ----------------------------------------
const SYM_TIP = {
  "→": "Implies — if the left side holds, the right side must hold.",
  "∧": "And — both sides must hold.",
  "∨": "Or — at least one side must hold.",
  "¬": "Not — negation.",
  "∀": "For all — universal quantifier (structural fragment).",
  "∃": "Exists — there is some (structural fragment).",
  "⊨": "Entails / verified — discharged by a reasoner.",
  "∈": "Element of — set membership.",
  "∅": "The empty set.",
  "=": "Equals.",
  "≠": "Not equal.",
  "≤": "Less than or equal to.",
  "≥": "Greater than or equal to.",
  "<": "Less than.",
  ">": "Greater than.",
};

// Verification statuses -------------------------------------------------------
const STATUS_TIP = {
  completed: "Status: the action completed successfully.",
  failed: "Status: the action failed.",
  proved: "Status: the proof obligation was discharged.",
  refuted: "Status: the proof obligation was refuted (counterexample found).",
  sat: "Status: the constraints were satisfiable.",
  unknown: "Status: the reasoner returned no definite answer.",
};

// Common action types — the CamelCase atoms that name a kind of recorded event.
const ACTION_TIP = {
  EditFile: "Action: an existing file was edited.",
  CreateFile: "Action: a new file was created.",
  DeleteFile: "Action: a file was deleted.",
  ReadFile: "Action: a file was read.",
  SearchCode: "Action: the codebase was searched.",
  AnalyzeCode: "Action: code was analyzed.",
  ReadDocumentation: "Action: documentation was read.",
  GitCommit: "Action: a git commit was made.",
  GitPush: "Action: changes were pushed to a remote.",
  Verify: "Action: a property was verified by a reasoner.",
  Formalize: "Action: an artifact was turned into a formal model.",
  Decompose: "Action: a goal was broken into sub-goals.",
  GenerateTests: "Action: tests were generated.",
  DefineVG: "Action: a verification goal was defined.",
  Deploy: "Action: something was deployed.",
  StaticAnalysis: "Action: static analysis was run.",
  CoverageAnalysis: "Action: coverage analysis was run.",
  Lint: "Action: a linter was run.",
  TypeCheck: "Action: type checking was run.",
  Decision: "Action: a decision was recorded.",
  Output: "Action: an output was produced.",
  Recommendation: "Action: a recommendation was produced.",
  Plan: "Action: a plan was produced.",
  Draft: "Action: a draft was produced.",
  UserApproval: "Action: a human approved a step.",
  Change: "Action: a tracked change.",
  Incident: "Action: an incident record.",
  Release: "Action: a release.",
  ToolCall: "Action: an external tool was called.",
  Retrieve: "Action: information was retrieved.",
  Compute: "Action: a computation was performed.",
};

const esc = (s) =>
  String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

function span(cls, text, tip) {
  const tipAttr = tip ? ` data-tip="${esc(tip)}"` : "";
  return `<span class="tok ${cls}"${tipAttr}>${esc(text)}</span>`;
}

function classifyWord(w) {
  if (OPS.has(w)) return span("t-op", w, OP_TIP[w]);
  if (STATUS_TIP[w]) return span("t-kw", w, STATUS_TIP[w]);
  if (/^[A-Z][A-Za-z0-9]*$/.test(w))
    return span("t-type", w, ACTION_TIP[w] || "Action type — an event of this kind recorded in the trace.");
  return span("t-flag", w, "Flag — a property attached to the action (a lowercase predicate).");
}

// One pass: emit highlighted HTML once so inserted markup is never re-scanned
// (chained .replace() passes would mangle words sitting inside data-tip text).
const TOKEN_RE = /([A-Za-z_][A-Za-z0-9_]*)|([→∧∨¬∀∃⊨∈∅≠≥≤<>=])/g;

export function highlightFormula(formula) {
  if (!formula) return "";
  let out = "";
  let last = 0;
  let m;
  TOKEN_RE.lastIndex = 0;
  while ((m = TOKEN_RE.exec(formula)) !== null) {
    out += esc(formula.slice(last, m.index));
    last = m.index + m[0].length;
    if (m[1] !== undefined) out += classifyWord(m[1]);
    else out += span("t-sym", m[2], SYM_TIP[m[2]]);
  }
  out += esc(formula.slice(last));
  return out;
}

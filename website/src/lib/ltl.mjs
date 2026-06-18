// A small evaluator for the ponens policy language — the temporal + scoped fragment.
//
// v1 scope (evaluated client-side, no backend):
//   future:   G F X
//   past:     P H
//   binary:   U S S_last
//   scoped:   P_target            (same-target previously)
//   boolean:  ¬ ∧ ∨ →            (ASCII: ! /\ \/ ->)
//   atoms:    action types (CamelCase), categories (gateway/reasoning/activity),
//             statuses (completed/failed/proved/refuted/sat/unknown),
//             lifecycle (start_event/end_event), 'action' (any), lowercase flags,
//             the call form  Type(φ)  (≡ Type ∧ φ), and  rationale ≠ ∅.
//
// Anything outside this (P_chain / H_chain / H_target lineage operators, quantifiers
// ∀ ∃ over residuals/artifacts, set comprehensions — i.e. the `structural` fragment)
// is reported as { supported: false } rather than guessed at, so the playground never
// disagrees with `ponens trace check`.

const UNARY = new Set(["G", "F", "X", "P", "H", "P_target", "P_chain", "H_target", "H_chain"]);
const BINTEMP = new Set(["U", "S", "S_last"]);
const STATUS = new Set(["completed", "failed", "proved", "refuted", "sat", "unknown"]);
const CATS = new Set(["gateway", "reasoning", "activity"]);

// Both ASCII dialects are accepted: /\ \/ (the browser's historical form) AND
// && || (the form `ponens trace check` uses), so a formula written for either
// engine parses here. Unicode ∧ ∨ are handled directly below.
const ASCII2 = { "->": "→", "/\\": "∧", "\\/": "∨", "&&": "∧", "||": "∨", "!=": "≠", ">=": "≥", "<=": "≤" };
const SYMS = "→∧∨¬∀∃∈∅≠≥≤<>=().,⊨";

function tokenize(src) {
  const toks = [];
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    if (/\s/.test(c)) { i++; continue; }
    const t2 = src.slice(i, i + 2);
    if (ASCII2[t2]) { toks.push({ t: "sym", v: ASCII2[t2] }); i += 2; continue; }
    if (c === "!") { toks.push({ t: "sym", v: "¬" }); i++; continue; }
    if (SYMS.includes(c)) { toks.push({ t: "sym", v: c }); i++; continue; }
    const num = src.slice(i).match(/^[0-9]+/);
    if (num) { toks.push({ t: "num", v: num[0] }); i += num[0].length; continue; }
    const m = src.slice(i).match(/^[A-Za-z_][A-Za-z0-9_]*/);
    if (m) { toks.push({ t: "id", v: m[0] }); i += m[0].length; continue; }
    throw { unsupported: true, reason: `unexpected character '${c}'` };
  }
  return toks;
}

function parse(src) {
  const toks = tokenize(src);
  let p = 0;
  const peek = () => toks[p];
  const eat = () => toks[p++];
  const isSym = (v) => peek() && peek().t === "sym" && peek().v === v;
  const isId = (set) => peek() && peek().t === "id" && set.has(peek().v);

  function implication() {
    let a = disjunction();
    if (isSym("→")) { eat(); return { k: "bin", op: "→", a, b: implication() }; }
    return a;
  }
  function disjunction() {
    let a = conjunction();
    while (isSym("∨")) { eat(); a = { k: "bin", op: "∨", a, b: conjunction() }; }
    return a;
  }
  function conjunction() {
    let a = binTemporal();
    while (isSym("∧")) { eat(); a = { k: "bin", op: "∧", a, b: binTemporal() }; }
    return a;
  }
  function binTemporal() {
    let a = unary();
    while (isId(BINTEMP)) { const op = eat().v; a = { k: "bin", op, a, b: unary() }; }
    return a;
  }
  function unary() {
    if (isSym("¬")) { eat(); return { k: "not", x: unary() }; }
    if (isSym("∀") || isSym("∃")) throw { unsupported: true, reason: "quantifiers (∀ / ∃) are structural — try the CLI" };
    if (isId(UNARY)) {
      const op = eat().v;
      if (["P_chain", "H_chain", "H_target"].includes(op))
        throw { unsupported: true, reason: `lineage operator ${op} isn't in the v1 simulator — try \`ponens trace check\`` };
      return { k: "un", op, x: unary() };
    }
    return primary();
  }
  function primary() {
    if (isSym("(")) { eat(); const e = implication(); if (!isSym(")")) throw { unsupported: true, reason: "expected )" }; eat(); return e; }
    if (peek() && peek().t === "id") {
      const name = eat().v;
      // count(φ) <op> N — trace-level aggregate over positions
      if (name === "count" && isSym("(")) {
        eat(); const body = implication();
        if (!isSym(")")) throw { unsupported: true, reason: "expected )" };
        eat();
        const opTok = peek();
        if (!opTok || opTok.t !== "sym" || !"≤<≥>=≠".includes(opTok.v))
          throw { unsupported: true, reason: "count(...) must be followed by a comparison and a number" };
        const op = eat().v;
        const numTok = peek();
        if (!numTok || numTok.t !== "num")
          throw { unsupported: true, reason: "count(...) comparison expects an integer" };
        eat();
        return { k: "count", body, op, n: parseInt(numTok.v, 10) };
      }
      if (isSym("(")) { eat(); const arg = implication(); if (!isSym(")")) throw { unsupported: true, reason: "expected )" }; eat(); return { k: "call", type: name, arg }; }
      if (isSym("≠") || isSym("=") || isSym("≥") || isSym("≤")) {
        const op = eat().v;
        const rt = eat();
        return { k: "cmp", op, left: name, right: rt ? rt.v : null };
      }
      return { k: "atom", name };
    }
    throw { unsupported: true, reason: `unexpected token ${peek() ? peek().v : "end of input"}` };
  }

  const ast = implication();
  if (p !== toks.length) throw { unsupported: true, reason: `unexpected '${peek().v}'` };
  return ast;
}

// Path patterns that mark an action as touching a high-stakes area. Kept in
// sync with the CLI (cli/ponens/trace.py).
const HIGH_STAKES = ["payments/", "risk/", "stripe_payment_flow"];
const START_TRIGGERS = new Set(["TaskReceived", "TriggeredByEvent"]);
const END_OUTCOMES = new Set(["ProcessCompleted", "ProcessAborted", "ProcessInterrupted"]);

// The keyword surface a custom predicate matches against — the action type plus
// its free text, mirroring the CLI's `type label detail rationale result_summary`
// blob. The playground's `flags` stand in for the action's text; underscores in a
// predicate name match spaces, so expand them here too.
function searchText(a) {
  const flags = (a.flags || []).map((f) => f.replace(/_/g, " "));
  return [a.type, a.detail, ...flags].filter(Boolean).join(" ").toLowerCase();
}

function atomHolds(name, i, trace, meta) {
  const a = trace[i];
  if (name === "action") return true;
  // Trace-level lifecycle predicates — properties of the trigger/outcome, not of
  // any position (matches the CLI exactly).
  if (name === "start_event") return START_TRIGGERS.has((meta.trigger || {}).type);
  if (name === "end_event") return END_OUTCOMES.has((meta.outcome || {}).type);
  if (STATUS.has(name)) return a.status === name;
  if (CATS.has(name)) return a.category === name;
  if (name === "high_stakes_path") return HIGH_STAKES.some((p) => (a.target || "").includes(p));
  if (/^[A-Z]/.test(name)) return a.type === name; // CamelCase → exact action/artifact type
  // lowercase custom predicate → substring keyword match against the action text
  return searchText(a).includes(name.replace(/_/g, " ").toLowerCase());
}

function evalAt(n, i, trace, meta) {
  switch (n.k) {
    case "atom": return atomHolds(n.name, i, trace, meta);
    case "call": return atomHolds(n.type, i, trace, meta) && evalAt(n.arg, i, trace, meta);
    case "count": {
      let c = 0;
      for (let j = 0; j < trace.length; j++) if (evalAt(n.body, j, trace, meta)) c++;
      const v = n.n;
      switch (n.op) {
        case "≤": return c <= v;
        case "<": return c < v;
        case "≥": return c >= v;
        case ">": return c > v;
        case "=": return c === v;
        case "≠": return c !== v;
      }
      return false;
    }
    case "cmp": {
      if (n.left === "rationale" && (n.right === "∅" || n.right === "EMPTY")) {
        const has = !!trace[i].rationale;
        return n.op === "≠" ? has : !has;
      }
      throw { unsupported: true, reason: `comparison \`${n.left} ${n.op} ${n.right}\` isn't in the v1 simulator` };
    }
    case "not": return !evalAt(n.x, i, trace, meta);
    case "bin": {
      const { op, a, b } = n;
      if (op === "∧") return evalAt(a, i, trace, meta) && evalAt(b, i, trace, meta);
      if (op === "∨") return evalAt(a, i, trace, meta) || evalAt(b, i, trace, meta);
      if (op === "→") return !evalAt(a, i, trace, meta) || evalAt(b, i, trace, meta);
      if (op === "U") {
        for (let k = i; k < trace.length; k++) {
          if (evalAt(b, k, trace, meta)) { for (let m = i; m < k; m++) if (!evalAt(a, m, trace, meta)) return false; return true; }
        }
        return false;
      }
      if (op === "S") {
        for (let k = i; k >= 0; k--) {
          if (evalAt(b, k, trace, meta)) { for (let m = k + 1; m <= i; m++) if (!evalAt(a, m, trace, meta)) return false; return true; }
        }
        return false;
      }
      if (op === "S_last") {
        let k = -1;
        for (let j = i - 1; j >= 0; j--) if (evalAt(b, j, trace, meta)) { k = j; break; }
        for (let m = k + 1; m <= i; m++) if (evalAt(a, m, trace, meta)) return true;
        return false;
      }
      throw { unsupported: true, reason: `operator ${op}` };
    }
    case "un": {
      const { op, x } = n;
      if (op === "G") { for (let j = i; j < trace.length; j++) if (!evalAt(x, j, trace, meta)) return false; return true; }
      if (op === "F") { for (let j = i; j < trace.length; j++) if (evalAt(x, j, trace, meta)) return true; return false; }
      if (op === "X") return i + 1 < trace.length && evalAt(x, i + 1, trace, meta);
      if (op === "P") { for (let j = 0; j < i; j++) if (evalAt(x, j, trace, meta)) return true; return false; }
      if (op === "H") { for (let j = 0; j < i; j++) if (!evalAt(x, j, trace, meta)) return false; return true; }
      if (op === "P_target") {
        const tg = trace[i].target;
        if (tg == null || tg === "") return false;
        for (let j = 0; j < i; j++) if (trace[j].target === tg && evalAt(x, j, trace, meta)) return true;
        return false;
      }
      throw { unsupported: true, reason: op };
    }
  }
  throw { unsupported: true, reason: "unknown node" };
}

// Evaluate a policy formula against a finite trace (a list of action objects).
// Returns:
//   { ok:false, error }                         — couldn't parse
//   { ok:true, supported:false, reason }         — uses a construct outside v1
//   { ok:true, supported:true, verdict, per, witness, witnessKind, bodyOp }
// `per[i]` is the truth of the formula's inner body at position i (for the step-through).
// `meta` carries trace-level context the lifecycle predicates read: { trigger, outcome }.
export function evaluate(formula, trace, meta = {}) {
  let ast;
  try { ast = parse(formula); }
  catch (e) { if (e && e.unsupported) return { ok: true, supported: false, reason: e.reason }; return { ok: false, error: String((e && e.message) || e) }; }
  try {
    const n = trace.length;
    const topTemporal = ast.k === "un" && ["G", "F", "H", "X", "P"].includes(ast.op);
    const body = topTemporal ? ast.x : ast;
    const per = [];
    for (let i = 0; i < n; i++) per.push(evalAt(body, i, trace, meta));
    const verdict = evalAt(ast, 0, trace, meta);
    let witness = null, witnessKind = null;
    if (ast.k === "un" && ast.op === "G") { const idx = per.findIndex((v) => !v); if (idx >= 0) { witness = idx; witnessKind = "violates"; } }
    else if (ast.k === "un" && ast.op === "F") { const idx = per.findIndex((v) => v); if (idx >= 0) { witness = idx; witnessKind = "satisfies"; } }
    return { ok: true, supported: true, verdict, per, witness, witnessKind, bodyOp: topTemporal ? ast.op : null };
  } catch (e) {
    if (e && e.unsupported) return { ok: true, supported: false, reason: e.reason };
    return { ok: false, error: String((e && e.message) || e) };
  }
}

export const VOCAB = {
  types: ["ReadFile", "EditFile", "CreateFile", "DeleteFile", "SearchCode", "AnalyzeCode",
    "ReadDocumentation", "RunTests", "Lint", "TypeCheck", "GitCommit", "GitPush",
    "Formalize", "Verify", "Decompose", "GenerateTests", "DefineVG", "UserApproval", "Deploy",
    "ToolCall", "Retrieve", "Compute", "Draft", "Release"],
  statuses: ["", "completed", "failed", "proved", "refuted", "sat"],
  // Trace-level lifecycle values the start_event / end_event predicates read.
  triggers: ["", "TaskReceived", "TriggeredByEvent"],
  outcomes: ["", "ProcessCompleted", "ProcessAborted", "ProcessInterrupted"],
};

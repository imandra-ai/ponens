// JS side of the parity harness. Reads the shared corpus (cases.json), renders
// each canonical trace into the browser evaluator's flat action shape, runs
// website/src/lib/ltl.mjs, and prints one JSON line per case to stdout:
//   { name, kind: "supported"|"unsupported"|"error", verdict?, reason?, error? }
//
// Run: node parity/run_js.mjs           (reads ./parity/cases.json)
//      node parity/run_js.mjs <path>    (explicit corpus path)

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { evaluate } from "../website/src/lib/ltl.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const casesPath = process.argv[2] || resolve(here, "cases.json");
const { cases } = JSON.parse(readFileSync(casesPath, "utf8"));

// Canonical action -> flat shape consumed by ltl.mjs. The browser evaluator is
// position-indexed, so the array order is the trace order.
function toJs(a) {
  const o = { type: a.type };
  if (a.category != null) o.category = a.category;
  if (a.target != null) o.target = a.target;
  if (a.status != null) o.status = a.status;
  if (a.flags != null) o.flags = a.flags;
  if (a.rationale !== undefined) o.rationale = a.rationale;
  return o;
}

const out = [];
for (const c of cases) {
  const trace = (c.trace || []).map(toJs);
  const meta = { trigger: c.trigger || {}, outcome: c.outcome || {} };
  const r = evaluate(c.formula, trace, meta);
  if (!r.ok) out.push({ name: c.name, kind: "error", error: r.error });
  else if (!r.supported) out.push({ name: c.name, kind: "unsupported", reason: r.reason });
  else out.push({ name: c.name, kind: "supported", verdict: r.verdict });
}

process.stdout.write(JSON.stringify(out));

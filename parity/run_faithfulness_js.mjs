// JS side of the faithfulness parity harness. Imports the VIEWER's goalFaithfulnessV (the exact
// function the Goals view inlines at build), runs it over the shared corpus, and prints one JSON
// object per case: { name, met, certified, weakly_specified, uncovered_clauses }.
//
// Run: node parity/run_faithfulness_js.mjs            (reads ./parity/faithfulness_cases.json)
//      node parity/run_faithfulness_js.mjs <path>     (explicit corpus path)

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { goalFaithfulnessV } from "../viewer/core/faithfulness.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const casesPath = process.argv[2] || resolve(here, "faithfulness_cases.json");
const { cases } = JSON.parse(readFileSync(casesPath, "utf8"));

const out = cases.map((c) => {
  const f = goalFaithfulnessV(c.goal);
  // Normalise to the Python field names so the harness compares like-for-like.
  return {
    name: c.name,
    met: !!f.met,
    certified: !!f.certified,
    weakly_specified: !!f.weak,
    uncovered_clauses: f.uncovered,
  };
});

process.stdout.write(JSON.stringify(out));

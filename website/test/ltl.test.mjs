// Correctness oracle for the v1 LTL evaluator. Run: node test/ltl.test.mjs
import { evaluate } from "../src/lib/ltl.mjs";

let pass = 0, fail = 0;
function check(name, formula, trace, expected, meta = {}) {
  const r = evaluate(formula, trace, meta);
  let got;
  if (!r.ok) got = `ERR:${r.error}`;
  else if (!r.supported) got = `UNSUPPORTED:${r.reason}`;
  else got = r.verdict;
  const ok = got === expected;
  if (ok) pass++; else { fail++; console.log(`  ✗ ${name}\n      formula: ${formula}\n      expected ${JSON.stringify(expected)}, got ${JSON.stringify(got)}`); }
}

const A = (type, extra = {}) => ({ type, ...extra });

// tests_before_commit — G(GitCommit → P(RunTests ∧ completed))
const F_TBC = "G(GitCommit → P(RunTests ∧ completed))";
check("tbc pass", F_TBC, [A("ReadFile"), A("RunTests", { status: "completed" }), A("EditFile"), A("GitCommit")], true);
check("tbc fail (no test)", F_TBC, [A("EditFile"), A("GitCommit")], false);
check("tbc fail (test failed)", F_TBC, [A("RunTests", { status: "failed" }), A("GitCommit")], false);
check("tbc vacuous (no commit)", F_TBC, [A("ReadFile"), A("EditFile")], true);

// research_before_edit — G(EditFile → P_target(ReadFile ∨ SearchCode))
const F_RBE = "G(EditFile → P_target(ReadFile ∨ SearchCode))";
check("rbe pass (same target)", F_RBE, [A("ReadFile", { target: "a.py" }), A("EditFile", { target: "a.py" })], true);
check("rbe fail (different target)", F_RBE, [A("ReadFile", { target: "b.py" }), A("EditFile", { target: "a.py" })], false);
check("rbe fail (no prior read)", F_RBE, [A("EditFile", { target: "a.py" })], false);

// no_force_push — G(¬(GitPush ∧ force))
const F_NFP = "G(¬(GitPush ∧ force))";
check("nfp pass", F_NFP, [A("GitPush", { flags: [] })], true);
check("nfp fail", F_NFP, [A("GitPush", { flags: ["force"] })], false);

// all_actions_have_rationale — G(action → rationale ≠ ∅)
const F_AHR = "G(action → rationale ≠ ∅)";
check("ahr pass", F_AHR, [A("ReadFile", { rationale: true }), A("EditFile", { rationale: true })], true);
check("ahr fail", F_AHR, [A("ReadFile", { rationale: true }), A("EditFile", { rationale: false })], false);

// lifecycle — start_event ∧ F end_event (trace-level trigger/outcome)
const LIFECYCLE_META = { trigger: { type: "TaskReceived" }, outcome: { type: "ProcessCompleted" } };
check("lifecycle pass", "start_event ∧ F end_event", [A("ReadFile"), A("GitCommit")], true, LIFECYCLE_META);
check("lifecycle fail (no outcome)", "start_event ∧ F end_event", [A("ReadFile"), A("GitCommit")], false, { trigger: { type: "TaskReceived" } });

// counterexample_triggers_fix — G(Verify ∧ refuted → F(EditFile))
const F_CTF = "G(Verify ∧ refuted → F(EditFile))";
check("ctf pass", F_CTF, [A("Verify", { status: "refuted" }), A("EditFile")], true);
check("ctf fail", F_CTF, [A("Verify", { status: "refuted" })], false);

// S_last — G(GitCommit → (RunTests ∧ completed) S_last GitCommit)
const F_TPBC = "G(GitCommit → (RunTests ∧ completed) S_last GitCommit)";
check("s_last pass", F_TPBC, [A("RunTests", { status: "completed" }), A("GitCommit"), A("RunTests", { status: "completed" }), A("GitCommit")], true);
check("s_last fail (no test since last commit)", F_TPBC, [A("RunTests", { status: "completed" }), A("GitCommit"), A("EditFile"), A("GitCommit")], false);

// ASCII operators should parse the same
check("ascii ops", "G(GitCommit -> P(RunTests /\\ completed))", [A("RunTests", { status: "completed" }), A("GitCommit")], true);

// count() aggregate — trajectory length / tool budget
check("count trajectory pass", "count(action) <= 3", [A("ReadFile"), A("EditFile")], true);
check("count trajectory fail", "count(action) <= 3", [A("ReadFile"), A("EditFile"), A("RunTests"), A("GitCommit")], false);
check("count by type", "count(RunTests) >= 2", [A("RunTests"), A("EditFile"), A("RunTests")], true);

// Unsupported (structural / lineage) — must NOT guess a verdict
check("unsupported P_chain", "G(EditFile ∧ high_stakes_path → P_chain(VerificationResult(proved ∨ sat) ∨ Decomposition))",
  [A("EditFile", { flags: ["high_stakes_path"] })], "UNSUPPORTED:lineage operator P_chain isn't in the v1 simulator — try `ponens trace check`");
check("unsupported quantifier", "¬∃ r ∈ residuals . r.severity = Critical", [A("ReadFile")],
  "UNSUPPORTED:quantifiers (∀ / ∃) are structural — try the CLI");

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);

#!/usr/bin/env python3
"""Generate the INTERNAL goal-contract gallery: a curated set of small, valid traces that each exercise
one facet of the Goal Contract (GOAL_CONTRACT_v0_2) — the three axes (met / governed / certified),
every evidence-artifact type, goal-scoped governance (block / disable), and faithfulness (coverage,
self-review). The website's /internal page and `ponens trace view` both read these.

Run:  python3 examples/make_goal_gallery.py     (writes examples/goal-contract/*.json + manifest.json)
"""
import copy
import json
import os

from ponens.goals import enrich

OUT = os.path.join(os.path.dirname(__file__), "goal-contract")


def axes_of(tr):
    """Resolve the three axes so the gallery can badge each example without re-running enrich."""
    g = enrich(copy.deepcopy(tr))["goals"][0]
    f = g.get("faithfulness", {})
    gov = g.get("governed")
    return {"met": bool(f.get("met")),
            "governed": (None if gov is None else bool(gov)),
            "certified": bool(f.get("certified"))}

# --- Inline policies (self-contained: no registry needed to resolve the governed axis) ---------------
POL_REPROVED = {
    "policy_id": "refuted_results_must_be_reproved", "name": "refuted_results_must_be_reproved",
    "severity": "error", "formula": "G(VerificationResult(refuted) → F(VerificationResult(proved ∨ sat)))",
}
POL_HIGH_STAKES = {
    "policy_id": "reasoning_required_for_high_stakes", "name": "reasoning_required_for_high_stakes",
    "severity": "error",
    "formula": "G(EditFile ∧ high_stakes_path → P_chain(VerificationResult(proved ∨ sat) ∨ Decomposition))",
}
POL_GENERATED_TESTS_DECOMP = {
    "policy_id": "generated_tests_require_decomposition", "name": "generated_tests_require_decomposition",
    "severity": "error", "formula": "G(GeneratedTests → Decomposition ∈ ancestors(derived_from))",
}


def _act(i, typ, label, outputs=None, **extra):
    a = {"id": i, "type": typ, "category": "activity", "label": label,
         "rationale": label, "inputs": [], "outputs": outputs or [], "evidence": []}
    a.update(extra)
    return a


def _art(aid, atype, producer, derived=None, payload=None, target_symbol=None, name=None):
    o = {"artifact_id": aid, "artifact_type": atype, "name": name or aid, "producer_action_id": producer}
    if derived:
        o["derived_from"] = derived
    p = dict(payload or {})
    if target_symbol:
        p["target_symbol"] = target_symbol
    if p:
        o["payload"] = p
    return o


def verification_chain(component, status, start_id, start_art, reproved=False):
    """A src → IMLModel → VG → VerificationResult chain for `component`, ending in `status`.
    Returns (actions, artifacts, evidence_artifact_id)."""
    s, a = start_id, start_art
    src, model, vg, vr = f"{a}_src", f"{a}_model", f"{a}_vg", f"{a}_vr"
    acts = [
        _act(s, "ReadFile", f"read {component}", [src]),
        _act(s + 1, "Formalize", f"autoformalize {component}", [model]),
        _act(s + 2, "DefineVG", f"define VG for {component}", [vg]),
        _act(s + 3, "Verify", f"verify {component}", [vr], vg_result={"status": status}),
    ]
    arts = [
        _art(src, "SourceCode", s),
        _art(model, "IMLModel", s + 1, [src], {"symbols": [component]}),
        _art(vg, "VerificationGoal", s + 2, [model], {"goal_id": vg}, target_symbol=component),
        _art(vr, "VerificationResult", s + 3, [vg], {"goal_id": vg, "goal_artifact_id": vg, "status": status}),
    ]
    ev = vr
    if reproved:
        vr2 = f"{a}_vr2"
        acts.append(_act(s + 4, "Verify", f"re-verify {component}", [vr2], vg_result={"status": "proved"}))
        arts.append(_art(vr2, "VerificationResult", s + 4, [vg], {"goal_id": vg, "status": "proved"}))
        ev = vr2
    return acts, arts, ev


def trace(trace_id, title, actions, artifacts, goal, high_stakes=None):
    return {
        "trace_id": trace_id, "spec_version": "1.7", "assistant": "codelogician", "model": "demo",
        "timestamp": "2026-07-25T00:00:00Z", "title": title,
        "trigger": {"type": "TaskReceived", "description": title},
        "actions": actions, "artifacts": artifacts,
        "outcome": {"type": "ProcessCompleted", "summary": title},
        "goals": [goal],
        **({"high_stakes_paths": high_stakes} if high_stakes else {}),
    }


def goal(intent, acceptance, clauses=None, review=None, policies=None, scope=None):
    g = {"id": "session-goal", "intent": intent, "scope": scope or [], "status": "active",
         "acceptance": acceptance}
    if clauses:
        g["intent_clauses"] = clauses
    if review:
        g["criteria_review"] = review
    if policies:
        g["policies"] = policies
    return g


def crit(cid, component, artifact, covers=None, author="agent"):
    c = {"id": cid, "component": {"function": component}, "evidence": {"artifact": artifact},
         "required": True, "author": author}
    if covers:
        c["covers"] = covers
    return c


REVIEW_OK = {"reviewed_by": "reviewer", "verdict": "approved", "at": "2026-07-25T01:00:00Z"}

CASES = []  # (group, filename, name, summary, trace)


def add(group, fname, name, summary, tr):
    CASES.append((group, fname, name, summary, tr))


# === THREE AXES ====================================================================================
acts, arts, ev = verification_chain("settle", "proved", 1, "a")
add("Three axes", "01-all-three-axes.json", "All three axes green",
    "settle is proved, its policy holds, and a non-doer certified the definition — met ∧ governed ∧ certified.",
    trace("gc-three-axes", "All three axes: met, governed, certified",
          acts, arts,
          goal("Settlement conserves money", [crit("c1", "settle", "VerificationResult", ["conserve money"])],
               clauses=["conserve money"], review=REVIEW_OK,
               policies={"policies": [POL_REPROVED]}, scope=["settle"])))

acts, arts, ev = verification_chain("settle", "refuted", 1, "a")  # refuted, never reproved
add("Three axes", "02-met-but-ungoverned.json", "Met but NOT governed",
    "A VerificationResult exists (so the criterion is MET), but it is refuted and never re-proved — the "
    "policy fails, so the goal is NOT governed. The headline case: met ≠ done.",
    trace("gc-ungoverned", "Met but ungoverned: a refuted proof still 'exists'",
          acts, arts,
          goal("Settlement conserves money", [crit("c1", "settle", "VerificationResult", ["conserve money"])],
               clauses=["conserve money"], review=REVIEW_OK,
               policies={"policies": [POL_REPROVED]}, scope=["settle"])))

acts, arts, ev = verification_chain("settle", "proved", 1, "a")
add("Three axes", "03-met-governed-uncertified.json", "Met + governed, NOT certified",
    "Proved and policy-clean, but no non-doer has signed off on the definition of done — certified is "
    "still open. Green work, unreviewed bar.",
    trace("gc-uncertified", "Met and governed, but the definition is self-authored",
          acts, arts,
          goal("Settlement conserves money", [crit("c1", "settle", "VerificationResult", ["conserve money"])],
               clauses=["conserve money"], policies={"policies": [POL_REPROVED]}, scope=["settle"])))

# certified but unmet: the definition is right (reviewed + covered) but the evidence artifact is absent.
add("Three axes", "04-certified-but-unmet.json", "Certified but NOT met",
    "A reviewer approved the definition and every clause is covered (certified), but no VerificationResult "
    "exists yet — the work is unfinished. The right target, in progress.",
    trace("gc-certified-unmet", "Certified definition, work not yet done",
          [_act(1, "ReadFile", "read settle", ["a_src"])],
          [_art("a_src", "SourceCode", 1)],
          goal("Settlement conserves money", [crit("c1", "settle", "VerificationResult", ["conserve money"])],
               clauses=["conserve money"], review=REVIEW_OK, scope=["settle"])))

# === EVIDENCE TYPES ================================================================================
# One goal whose criteria each require a DIFFERENT artifact type — all present → all met. Evidence is
# generic: formal (VerificationResult, Decomp) and informal (Tests, Diff, Documentation) all count.
ev_acts, ev_arts = [], []
vacts, varts, _ = verification_chain("price", "proved", 1, "p")
ev_acts += vacts; ev_arts += varts
# decomposition of tier
ev_acts += [_act(10, "ReadFile", "read tier", ["t_src"]),
            _act(11, "Formalize", "formalize tier", ["t_model"]),
            _act(12, "Decompose", "decompose tier", ["t_dec"])]
ev_arts += [_art("t_src", "SourceCode", 10),
            _art("t_model", "IMLModel", 11, ["t_src"], {"symbols": ["tier"]}),
            _art("t_dec", "Decomp", 12, ["t_model"], {"region_count": 6}, target_symbol="tier")]
# tests for refund (generated, not necessarily via decomposition)
ev_acts += [_act(20, "GenerateTests", "generate tests for refund", ["r_tests"])]
ev_arts += [_art("r_tests", "Tests", 20, None, {"count": 14, "failing": 0}, target_symbol="refund")]
# a plain diff for config
ev_acts += [_act(30, "EditFile", "edit config", ["cfg_diff"])]
ev_arts += [_art("cfg_diff", "Diff", 30, None, {}, target_symbol="config")]
# a documentation note for onboarding
ev_acts += [_act(40, "WriteDoc", "document onboarding", ["ob_doc"])]
ev_arts += [_art("ob_doc", "Documentation", 40, None, {}, target_symbol="onboarding")]
add("Evidence types", "05-evidence-artifact-types.json", "Any artifact is evidence",
    "Five criteria, five kinds of evidence — a proof, a decomposition, a generated test suite, a plain "
    "diff, and a documentation note. Evidence need not be formal; a policy decides if it's strong enough.",
    trace("gc-evidence-types", "Evidence is any artifact in the component's lineage",
          ev_acts, ev_arts,
          goal("Ship the pricing change", [
              crit("c1", "price", "VerificationResult"),
              crit("c2", "tier", "Decomp"),
              crit("c3", "refund", "Tests"),
              crit("c4", "config", "Diff"),
              crit("c5", "onboarding", "Documentation"),
          ], scope=["price", "tier", "refund", "config", "onboarding"])))

# === GOVERNANCE ====================================================================================
# A high-stakes component backed only by a Diff → MET, but reasoning_required_for_high_stakes FAILS →
# not governed. This is exactly what "weakly specified" used to (crudely) flag — now a policy.
add("Governance", "06-high-stakes-needs-proof.json", "A diff isn't enough on a high-stakes path",
    "The criterion is met by a Diff, but settle is high-stakes and the policy demands a proof or a "
    "decomposition in lineage — so the goal is blocked (not governed). Rigor lives in the policy.",
    trace("gc-block-default", "Block by default: high-stakes edit needs formal backing",
          [_act(1, "EditFile", "edit settle", ["d1"], request={"path": "src/settle.py"})],
          [_art("d1", "Diff", 1, None, {}, target_symbol="settle")],
          goal("Change settlement", [crit("c1", "settle", "Diff", ["change settle"])],
               clauses=["change settle"], review=REVIEW_OK,
               policies={"policies": [POL_HIGH_STAKES]}, scope=["settle"]),
          high_stakes=["settle"]))

# Same trace, but the goal DISABLES the policy → recorded, not blocking → governed.
add("Governance", "07-policy-disabled.json", "Override: policy disabled (recorded)",
    "The same high-stakes diff, but the goal explicitly DISABLES the policy — an on-the-record override, "
    "never silent. The goal is governed again, and the disabled rule is visible in the contract.",
    trace("gc-disabled", "Disabled policy: an explicit, recorded override",
          [_act(1, "EditFile", "edit settle", ["d1"], request={"path": "src/settle.py"})],
          [_art("d1", "Diff", 1, None, {}, target_symbol="settle")],
          goal("Change settlement", [crit("c1", "settle", "Diff", ["change settle"])],
               clauses=["change settle"], review=REVIEW_OK,
               policies={"policies": [POL_HIGH_STAKES], "disabled": ["reasoning_required_for_high_stakes"]},
               scope=["settle"]),
          high_stakes=["settle"]))

# === FAITHFULNESS ==================================================================================
acts, arts, ev = verification_chain("settle", "proved", 1, "a")
add("Faithfulness", "08-uncovered-clause.json", "Uncovered intent clause",
    "The intent has two clauses but the acceptance covers only one — so even a proved, reviewed goal is "
    "NOT certified: the definition doesn't fully capture the intent.",
    trace("gc-uncovered", "An uncovered clause blocks certification",
          acts, arts,
          goal("Settlement conserves money and refunds are bounded",
               [crit("c1", "settle", "VerificationResult", ["conserve money"])],
               clauses=["conserve money", "bound refunds"], review=REVIEW_OK, scope=["settle"])))

acts, arts, ev = verification_chain("settle", "proved", 1, "a")
add("Faithfulness", "09-self-review.json", "Self-review can't certify",
    "The agent that authored the criteria is also the reviewer — a doer can't certify its own bar, so "
    "certified stays false. Certification needs a different principal.",
    trace("gc-self-review", "A doer cannot certify its own definition of done",
          acts, arts,
          goal("Settlement conserves money",
               [crit("c1", "settle", "VerificationResult", ["conserve money"], author="agent")],
               clauses=["conserve money"],
               review={"reviewed_by": "agent", "verdict": "approved", "at": "2026-07-25T01:00:00Z"},
               scope=["settle"])))


# ===================================================================================================
# RICH WALKTHROUGHS — full start-to-end stories with a steppable action flow (meta_actions) on the
# left. These read like a real session: understand → formalize → hit a wall → fix → prove → certify.
# ===================================================================================================

def ract(i, typ, label, rationale, mid, outputs=None, inputs=None, category="activity",
         result_summary=None, vg_result=None, request=None):
    a = {"id": i, "type": typ, "category": category, "label": label, "rationale": rationale,
         "inputs": inputs or [], "outputs": outputs or [], "evidence": [], "meta_action_id": mid}
    if result_summary:
        a["result_summary"] = result_summary
    if vg_result:
        a["vg_result"] = vg_result
    if request:
        a["request"] = request
    return a


def ma(mid, title, intent, action_ids, produced=None):
    return {"id": mid, "title": title, "intent": intent, "action_ids": action_ids,
            "source": "plan_declared", "status": "completed", "produced_artifact_ids": produced or []}


def rich_trace(trace_id, title, actions, meta_actions, artifacts, goal, residuals=None,
               policies=None, evals=None, files=None, high_stakes=None):
    return {
        "trace_id": trace_id, "spec_version": "1.7", "assistant": "codelogician", "model": "demo",
        "timestamp": "2026-07-25T00:00:00Z", "title": title,
        "trigger": {"type": "TaskReceived", "description": title},
        "actions": actions, "meta_actions": meta_actions, "artifacts": artifacts,
        "outcome": {"type": "ProcessCompleted", "summary": title},
        "goals": [goal], "residuals": residuals or [],
        "policies": policies or [], "policy_evaluations": evals or [],
        "files_modified": files or [],
        "metrics": {"total_actions": len(actions), "meta_action_count": len(meta_actions)},
        **({"high_stakes_paths": high_stakes} if high_stakes else {}),
    }


def story_idempotency():
    """Proof-first arc: a counterexample, a fix, a proof, a human sign-off — ends all-green."""
    A = [
        ract(1, "ReadFile", "read billing/capture.py", "Understand the capture path before changing it.",
             "m1", outputs=["src"]),
        ract(2, "AnalyzeCode", "trace the retry path", "Capture is called again on gateway retries — suspicious.",
             "m1"),
        ract(3, "Formalize", "autoformalize capture", "Lift capture into an IML model to reason about it.",
             "m2", inputs=["src"], outputs=["model"], category="reasoning"),
        ract(4, "DefineVG", "define VG: capture is idempotent", "State the property: re-capture must not double-charge.",
             "m2", inputs=["model"], outputs=["vg"], category="reasoning"),
        ract(5, "Verify", "verify idempotency — REFUTED", "ImandraX finds a counterexample: retry after partial refund double-charges.",
             "m3", inputs=["vg"], outputs=["vr1"], category="reasoning",
             result_summary="refuted — counterexample: retry after partial refund", vg_result={"status": "refuted"},
             request={"engine": "imandrax"}),
        ract(6, "AnalyzeCode", "diagnose the counterexample", "The guard keys on request id but not on refund state.",
             "m4"),
        ract(7, "EditFile", "add idempotency guard to capture", "Key the guard on (request_id, ledger_version).",
             "m4", inputs=["src"], outputs=["diff"]),
        ract(8, "Verify", "re-verify idempotency — PROVED", "With the guard, the property now holds for all inputs.",
             "m5", inputs=["vg"], outputs=["vr2"], category="reasoning",
             result_summary="proved", vg_result={"status": "proved"}, request={"engine": "imandrax"}),
        ract(9, "GenerateTests", "generate regression tests", "Pin the counterexample and boundaries as tests.",
             "m6", inputs=["vg"], outputs=["tests"]),
        ract(10, "RunTests", "run the suite — all pass", "18 tests, including the former counterexample.",
             "m6", result_summary="18 passed, 0 failing"),
        ract(11, "GitCommit", "commit the fix + proof", "Bind the reasoning record 1:1 to the commit.",
             "m6", outputs=["commit"]),
    ]
    M = [
        ma("m1", "Understand the capture path", "Read capture and find the retry path", [1, 2], ["src"]),
        ma("m2", "Formalize & specify idempotency", "Model capture and state the property", [3, 4], ["model", "vg"]),
        ma("m3", "First proof attempt — counterexample", "Verify and get refuted", [5], ["vr1"]),
        ma("m4", "Diagnose & fix the double-charge", "Find the missing guard and add it", [6, 7], ["diff"]),
        ma("m5", "Re-verify — proved", "Prove the property holds with the fix", [8], ["vr2"]),
        ma("m6", "Test, then commit", "Regression tests and commit", [9, 10, 11], ["tests", "commit"]),
    ]
    T = [
        _art("src", "SourceCode", 1, name="billing/capture.py"),
        _art("model", "IMLModel", 3, ["src"], {"symbols": ["capture"]}, name="capture (IML model)"),
        _art("vg", "VerificationGoal", 4, ["model"], {"goal_id": "vg", "property_name": "idempotent"},
             target_symbol="capture", name="idempotent"),
        _art("vr1", "VerificationResult", 5, ["vg"], {"goal_id": "vg", "status": "refuted",
             "counterexample": "retry after partial refund"}, name="idempotent — refuted"),
        _art("diff", "Diff", 7, ["src"], {}, target_symbol="capture", name="add idempotency guard"),
        _art("vr2", "VerificationResult", 8, ["vg"], {"goal_id": "vg", "status": "proved"}, name="idempotent — proved"),
        _art("tests", "Tests", 9, ["vg"], {"count": 18, "failing": 0}, target_symbol="capture", name="capture regression suite"),
        _art("commit", "Commit", 11, ["diff", "vr2"], {}, name="fix: idempotent capture"),
    ]
    R = [{"residual_id": "r1", "kind": "limitation", "severity": "high",
          "statement": "Idempotency is proved for single-threaded transition application; concurrent "
                       "capture/refund interleavings are not modeled.",
          "target": {"target_type": "artifact", "target_id": "vr2"},
          "suggested_check": "Add a concurrency model or a DB-level unique constraint on the guard key.",
          "status": "open"}]
    g = goal("Make payment capture idempotent",
             [crit("c1", "capture", "VerificationResult", ["capture is idempotent"])],
             clauses=["capture is idempotent"], review=REVIEW_OK,
             policies={"policies": [POL_REPROVED]}, scope=["capture"])
    return rich_trace("gc-walk-idempotency", "Walkthrough: prove payment capture is idempotent",
                      A, M, T, g, residuals=R, files=["billing/capture.py"])


def story_tax_brackets():
    """Decomposition-first arc: decompose the input space, cover regions, catch a boundary bug in the
    tests, fix it, then prove monotonicity — the 'edge cases matter' loop. Ends all-green."""
    A = [
        ract(1, "ReadFile", "read pricing/tax.py", "Read the bracket table and rate logic.", "m1", outputs=["src"]),
        ract(2, "AnalyzeCode", "identify the bracket boundaries", "Boundaries at 10k/40k/85k are the risky inputs.",
             "m1"),
        ract(3, "Formalize", "autoformalize tax_bracket", "Model the piecewise bracket function in IML.",
             "m2", inputs=["src"], outputs=["model"], category="reasoning"),
        ract(4, "Decompose", "decompose the input space", "ImandraX splits the domain into 7 regions (each bracket + boundaries).",
             "m2", inputs=["model"], outputs=["dec"], category="reasoning",
             result_summary="7 regions incl. all bracket boundaries"),
        ract(5, "GenerateTests", "generate one test per region", "Cover every region, boundaries included.",
             "m3", inputs=["dec"], outputs=["tests"]),
        ract(6, "RunTests", "run the suite — boundary FAILS", "Region at exactly 40000 computes the wrong rate (off-by-one).",
             "m3", result_summary="1 failing: rate at income == 40000"),
        ract(7, "AnalyzeCode", "diagnose the boundary", "The comparison is > where it must be >=.", "m4"),
        ract(8, "EditFile", "fix the boundary comparison", "Change > to >= at the bracket edge.", "m4",
             inputs=["src"], outputs=["diff"]),
        ract(9, "RunTests", "re-run — all pass", "All 7 region tests pass, boundary included.", "m4",
             result_summary="7 passed, 0 failing"),
        ract(10, "DefineVG", "define VG: tax is monotonic in income", "More income never means less tax after-bracket.",
             "m5", inputs=["model"], outputs=["vg"], category="reasoning"),
        ract(11, "Verify", "verify monotonicity — PROVED", "Holds across all regions.", "m5",
             inputs=["vg"], outputs=["vr"], category="reasoning", result_summary="proved",
             vg_result={"status": "proved"}, request={"engine": "imandrax"}),
        ract(12, "GitCommit", "commit the fix + evidence", "Bind the record to the commit.", "m6", outputs=["commit"]),
    ]
    M = [
        ma("m1", "Map the bracket logic", "Read tax.py and mark the boundaries", [1, 2], ["src"]),
        ma("m2", "Formalize & decompose the input space", "Model tax_bracket and split into regions", [3, 4],
           ["model", "dec"]),
        ma("m3", "Cover regions with tests — a boundary fails", "One test per region; the 40k edge fails", [5, 6],
           ["tests"]),
        ma("m4", "Fix the boundary off-by-one", "Correct the comparison and re-run", [7, 8, 9], ["diff"]),
        ma("m5", "Prove monotonicity across regions", "State and prove the ordering property", [10, 11],
           ["vg", "vr"]),
        ma("m6", "Commit", "Bind the record to the commit", [12], ["commit"]),
    ]
    T = [
        _art("src", "SourceCode", 1, name="pricing/tax.py"),
        _art("model", "IMLModel", 3, ["src"], {"symbols": ["tax_bracket"]}, name="tax_bracket (IML model)"),
        _art("dec", "Decomposition", 4, ["model"], {"region_count": 7, "regions": [{
            "function": "tax_bracket", "count": 7, "regions": [
                {"label_path": "R1", "invariant": "tax = 0", "constraints": ["income <= 0"]},
                {"label_path": "R2", "invariant": "tax = income * 0.10", "constraints": ["0 < income", "income <= 10000"]},
                {"label_path": "R3", "invariant": "tax = 1000 + (income-10000)*0.20", "constraints": ["10000 < income", "income <= 40000"]},
                {"label_path": "R4 (boundary)", "invariant": "tax = 1000 + (income-10000)*0.20", "constraints": ["income = 40000"]},
                {"label_path": "R5", "invariant": "tax = 7000 + (income-40000)*0.30", "constraints": ["40000 < income", "income <= 85000"]},
                {"label_path": "R6", "invariant": "tax = 20500 + (income-85000)*0.37", "constraints": ["85000 < income"]},
                {"label_path": "R7", "invariant": "tax >= 0", "constraints": ["income is integer"]},
            ]}]}, target_symbol="tax_bracket", name="tax_bracket regions (7)"),
        _art("tests", "GeneratedTests", 5, ["dec"], {"count": 7, "failing": 0}, target_symbol="tax_bracket",
             name="per-region tests"),
        _art("diff", "Diff", 8, ["src"], {}, target_symbol="tax_bracket", name="fix boundary comparison"),
        _art("vg", "VerificationGoal", 10, ["model"], {"goal_id": "vg", "property_name": "monotonic"},
             target_symbol="tax_bracket", name="monotonic in income"),
        _art("vr", "VerificationResult", 11, ["vg"], {"goal_id": "vg", "status": "proved"}, name="monotonic — proved"),
        _art("commit", "Commit", 12, ["diff", "vr", "tests"], {}, name="fix: tax bracket edge cases"),
    ]
    R = [{"residual_id": "r1", "kind": "assumption", "severity": "medium",
          "statement": "Rounding is assumed banker's rounding at 2 decimals; other rounding modes are out of scope.",
          "target": {"target_type": "artifact", "target_id": "vr"},
          "suggested_check": "Confirm the ledger's configured rounding mode matches.", "status": "open"}]
    g = goal("Get the tax-bracket edge cases right",
             [crit("c1", "tax_bracket", "Decomposition", ["cover every bracket region"]),
              crit("c2", "tax_bracket", "VerificationResult", ["brackets are monotonic in income"])],
             clauses=["cover every bracket region", "brackets are monotonic in income"], review=REVIEW_OK,
             policies={"policies": [POL_GENERATED_TESTS_DECOMP]}, scope=["tax_bracket"])
    return rich_trace("gc-walk-tax-brackets", "Walkthrough: get the tax-bracket edge cases right",
                      A, M, T, g, residuals=R, files=["pricing/tax.py"])


add("Walkthroughs", "W1-idempotency-proof-arc.json", "Prove payment capture is idempotent (proof-first)",
    "A full session: read the code, formalize, hit a COUNTEREXAMPLE, diagnose and fix it, re-verify to a "
    "PROOF, add regression tests, and get a non-doer sign-off. Step through the flow on the left. "
    "Ends met ∧ governed ∧ certified, with one honest residual (concurrency).",
    story_idempotency())
add("Walkthroughs", "W2-tax-brackets-decomposition-arc.json", "Get tax-bracket edge cases right (decomposition-first)",
    "The 'edge cases matter' loop: formalize, DECOMPOSE the input space into regions, cover them with "
    "tests, catch a boundary off-by-one, fix it, then PROVE monotonicity. Governed by 'generated tests "
    "must be decomposition-backed'. Ends met ∧ governed ∧ certified, with a rounding-mode assumption.",
    story_tax_brackets())


def walkthrough_sidecar(tr):
    """Turn a rich trace into a STEPPABLE session→trace record: for each meta-step, the developer's
    actions (left pane) and the trace it has produced so far, with the three axes re-resolved on the
    trace PREFIX (right pane). Certification is applied only at the final step, so `certified` flips
    when the human signs off — you watch met/governed/certified evolve as the story unfolds."""
    metas = tr["meta_actions"]
    a_by_id = {a["id"]: a for a in tr["actions"]}
    art_by_id = {a["artifact_id"]: a for a in tr["artifacts"]}
    steps, seen_actions, produced = [], [], []
    for k, m in enumerate(metas):
        seen_actions += m["action_ids"]
        produced += m.get("produced_artifact_ids", [])
        sub_goal = copy.deepcopy(tr["goals"][0])
        if k < len(metas) - 1:
            sub_goal.pop("criteria_review", None)  # the sign-off is the LAST beat
        sub = {**{key: tr[key] for key in tr if key not in ("actions", "artifacts", "goals", "meta_actions")},
               "actions": [a_by_id[i] for i in seen_actions if i in a_by_id],
               "artifacts": [art_by_id[p] for p in produced if p in art_by_id],
               "meta_actions": metas[:k + 1], "goals": [sub_goal]}
        steps.append({
            "id": m["id"], "title": m["title"], "intent": m.get("intent"),
            "actions": [{"type": a_by_id[i].get("type"), "label": a_by_id[i].get("label"),
                         "result": a_by_id[i].get("result_summary")}
                        for i in m["action_ids"] if i in a_by_id],
            "produced": [{"id": p, "type": art_by_id[p]["artifact_type"]}
                         for p in m.get("produced_artifact_ids", []) if p in art_by_id],
            "axes_after": axes_of(sub),
        })
    return {"trace_id": tr["trace_id"], "title": tr["title"], "final_axes": axes_of(tr),
            "residuals": [{"kind": r.get("kind"), "severity": r.get("severity"),
                           "statement": r.get("statement")} for r in tr.get("residuals", [])],
            "steps": steps}


def main():
    os.makedirs(OUT, exist_ok=True)
    manifest = {"description": "Internal Goal Contract gallery — worked examples spanning the model "
                "(three axes, evidence types, governance, faithfulness). Generated by make_goal_gallery.py.",
                "groups": []}
    by_group = {}
    for group, fname, name, summary, tr in CASES:
        # Serve the ENRICHED trace: the viewer doesn't run enrich, so this is what makes the Goals tab
        # show resolved progress (met/governed/certified) instead of 0%. The in-memory raw `tr` still
        # feeds the sidecar and axes below.
        with open(os.path.join(OUT, fname), "w") as f:
            json.dump(enrich(copy.deepcopy(tr)), f, indent=2, ensure_ascii=False)
            f.write("\n")
        entry = {"file": fname, "name": name, "summary": summary, "axes": axes_of(tr)}
        # Walkthroughs also get a steppable session→trace sidecar for the split-screen view.
        if group == "Walkthroughs":
            walk_name = fname.replace(".json", ".walk.json")
            with open(os.path.join(OUT, walk_name), "w") as f:
                json.dump(walkthrough_sidecar(tr), f, indent=2, ensure_ascii=False)
                f.write("\n")
            entry["walk"] = walk_name
        by_group.setdefault(group, []).append(entry)
    for group in ["Walkthroughs", "Three axes", "Evidence types", "Governance", "Faithfulness"]:
        manifest["groups"].append({"group": group, "examples": by_group[group]})
    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {len(CASES)} examples + manifest to {OUT}")


if __name__ == "__main__":
    main()

"""Build the trace WIRE schema (JSON Schema 2020-12) for the newest Trace Spec, 1.15: `ponens/schema/trace.v1_15.json`.

`trace.v1_14.json` beside it is the 1.14 projection, frozen when 1.15 was drafted; 1.15 only adds (every valid
1.14 trace is a valid 1.15 one), so traces of either version are checked against this one.

The interchange projection of TRACE_SPEC_v1_15 (§16): what a trace looks like on the wire, as ponens
reads and writes it - not the canonical OCaml model. Where the spec's prose and ponens' code disagree on a
spelling, the code wins, because it is what every consumer reads; each such place says so in its
description. The rules applied:

- Discriminators serialise as lowercase snake_case without their constructor prefix (§13.6, §16.1):
  `VrProved` -> `proved`, `GoalActive` -> `active`, `PartiallyReproducible` -> `partially_reproducible`.
  Two exceptions, as ponens writes them: action and artifact types keep their constructor names
  (`EditFile`, `VerificationResult`), and so do event types (`TaskReceived`).
- An `option` field may be absent or null; a `list` is a list (canonically `[]`).
- A vocabulary is CLOSED where the spec or ponens treats it as closed (validate_trace, transitions.py,
  the residual sets); OPEN, with its known values listed, where ponens reads any name (action and
  artifact types, oracle types, event types).
- Extra properties are allowed everywhere - an interchange format must not reject a producer's
  additions. `tools/strict_schema.py` derives a STRICT variant that forbids them, to LIST what a
  producer adds beyond the spec; it is an audit tool, not a validity bar.

Run:  python3 tools/build_trace_schema.py          (writes the schema)
      python3 tools/build_trace_schema.py --check  (exit 1 when the committed file differs)
"""

import json
import pathlib
import sys

OUT = pathlib.Path(__file__).resolve().parent.parent / "ponens" / "schema" / "trace.v1_15.json"


# ---- helpers -----------------------------------------------------------------------------------

def ref(name):
    return {"$ref": f"#/$defs/{name}"}


def S(desc=None, **kw):
    return {"type": "string", **kw, **({"description": desc} if desc else {})}


def I(desc=None):
    return {"type": "integer", **({"description": desc} if desc else {})}


def B(desc=None):
    return {"type": "boolean", **({"description": desc} if desc else {})}


def N(desc=None):
    return {"type": "number", **({"description": desc} if desc else {})}


def L(items, desc=None):
    return {"type": "array", "items": items, **({"description": desc} if desc else {})}


def E(values, desc=None):
    return {"enum": list(values), **({"description": desc} if desc else {})}


def opt(s):
    """An `option` field: absent, null, or the value."""
    return {"anyOf": [s, {"type": "null"}]}


def O(props, required=(), desc=None):
    """An object. Optional scalar/object properties accept null (an `option`); lists do not."""
    out = {"type": "object", "properties": {k: (v if k in required or v.get("type") == "array" else opt(v))
                                             for k, v in props.items()}}
    if required:
        out["required"] = list(required)
    if desc:
        out["description"] = desc
    return out


def merge(*parts):
    p = {}
    for x in parts:
        p.update(x)
    return p


STRS = L(S())
ANY = {}                       # any JSON value
ID = S(minLength=1)
INT_OR_STR = {"type": ["integer", "string"]}


# ---- vocabularies ------------------------------------------------------------------------------

ACTION_CATEGORIES = ("activity", "gateway", "reasoning", "governance")
DETERMINISM = ("deterministic", "mixed", "nondeterministic")
EVIDENCE_STRENGTH = ("proof", "sat", "tests", "static_analysis", "attested")       # oracles.py, locked
CONFIDENCE = ("high", "medium", "low")
RESIDUAL_KINDS = ("assumption", "unverified", "out_of_scope", "limitation", "open_question", "defeater",
                  "needs_rereasoning", "coverage_regression", "goal_divergence")   # trace.py RESIDUAL_KINDS
DEFEATER_KINDS = ("rebuts", "undermines", "undercuts")
SEVERITIES = ("info", "low", "medium", "high", "critical")
RESIDUAL_STATUSES = ("open", "acknowledged", "addressed", "waived")
RESIDUAL_SOURCES = ("agent_declared", "policy_derived", "tool_inferred", "reviewer_added", "binding")
# 1.15: a residual may be about code, not only about the trace - a declaration, a file, or a declared subject.
TARGET_TYPES = ("trace", "action", "artifact", "policy", "policy_evaluation", "reference_artifact", "symbol", "file", "subject")
META_STATUSES = ("completed", "partial", "abandoned")
META_SOURCES = ("plan_declared", "turn_segmented", "intent_inferred", "curated")
VR_STATUSES = ("proved", "refuted", "sat", "unknown", "bounded")                    # bounded: 1.15
PROPERTY_STATUSES = ("pending", "proved", "refuted", "unknown")
VG_KINDS = ("verify", "instance", "theorem", "lemma", "axiom")
CONFORMANCE_STATUSES = ("passed", "failed", "partial", "unknown")
COSIM_STATUSES = ("matched", "mismatched", "partial", "error")
FORMALIZATION_STATUSES = ("transparent", "opaque", "failed")
REPRO_STATUSES = ("not_reproducible", "partially_reproducible", "reproducible")
REPRO_KINDS = ("deterministic_replay", "tool_reexecution", "procedural_replay", "manual_reproduction", "not_reproducible")
PROCEDURE_KINDS = ("command", "workflow", "reference", "manual")
ENV_KINDS = ("toolchain", "container", "service", "external_system")
COMMENT_STATUSES = ("open", "resolved")
REVIEW_STATUSES = ("open", "acknowledged", "resolved", "waived")
RELATIONSHIPS = ("supersedes", "reruns", "derived_from", "same_task", "same_pr", "policy_recheck_of",
                 "conformance_recheck_of", "forked_from", "related_to")
CHAIN_STATUSES = ("active", "superseded", "archived")
GOAL_STATUSES = ("scratch", "active", "done", "abandoned", "superseded")            # superseded: 1.15
ACCEPTANCE_KINDS = ("change", "property", "obligation", "gap")
ACCEPTANCE_STATUSES = ("todo", "doing", "done", "blocked")
POLICY_VERDICTS = ("passed", "failed", "warning", "not_applicable")                  # transitions.py
RESOLUTION_STATUSES = ("acknowledged", "addressed", "waived")                         # never `open`, §13.3a
AMENDMENT_CHANGES = ("item_withdrawn", "goal_withdrawn", "goal_replaced", "criteria_reviewed")
CRITERIA_VERDICTS = ("unreviewed", "approved", "changes-requested")                   # transitions.py spelling
CARRIED_BASES = ("closure-disjoint", "uninterpreted-opaque")                         # merge.py spelling
CONFORMANCE_KINDS = ("refinement", "equivalence", "invariant")
REF_VG_KINDS = ("conformance", "invariant", "refinement")
SIG_ALGOS = ("ssh", "gpg", "sigstore")
EVENT_TYPES = ("TaskReceived", "TriggeredByEvent", "ProcessCompleted", "ProcessAborted", "ProcessInterrupted")


# ---- defs --------------------------------------------------------------------------------------

D = {}

D["target_ref"] = O({"target_type": E(TARGET_TYPES, "§14.1 - what is targeted"),
                     "target_id": {"type": ["string", "integer"],
                                   "description": "the id of the targeted object - an action's is its integer id (absent for the trace itself); "
                                                  "a symbol's is the declaration's name, a file's its path, a subject's its name (1.15)"},
                     "path": S("symbol (1.15): the file that declares it"),
                     "subject_kind": S("subject (1.15): what kind of thing it is - protocol, service, table, endpoint, ...")},
                    required=("target_type",), desc="§14.1 - a reference to a trace object.")

D["oracle_attribution"] = O({
    "id": ID,
    "oracle_type": S("§10.12 - reasoner | tester | analyzer | monitor | judge | attestor, or a registered name: an "
                     "OPEN vocabulary (a consumer warns on an unknown name, never rejects it)"),
    "evidence_strength": E(EVIDENCE_STRENGTH, "the strength of THIS result, strongest first - absent on an unknown or error verdict"),
    "version": S(), "specializes": S("for a non-standard oracle_type: the standard type it specializes"),
}, required=("id",), desc="§10.12 - the oracle that produced an evidence payload.")

D["fingerprint"] = O({
    # reasoner profile (§10.4a, 1.9) and the generic evidence fingerprint (1.12); either names are accepted
    "task_checksum": S(), "task_shape": S(), "target_symbol": S(), "engine": S(), "engine_version": S(),
    "model_artifact_id": S(), "model_revision": I(),
    "subject_checksum": S(), "subject_shape": S(), "subject_ref": S(), "oracle_id": S(), "oracle_version": S(),
    "observed_at": S(), "valid_until": S(),
}, desc="§10.4a - the freshness anchor: a reasoning_fingerprint (task_*) or an evidence_fingerprint (subject_*).")

D["region"] = O({"constraints": STRS, "invariant": S(), "model": ANY, "model_eval": S(),
                 # 1.15: whether the invariant was checked to hold over the region, and a point in it with the model's output there
                 "invariant_checked": B("1.15 - the invariant was checked to hold over the whole region"),
                 "sample": {"type": "object", "description": "1.15 - a point in the region: argument -> value"},
                 "sample_output": S("1.15 - the model's output at the sample"),
                 # as ponens' demos write a region (pre-1.4 decomposition shape)
                 "id": INT_OR_STR, "constraint": S(), "count": I(), "function": S(), "regions": L(ANY)},
                desc="§10.5 - one region of a state-space analysis.")
D["property_item"] = O({"name": S(), "status": E(PROPERTY_STATUSES), "src": S(), "note": S()},
                       desc="§10.3 - a property under a verification goal.")
D["generated_test"] = O({"name": S(), "region_index": I(), "constraints": STRS, "inputs": ANY, "expected": ANY, "code": S()},
                        desc="§10.8 - one generated test.")

# Keys any evidence payload may carry that ponens reads to root it in a component (GOAL_CONTRACT §4.1) and to
# grade it (§10.12): what it is about, what it says it checked, who produced it, how fresh it is.
BASE_PAYLOAD = {
    "target_symbol": S("the declaration this artifact is about - read first when rooting it in a component"),
    "symbols": STRS, "symbol": S(), "function": S(), "file": S(), "path": S(), "files": STRS,
    "subject": {"anyOf": [S(), O({"kind": S(), "name": S()}, required=("name",))],
                "description": "a named subject this evidence is about: its name, or stated in full {kind, name} (goals.py)"},
    "subjects": L(ANY),
    "component_ids": STRS, "target_component_id": S(),
    "description": S(), "property": S(), "properties": L(ANY),
    "satisfies": S("the acceptance criterion this artifact was produced for (GOAL_CONTRACT §4)"),
    "oracle": ref("oracle_attribution"), "evidence_strength": E(EVIDENCE_STRENGTH), "fingerprint": ref("fingerprint"),
    "confirmed": B("false: someone was asked to reproduce this result and could not - it establishes nothing yet"),
}


def payload(props, required=(), desc=None, base=True):
    return O(merge(BASE_PAYLOAD if base else {}, props), required=required, desc=desc)


D["formalization_payload"] = payload({"status": E(FORMALIZATION_STATUSES), "src_lang": S(), "src_code": S(), "formal_code": S(),
                                      "model_language": S()}, desc="§10.1")
WITNESSED_BY = S("1.15 - who ran the reasoner and recorded what it answered: a platform (e.g. grounds) or the producer itself; "
                 "absent when the producer reports a result it did not witness")
D["formal_model_payload"] = payload({"model_language": S("the modelling language, e.g. iml"), "formal_code": S(), "scope": S(),
                                     "declarations": L(O({"name": S(), "type": S()}, required=("name",)), "1.15 - the declarations the reasoner admitted, with their types"),
                                     "engine": S("1.15 - the reasoner that admitted the model"), "witnessed_by": WITNESSED_BY,
                                     "checksum": S("the model's content checksum (§11.2)"),
                                     # IMLModel, the pre-1.4 name FormalModel aliases (TYPE_SYNONYMS), as ponens' demos still write it
                                     "iml_code": S("IMLModel (legacy): the IML"), "src_code": S(), "src_lang": S(),
                                     "status": S("IMLModel (legacy): transparent | opaque | failed | proved")},
                                    desc="§10.2 - also the payload of an `IMLModel` (the legacy name; TYPE_SYNONYMS).")
D["verification_goal_payload"] = payload({
    "goal_id": INT_OR_STR, "goal_revision": I(), "kind": E(VG_KINDS), "src": S(), "formula": S(),
    "target_artifact_id": S(), "property_name": S(), "model_symbols": L(S(), "§10.3 (1.14) - for a result about a SUBJECT, the model definitions its interface maps to"),
    "statement": S("1.15 - the property in plain language, as the goal's author stated it"),
    "within_subject": S("1.15 - the declared subject this goal is about, when it is about one"),
}, desc="§10.3")
D["verification_result_variant"] = O({
    "proved": O({"proof_pp": S(), "properties": L(ref("property_item"))}),
    "refuted": O({"counterexample": S()}),
    "sat": O({"model": O({"m_type": E(("instance_model", "counterexample_model")), "src": S()})}),
    "unknown": O({"note": S()}),
    "bounded": O({"bounds": STRS, "note": S()}),
}, desc="§10.4 - the verdict's detail, tagged by its status.")
D["verification_result_payload"] = payload({
    "goal_id": INT_OR_STR, "goal_artifact_id": S("the VerificationGoal artifact this result answers"),
    "status": E(VR_STATUSES, "§10.4 - proved | refuted | sat | unknown | bounded (1.15: holds within the stated bounds - never a proof)"),
    "engine": S(), "engine_version": S(), "completed_at": S(),
    "result": ref("verification_result_variant"), "counterexample": S(), "kind": S(),
    "bounds": L(S(), "1.15 - for a bounded result: the bounds it holds within, in words (e.g. runs of length up to 10)"),
    "witnessed_by": WITNESSED_BY, "model_checksum": S("1.15 - the checksum of the model the result is about (§11.2)"),
    "verification_id": S("1.15 - the producer's id for the recorded result, so it can be cited"),
    "formula": S("1.15 - the formula as the reasoner checked it"), "job_ref": S("1.15 - the reasoner's own reference for the run"),
}, desc="§10.4")
D["state_space_analysis_result_payload"] = payload({
    "target_artifact_id": S(), "analysis_kind": S("e.g. region_decomposition"), "analysis_revision": I(), "complete": B(),
    "regions": L(ref("region")), "coverage_summary": S(), "notes": S(), "engine": S(), "engine_version": S(),
    "target_function": S("Decomposition (legacy): the model function decomposed"), "region_count": I(),
    "verification_id": S("1.15 - the producer's id for the recorded analysis, so it can be cited"),
}, desc="§10.5 - also the payload of a `Decomposition` (the legacy name; TYPE_SYNONYMS).")
D["conformance_result_payload"] = payload({
    "reference_artifact_id": ID, "target_artifact_id": ID,
    "status": E(CONFORMANCE_STATUSES), "engine": S(), "findings": STRS, "note": S(),
    # §11.2 (1.13) - conformance against a reference
    "entry_symbol": S("the reference-model symbol"), "conformance_kind": E(CONFORMANCE_KINDS),
    "reference_version": S(), "reference_checksum": S(),
    # 1.15 - the run itself, and whether the model takes what the code takes
    "command": S("1.15 - the command that ran the tests against the code"), "passed": I("1.15"), "failed": I("1.15"),
    "interface": O({"match": B("null: it could not be checked"), "reason": S()}, desc="1.15 - the model's interface read against the code's"),
}, required=("reference_artifact_id", "target_artifact_id", "status"), desc="§10.6, §11.2")
D["cosimulation_result_payload"] = payload({
    "target_artifact_id": ID, "input_artifact_ids": STRS, "status": E(COSIM_STATUSES), "engine": S(),
    "replayed_steps": I(), "divergence_points": L(ANY), "summary": S(), "observations": STRS,
}, required=("target_artifact_id", "status"), desc="§10.7")
D["generated_tests_payload"] = payload({
    "language": S(), "source_analysis_artifact_id": S("§10.8 - the analysis the tests were generated from"),
    "tests": L(ref("generated_test")), "count": I(), "failing": I(),
    "source_decomposition_artifact_id": S("legacy name of source_analysis_artifact_id, as ponens' demos write it"),
}, desc="§10.8 (`function_` in the canonical model is `function` on the wire)")
D["reproduction_bundle_payload"] = payload({"entry_action_ids": L(I()), "artifact_ids": STRS, "environment_ids": STRS, "notes": S()},
                                           desc="§10.10")
D["observation_payload"] = payload({
    "statement": S("the fact, in plain language", minLength=1), "source": S("the source id: a database, a feed, a system", minLength=1),
    "query": S(), "value": ANY, "observed_at": S(), "valid_until": S(), "confidence": E(CONFIDENCE),
}, required=("statement", "source"), desc="§10.11 (1.12) - a monitor's evidence; graded `attested`, never higher.")
D["carried_forward_payload"] = payload({
    "result_id": ID, "basis": E(CARRIED_BASES, "§15.3 - as ponens writes it (merge.py)"), "closure": STRS, "via_assumptions": STRS,
    # ORACLE_SPEC v0.2 §6, as merge.py writes them: the carried result's strength, and a stronger one from THEIRS
    "strength": E(EVIDENCE_STRENGTH), "preferred_result_id": S(), "theirs_strength": E(EVIDENCE_STRENGTH),
}, required=("result_id", "basis"), desc="§15.3")
RESIDUAL_PROPS = {
    "residual_id": S("1.15 - the residual's own id, stable across revisions of its artifact (a resolution names it, §13.3a)"),
    "kind": E(RESIDUAL_KINDS), "defeater_kind": E(DEFEATER_KINDS, "set iff kind = defeater"),
    "statement": S("the gap (or, for a defeater, the challenge), in plain language"), "severity": E(SEVERITIES),
    "target": ref("target_ref"), "related_artifact_ids": STRS, "rationale": S(), "suggested_check": S(),
    "source": E(RESIDUAL_SOURCES, "§13.1, and `binding` (§11.2: the interpretation a binding chose)"),
    "status": E(RESIDUAL_STATUSES), "introduced_by_action_id": I(), "tags": STRS,
    # read by ponens' residual surface (lineage._RESIDUAL_PAYLOAD_KEYS)
    "derived": B("a derived (computed) gap, not a declared one"), "summary": S(), "counterexample": S(),
    "retires_when": ANY, "record_size_at_declaration": I(),
}
D["residual_payload"] = payload(RESIDUAL_PROPS, required=("kind", "statement"), desc="§13.1 - a residual's fields, in the payload of a `Residual` artifact.")
D["residual_resolution_payload"] = payload({
    "residual_id": ID, "status": E(RESOLUTION_STATUSES, "never `open` (§13.3a)"), "justification": S(minLength=1),
    "by": S(), "at": S(), "evidence_artifact_ids": STRS,
}, required=("residual_id", "status", "justification"), desc="§13.3a (1.14)", base=False)
D["goal_amendment_payload"] = payload({
    "goal_id": ID, "change": E(AMENDMENT_CHANGES), "item_id": S(), "was": ANY, "reason": S(minLength=1), "by": S(), "at": S(),
}, required=("goal_id", "change", "reason"), desc="§18.3a (1.14)", base=False)
# Abstract in the canonical model (§10.9: "may be refined by implementations"): what ponens reads of a command's
# result, the rest open.
D["command_result_payload"] = payload({"command": S(), "status": S(), "exit_code": I(), "passed": I(), "failed": I(),
                                       "findings": ANY, "tool": S(), "kind": S()}, desc="§10.9 - open; refined by implementations.")
# Common-only artifacts (§7.1: no payload in the canonical model) - on the wire their payload, when present, carries
# what ponens reads to root them (a Diff's `target_symbol`, §18.3 1.14) and is otherwise open.
COMPONENT_PROPS = {"signature_changed": B(), "language": S()}
D["component_payload"] = payload(COMPONENT_PROPS,
                                 desc="the payload of an artifact with none in the canonical model (Diff, AnalysisNote, …) - "
                                      "what ponens reads to root it, otherwise open")
# 1.15 §10.13 - what a formal model is made from: a SourceCode, Documentation or UserInstruction artifact may say it is a
# model's input, read and fingerprinted at a commit, so a change to it can be found and the model looked at again.
MODEL_INPUT_PROPS = {
    "input_id": S("1.15 §10.13 - the input's own id"), "input_of": S("1.15 §10.13 - what it is an input of, e.g. formalization"),
    "kind": E(("code", "document", "requirement", "package", "model"), "1.15 §10.13 - what kind of input"),
    "grain": S("1.15 §10.13 - how much of it was read and fingerprinted: declaration | file | text | section | unread"),
    "checksum": S("1.15 §10.13 - its fingerprint when read (absent: it could not be read)"),
    "read_at": S("1.15 §10.13 - the commit it was read at"), "commit": S("the commit the artifact is of"),
    "why": S("1.15 §10.13 - what of it the model encodes"), "note": S("1.15 §10.13 - what the reader could not do, in words"),
    "ref": S("1.15 §10.13 - a requirement: the goal, criterion or ticket it is"), "section": S("1.15 §10.13 - a document: the section meant"),
    "package": S("1.15 §10.13 - a package: its name"), "version": S("1.15 §10.13 - a package: the version assumed"),
    "ecosystem": S("1.15 §10.13 - a package: npm, pypi, go, cargo, ..."),
}
D["source_payload"] = payload(merge(COMPONENT_PROPS, MODEL_INPUT_PROPS),
                              desc="SourceCode, Documentation, UserInstruction: what ponens reads to root it, and - when it is a model's input - "
                                   "the input's fingerprint (1.15 §10.13); otherwise open")
D["search_results_payload"] = payload(merge(COMPONENT_PROPS, {
    "query": S("1.15 - what was searched for"), "scope": L(S(), "1.15 - the paths searched (none: the whole repository)"),
    "commit": S("1.15 - the commit searched"), "matches": I("1.15 - how many matches"),
    "hits": L(O({"path": S(), "line": I(), "text": S()}), "1.15 - the matches, or the first of them"),
}), desc="SearchResults (1.15): the search, where and at which commit, and what it found")
D["plan_payload"] = payload(merge(COMPONENT_PROPS, {
    "approach": S("1.15 - how the work will be done, in words"), "intended_files": L(S(), "1.15 - the files the plan means to touch"),
}), desc="Plan (1.15): the approach and the files it means to touch")

TYPED_ARTIFACTS = {
    "Formalization": "formalization_payload",
    "FormalModel": "formal_model_payload", "IMLModel": "formal_model_payload",
    "VerificationGoal": "verification_goal_payload",
    "VerificationResult": "verification_result_payload",
    "StateSpaceAnalysisResult": "state_space_analysis_result_payload", "Decomposition": "state_space_analysis_result_payload",
    "ConformanceResult": "conformance_result_payload",
    "CoSimulationResult": "cosimulation_result_payload",
    "GeneratedTests": "generated_tests_payload",
    "CommandResult": "command_result_payload",
    "ReproductionBundle": "reproduction_bundle_payload",
    "Observation": "observation_payload",
    "CarriedForward": "carried_forward_payload",
    "Residual": "residual_payload",
    "ResidualResolution": "residual_resolution_payload",
    "GoalAmendment": "goal_amendment_payload",
    **{t: "source_payload" for t in ("UserInstruction", "SourceCode", "Documentation")},
    "SearchResults": "search_results_payload", "Plan": "plan_payload",
    **{t: "component_payload" for t in ("AnalysisNote", "Diff", "UserApproval", "Commit")},
}

KNOWN_ARTIFACT_TYPES = sorted(set(TYPED_ARTIFACTS))
D["artifact"] = {
    **O({
        "artifact_id": ID,
        "artifact_type": S("the artifact's kind, discriminating its payload (§7.1). OPEN: ponens reads any name; the "
                           "payload of a known type is checked. Known: " + ", ".join(KNOWN_ARTIFACT_TYPES), minLength=1),
        "artifact_role": S("§7.1 - formal_model | approved_reference | reasoning_goal | reasoning_result | proof | "
                           "counterexample | state_space_analysis | generated_test | audit_evidence | a custom role"),
        "name": S(), "format": S(), "revision": I(),
        "producer_action_id": I("the action that produced it"),
        "derived_from": L(S(), "its immediate inputs - artifact or reference-artifact ids (§7.3, §11.2)"),
        "supersedes": {"type": ["string", "array"], "items": S(), "description": "§7.3 - a replaced predecessor (one id; a list is tolerated)"},
        "content_ref": S(), "summary": S(),
        "component_id": S("§7.1 (1.10) - a durable identity for the code component, stable across rename/move"),
        "metadata": {"type": "object"},
        "payload": {"type": "object"},
    }, required=("artifact_id", "artifact_type")),
    "description": "§7 - a typed artifact; its `payload` is checked by `artifact_type` for every known type.",
    "allOf": [{"if": {"properties": {"artifact_type": {"const": t}}, "required": ["artifact_type"]},
               "then": {"properties": {"payload": ref(p)}}} for t, p in TYPED_ARTIFACTS.items()],
}

D["evidence"] = O({"type": S("§9.1 - file_ref | url_ref | command_output | search_result"), "ref": S(), "exit_code": I()},
                  desc="§9.1 - evidence an action cites (`typ`/`ref_` in the canonical model).")
D["observation"] = O({"observation_id": S(), "derived_from": STRS, "statement": S(), "confidence": E(CONFIDENCE)},
                     required=("statement",), desc="§9.2 - a statement an action held while working (not the Observation artifact).")
D["execution"] = O({"tool": S(), "version": S(), "method": S(), "determinism": E(DETERMINISM), "duration_ms": I(), "cost": N()},
                   desc="§8.3")
D["decision_option"] = O({"label": S(), "chosen": B(), "rejected_because": S(), "next_action_id": I()}, desc="§8.1 - a gateway's option")
D["replay_check"] = O({"kind": E(("json_path",)), "path": S("dotted, with numeric indices"), "present": B(), "equals": ANY},
                      required=("kind", "path"), desc="§12.2 - how a replay decides")
D["action_reproducibility"] = O({
    "status": E(REPRO_STATUSES), "reproduction_kind": E(REPRO_KINDS), "input_artifact_ids": STRS, "environment_id": S(),
    "procedure": O({"kind": E(PROCEDURE_KINDS), "command": S(), "working_directory": S(), "arguments": STRS, "steps": STRS, "reference": S()}),
    "expected_output": O({"artifact_ids": STRS, "result_summary": S(), "check": ref("replay_check")}),
    "limitations": STRS, "notes": S(),
}, desc="§12.2")

KNOWN_ACTION_TYPES = ("ReadFile, SearchCode, SearchWeb, AnalyzeCode, ExploreDirectory, ReadDocumentation, EditFile, CreateFile, "
                      "DeleteFile, RenameFile, RunCommand, RunTests, TypeCheck, Lint, ManualVerification, GitStatus, GitDiff, GitCommit, "
                      "AskUser, ReportProgress, Explain, FormulatePlan, DecomposeTask, EstimateImpact (activity); ExclusiveDecision, "
                      "ParallelSplit, EventBasedDecision, LoopGateway (gateway); Formalize, DefineVerificationGoal, Verify, "
                      "StateSpaceAnalysis, ConformanceCheck, CoSimulate, GenerateTests, Test, Analyze, Observe, Judge, Attest "
                      "(reasoning); EvaluatePolicy, CreateReviewItem, AcknowledgeReviewItem, ResolveReviewItem, AddComment, "
                      "RequestApproval, Approve, Reject, CreateSnapshot, RecordAudit, LinkTrace (governance)")
D["action"] = O({
    "id": I("unique within the trace"),
    "type": S("§8.1 - the action's kind. OPEN: ponens reads any name, and policy packs add their own vocabulary "
              "(policy_compiler.ACTION_TYPES). The spec's: " + KNOWN_ACTION_TYPES, minLength=1),
    "category": E(ACTION_CATEGORIES, "§8.1, §16.3 - the strict action family"),
    "label": S(), "rationale": S(), "detail": S(),
    "inputs": STRS, "outputs": STRS,
    "evidence": L(ref("evidence")), "observations": L(ref("observation")),
    "execution": ref("execution"), "reproducibility": ref("action_reproducibility"),
    "meta_action_id": S("§8.4 - the enclosing meta-action"),
    "request": {"type": "object", "description": "§8.2 - implementation-specific request (open)"},
    "result": {"type": "object", "description": "§8.2 - implementation-specific result (open)"},
    "result_summary": S(), "timestamp": S(),
    "agent": S("in a multi-agent trace, the agent that took the step"),
    "created": B("1.15 - an EditFile that created the file (a CreateFile shown as the edit it is)"),
    "vg_result": O({"status": S()}, desc="a Verify action's verdict, as the reasoner reported it"),
    # gateway payload (§8.1), flattened onto the action as ponens writes it
    "decision_basis": S(), "supporting_inputs": STRS, "options": L(ref("decision_option")),
}, required=("id", "type"), desc="§8 - one atomic step.")

D["meta_action"] = O({
    "id": ID, "title": S(), "intent": S(), "action_ids": L(I()), "outcome": S(),
    "status": E(META_STATUSES), "source": E(META_SOURCES), "parent_id": S(),
    "produced_artifact_ids": STRS, "residual_ids": STRS, "tags": STRS,
}, required=("id",), desc="§8.4 - a unit of intent over the atomic actions.")

D["event"] = O({"type": S("§6.1 - " + " | ".join(EVENT_TYPES) + "; OPEN (adapters record others, e.g. OtelExport)"),
                "description": S(), "summary": S(), "from_user": S(), "reason": S()},
               desc="§6 - how the process began (trigger) or ended (outcome); `typ` in the canonical model.")

D["reference_artifact"] = O({
    "reference_artifact_id": ID, "name": S(), "description": S(), "domain": S(), "version": S(), "source": S(),
    "artifact_type": S("§11.1 - RefFormalModel | RefDocumentation | RefContractModel | RefProtocolSpec | another name"),
    "format": S(), "content_ref": S(),
    "payload": O({"checksum": S("the reference's content checksum (§11.2)")}),
    "verification_goals": L(O({"vg_id": S(), "description": S(), "kind": E(REF_VG_KINDS), "src": S()})),
}, required=("reference_artifact_id",), desc="§11 - an approved model, specification or contract used as ground truth.")

D["policy"] = O({
    "policy_id": S(), "name": S(), "description": S(), "kind": S(), "scope": S(),
    "severity": S("error (blocks) | warning (annotates) - GOAL_CONTRACT §6"), "formula": S("the policy formula (POLICY_LANGUAGE)"),
    "applies_when": {"type": "object"}, "reference_model_id": S(),
}, desc="a policy checked over the trace (POLICY_SPEC); needs a policy_id or a name.")
D["policy_evaluation"] = O({
    "policy_id": S(), "status": E(POLICY_VERDICTS), "note": S(), "checked_at_action_id": I(),
    "evidence_action_ids": L(I()), "violating_action_ids": L(I()), "evidence_artifact_ids": STRS, "violating_artifact_ids": STRS,
}, required=("policy_id", "status"), desc="a policy's verdict over the trace (derived by `trace check`).")

D["execution_environment"] = O({
    "environment_id": ID, "kind": E(ENV_KINDS), "name": S(),
    "components": L(O({"name": S(), "version": S()}, required=("name",))), "configuration": ANY, "notes": S(),
}, required=("environment_id",), desc="§12.3")
D["trace_reproducibility"] = O({
    "status": E(REPRO_STATUSES), "entrypoints": STRS, "required_artifact_ids": STRS, "required_environment_ids": STRS,
    "limitations": STRS, "notes": S(),
}, required=("status",), desc="§12.1")
D["comment"] = O({
    "comment_id": ID, "author": S(), "created_at": S(), "body": S(), "target": ref("target_ref"), "thread_parent_id": S(),
    "status": E(COMMENT_STATUSES), "resolved_at": S(), "tags": STRS,
}, required=("comment_id",), desc="§14.2")
D["review_item"] = O({
    "review_item_id": ID, "author": S(), "created_at": S(), "title": S(), "body": S(), "target": ref("target_ref"),
    "assignee": S(), "status": E(REVIEW_STATUSES), "blocking": B(), "acknowledged_at": S(), "acknowledged_by": S(),
    "resolved_at": S(), "resolved_by": S(), "resolution_note": S(), "tags": STRS,
}, required=("review_item_id",), desc="§14.3")
D["trace_link"] = O({
    "link_id": S(), "from_trace_id": S(), "to_trace_id": S(), "relationship": E(RELATIONSHIPS),
    "created_at": S(), "created_by": S(), "note": S(),
}, desc="§15.1")
D["trace_lineage"] = O({
    "parent_trace_id": S(), "root_trace_id": S(), "chain_position": I(), "chain_status": E(CHAIN_STATUSES), "latest_descendant_trace_id": S(),
}, desc="§15.2")
D["metrics"] = O({"total_actions": I(), "decision_points": I(), "parallel_blocks": I(), "loops": I(), "max_loop_iterations": I(),
                  "meta_action_count": I()}, desc="§5.1")
D["signature"] = O({
    "signer": S(), "content_hash": S(), "algo": E(SIG_ALGOS), "signed_at": S(), "signature": S(),
    "key_type": S(), "key_id": S(), "public_key": S(), "namespace": S(), "bundle": S(), "oidc_issuer": S(), "transparency_log": S(),
    "role": S(), "disposition": S(),
    "timestamp": O({"standard": S(), "tsa": S(), "hash_alg": S(), "message_imprint": S(), "token": S(), "time": S()}),
}, required=("signer", "content_hash", "algo", "signature"), desc="§12.4 (1.11) - a cryptographic sign-off over content_hash.")
D["merge_event"] = O({"parents": STRS, "base": S(), "kind": S("merge | rebase | cherry-pick | squash")}, desc="§15.3")

# Goals (§18) on the wire, in both forms ponens reads: the typed criterion of GOAL_CONTRACT_v0_2 (`id`, `component`,
# `evidence`, `required`) and the §18.1 item (`acceptance_id`, `kind`, `binding`). A criterion is typed iff it carries
# `component` + `evidence` (GOAL_CONTRACT §7).
D["acceptance_item"] = O({
    # GOAL_CONTRACT v0.2 §3 - the typed criterion
    "id": S(), "statement": S(),
    "component": {**O({"function": S(), "function_": S(), "symbol": S(), "file": S(), "path": S()},
                      desc="§4.1 - a function, a file, or a named subject: any other key names a SUBJECT (endpoint, table, …)"),
                  "additionalProperties": S()},
    "property": S("the property the evidence must say it checked"),
    "evidence": {"anyOf": [O({"artifact": S("the artifact TYPE required in the component's lineage"), "reference": S()}, required=("artifact",)),
                           S("the evidence pointer of a resolved §18.1 item")]},
    "required": B(), "covers": STRS, "formula": ANY,
    # TRACE_SPEC §18.1 - the authored item
    "acceptance_id": S(), "kind": E(ACCEPTANCE_KINDS), "label": S(),
    "binding": O({"symbol": S(), "file": S(), "property": S(), "policy_id": S(), "residual_id": S()}),
    "reference": S("§11.2 - a reference artifact id the evidence must be judged against"),
    "status": E(ACCEPTANCE_STATUSES, "authored fallback, or the derived status of a resolved item"),
    # derived by `trace enrich` (§18.3), and the criterion's provenance
    "evidence_ref": S(), "author": S("who drafted the criterion"), "property_match": S(), "from_trace": B(),
    "key": S("1.15 - a short stable name for the criterion, unchanged when its wording is"),
}, desc="§18.1 / GOAL_CONTRACT v0.2 §3 - one acceptance criterion.")
D["goal"] = O({
    "id": S("the goal's id (GOAL_CONTRACT; `goal_id` in §18.1)"), "goal_id": S(),
    "intent": S("the change and why, in plain language"), "intent_author": S("human | agent - who stated the intent"),
    "scope": STRS, "acceptance": L(ref("acceptance_item")), "status": E(GOAL_STATUSES), "meta_action_id": S(),
    "superseded_by": S("1.15 - for a superseded goal: the id of the goal that replaced it"),
    "ticket": S("1.15 - the issue or ticket the goal is for"),
    "policies": O({"packs": L(ANY), "policies": L(ANY), "disabled": STRS},
                  desc="GOAL_CONTRACT §5 - packs/policies governing the goal (ids, or as resolved by enrich)"),
    "intent_clauses": STRS,
    "criteria_review": O({"verdict": E(CRITERIA_VERDICTS), "reviewed_by": S(), "at": S(), "note": S()}),
    # derived by `trace enrich` (§18.3)
    "progress": N(), "cone": L(I()), "open_gaps": I(), "faithfulness": {"type": "object"}, "governance": L(ANY), "governed": B(),
}, desc="§18 - a goal: intent and its definition of done.")

# The legacy top-level residual list (§13.7): the flat residual shape, folded forward into Residual artifacts by
# `migrate_residuals`. Read, never written by a current producer.
D["legacy_residual"] = O(merge({"residual_id": ID}, RESIDUAL_PROPS), required=("residual_id",),
                         desc="§13.7 - deprecated (1.8): a residual in the legacy top-level list")

D["trace"] = O({
    "trace_id": ID, "spec_version": S("the trace spec version, e.g. 1.15", pattern=r"^\d+(\.\d+)*$"),
    "assistant": S(), "model": S(), "timestamp": S(), "title": S(),
    "trigger": ref("event"), "outcome": ref("event"),
    "actions": L(ref("action")), "meta_actions": L(ref("meta_action")),
    "artifacts": L(ref("artifact")), "reference_artifacts": L(ref("reference_artifact")),
    "policies": L(ref("policy")), "policy_evaluations": L(ref("policy_evaluation")),
    "execution_environments": L(ref("execution_environment")), "reproducibility": ref("trace_reproducibility"),
    "comments": L(ref("comment")), "review_items": L(ref("review_item")),
    "residuals": L(ref("legacy_residual"), "§13.7 - DEPRECATED (1.8): residuals are Residual artifacts; read, no longer written"),
    "goals": L(ref("goal")), "trace_links": L(ref("trace_link")), "trace_lineage": ref("trace_lineage"),
    "files_modified": STRS, "metrics": ref("metrics"),
    "content_hash": S("§12.4 - sha256 over the canonical trace, excluding HASH_EXCLUDE"), "signatures": L(ref("signature")),
    # transport/binding metadata (§5, CLI_SYNC_MODEL) - excluded from the content hash
    "repo": S(), "branch": S(), "commit_sha": S(),
    "merge": ref("merge_event"),
    # read by ponens beyond the spec prose
    "task": {"type": "object"}, "task_ref": S(),
    "high_stakes_paths": L(S(), "path fragments marking high-stakes code (formalization-target scan)"),
    "path_labels": {"type": "object", "additionalProperties": STRS, "description": "label -> path patterns (globs or fragments)"},
    "artifact_freshness": {"type": "object", "description": "store-ref -> fresh | stale | gone, stamped by the extension"},
    "summary": {"type": "object", "description": "the record's summary, derived by `trace enrich`"},
    "exploration_actions": L(I(), "the actions in no goal's cone - derived by `trace enrich` (§18.3)"),
    "telemetry": L(ANY, "telemetry an adapter (OpenTelemetry, Langfuse) carried over"),
    "reference_models": L(ANY, "legacy: reference models inline, before reference_artifacts (§11)"),
}, required=("trace_id", "actions", "artifacts"), desc="§5 - a trace: the complete record of an agent's work session.")


SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://ponens.dev/schema/trace.v1_15.json",
    "title": "Ponens trace (Trace Spec 1.15, wire format)",
    "description": "The interchange projection of TRACE_SPEC_v1_15 (§16) as ponens reads and writes it - every valid 1.14 trace "
                   "is a valid 1.15 one. Generated by cli/tools/build_trace_schema.py - edit that, not this file.",
    "$ref": "#/$defs/trace",
    "$defs": D,
}


def render():
    return json.dumps(SCHEMA, indent=1, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    text = render()
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text() != text:
            print(f"{OUT} is out of date - run python3 tools/build_trace_schema.py", file=sys.stderr)
            sys.exit(1)
        sys.exit(0)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text)
    print(f"wrote {OUT} ({len(text)} bytes, {len(D)} definitions)")

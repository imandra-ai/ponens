"""The trace wire schema - Trace Spec 1.15 as JSON Schema (ponens/schema/trace.v1_15.json; 1.14 frozen beside it).

The bundle it replaces (spec/schema/trace.v1_4) could not be used to validate anything: it had no root, so
every JSON value passed, and it described the OCaml encoding of the canonical types (`tag`, `typ`,
`PartiallyReproducible`) rather than the JSON ponens and its producers exchange. Run over real traces from
a producer, all of them failed it - on the encoding, not on anything wrong with them.

So these tests hold the schema to the wire: every trace ponens itself ships validates; each known artifact
type's payload is typed; the closed vocabularies refuse a value the spec does not have, in the spelling
the code uses; the generated file is current; and `trace validate` reports what the schema finds.
"""

import argparse
import json
import pathlib
import sys

import pytest

jsonschema = pytest.importorskip("jsonschema")

from ponens import schema  # noqa: E402
from ponens import trace as trace_mod  # noqa: E402

CLI = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CLI / "tools"))
import build_trace_schema  # noqa: E402
import strict_schema  # noqa: E402


def errors_of(t):
    return schema.schema_errors(t)


def trace(**over):
    t = {"trace_id": "t1", "spec_version": "1.14", "actions": [], "artifacts": []}
    t.update(over)
    return t


def art(artifact_type, payload, **extra):
    return {"artifact_id": "a1", "artifact_type": artifact_type, "payload": payload, **extra}


# ---- the schema itself ------------------------------------------------------------------------

def test_the_schema_is_valid_json_schema_with_a_root():
    s = schema.load()
    jsonschema.Draft202012Validator.check_schema(s)
    assert s["$ref"] == "#/$defs/trace"
    # The v1.4 bundle had no root: `{}` and a string validated. This one is a trace or it is nothing.
    assert errors_of({})
    assert errors_of("not a trace")


def test_the_committed_schema_is_what_the_builder_generates():
    assert schema.SCHEMA_PATH.read_text() == build_trace_schema.render(), \
        "ponens/schema/trace.v1_15.json is stale - run python3 tools/build_trace_schema.py"


def test_the_schema_is_shipped_in_the_package():
    text = (CLI / "pyproject.toml").read_text()
    assert '"schema/*.json"' in text
    assert schema.SCHEMA_PATH.parent.name == "schema" and schema.SCHEMA_PATH.exists()


# ---- every trace ponens ships validates ---------------------------------------------------------

# Fixtures malformed on purpose, to test that a derivation tolerates them - the schema must refuse them.
MALFORMED = {"resolution-no-target.json": "artifacts[1].payload"}


def _shipped():
    roots = [CLI / "ponens" / "demos", CLI / "tests" / "fixtures", CLI.parent / "examples"]
    for root in roots:
        for f in sorted(root.rglob("*.json")) if root.exists() else []:
            try:
                doc = json.loads(f.read_text())
            except ValueError:
                continue
            if f.name in MALFORMED:
                continue
            if isinstance(doc, dict) and "trace_id" in doc and isinstance(doc.get("actions"), list) and "artifacts" in doc:
                yield pytest.param(doc, id=str(f.relative_to(CLI.parent)))


SHIPPED = list(_shipped())


def test_there_are_shipped_traces_to_check():
    assert len(SHIPPED) >= 8


@pytest.mark.parametrize("doc", SHIPPED)
def test_every_shipped_trace_validates(doc):
    assert errors_of(doc) == []


@pytest.mark.parametrize("name,where", sorted(MALFORMED.items()))
def test_a_fixture_malformed_on_purpose_is_refused(name, where):
    doc = json.loads(next((CLI / "tests" / "fixtures").rglob(name)).read_text())
    assert any(e.startswith(f"schema: {where}:") for e in errors_of(doc))


# ---- each known artifact type, typed ----------------------------------------------------------

VALID = {
    "Formalization": {"status": "transparent", "src_lang": "python", "src_code": "x", "formal_code": "let x = 1", "model_language": "iml"},
    "FormalModel": {"model_language": "iml", "formal_code": "let f x = x", "symbols": ["f"], "scope": None},
    "IMLModel": {"iml_code": "let f x = x", "src_lang": "python", "status": "transparent", "symbols": ["f"]},
    "VerificationGoal": {"goal_id": 1, "kind": "verify", "description": "f is idempotent", "src": "verify (fun x -> f (f x) = f x)",
                         "target_artifact_id": "m1", "target_symbol": "f", "model_symbols": ["f"], "properties": []},
    "VerificationResult": {"goal_id": 1, "goal_artifact_id": "vg1", "status": "refuted", "engine": "imandrax",
                           "result": {"refuted": {"counterexample": "x = 3"}},
                           "oracle": {"id": "imandrax", "oracle_type": "reasoner", "evidence_strength": "proof"},
                           "fingerprint": {"task_checksum": "abc", "target_symbol": "f", "engine": "imandrax"}},
    "StateSpaceAnalysisResult": {"target_artifact_id": "m1", "target_symbol": "f", "analysis_kind": "region_decomposition", "complete": True,
                                 "regions": [{"constraints": ["x > 0"], "invariant": "x", "model": None, "model_eval": None}]},
    "Decomposition": {"target_artifact_id": "m1", "regions": [{"constraints": ["x <= 0"]}]},
    "ConformanceResult": {"reference_artifact_id": "ref1", "target_artifact_id": "src1", "status": "passed", "findings": [],
                          "entry_symbol": "settle", "target_symbol": "settle", "conformance_kind": "refinement",
                          "reference_version": "2024-12", "reference_checksum": "c", "evidence_strength": "tests"},
    "CoSimulationResult": {"target_artifact_id": "src1", "input_artifact_ids": [], "status": "matched", "divergence_points": [], "observations": []},
    "GeneratedTests": {"function": "f", "language": "python", "source_analysis_artifact_id": "d1",
                       "tests": [{"name": "t1", "region_index": 0, "constraints": ["x > 0"], "inputs": {"x": 1}, "expected": 1, "code": "assert f(1) == 1"}]},
    "CommandResult": {"command": "pytest", "status": "passed", "passed": 3, "failed": 0},
    "ReproductionBundle": {"entry_action_ids": [1], "artifact_ids": ["a1"], "environment_ids": ["env1"]},
    "Observation": {"statement": "the calendar has 252 trading days", "source": "refdata", "query": "days(2026)", "value": 252,
                    "observed_at": "2026-10-01T00:00:00Z", "confidence": "high", "oracle": {"id": "refdata", "oracle_type": "monitor", "evidence_strength": "attested"}},
    "CarriedForward": {"result_id": "vr1", "basis": "closure-disjoint", "closure": ["c1"], "via_assumptions": []},
    "Residual": {"kind": "defeater", "defeater_kind": "rebuts", "statement": "refuted under interleaving", "severity": "critical",
                 "target": {"target_type": "artifact", "target_id": "vr1"}, "related_artifact_ids": ["cx1"], "source": "reviewer_added",
                 "status": "open", "introduced_by_action_id": 3, "tags": []},
    "ResidualResolution": {"residual_id": "r1", "status": "waived", "justification": "accepted by product", "by": "pm", "evidence_artifact_ids": []},
    "GoalAmendment": {"goal_id": "g1", "change": "item_withdrawn", "item_id": "c2", "was": {"id": "c2"}, "reason": "out of scope"},
    "Diff": {"file": "src/fees.py", "target_symbol": "fee", "subject": {"kind": "config key", "name": "fee.rate"}},
}


@pytest.mark.parametrize("artifact_type", sorted(VALID))
def test_each_known_artifact_type_with_a_valid_payload_validates(artifact_type):
    assert errors_of(trace(artifacts=[art(artifact_type, VALID[artifact_type])])) == []


def test_an_artifact_type_ponens_does_not_know_is_accepted_with_any_payload():
    # Packs bring their own vocabulary (DO-178C's HLR/LLR); the type is open, its payload unchecked.
    assert errors_of(trace(artifacts=[art("HLR", {"anything": [1, 2]})])) == []


# ---- the closed vocabularies, in the code's spelling -------------------------------------------

@pytest.mark.parametrize("label,t,where", [
    ("a verdict the spec does not have", trace(artifacts=[art("VerificationResult", {"status": "holds"})]), "artifacts[0].payload.status"),
    ("a residual kind", trace(artifacts=[art("Residual", {"kind": "worry", "statement": "x"})]), "artifacts[0].payload.kind"),
    ("a residual target type", trace(artifacts=[art("Residual", {"kind": "assumption", "statement": "x",
                                                                 "target": {"target_type": "protocol", "target_id": "f"}})]),
     "artifacts[0].payload.target.target_type"),
    ("a resolution back to open", trace(artifacts=[art("ResidualResolution", {"residual_id": "r1", "status": "open", "justification": "j"})]),
     "artifacts[0].payload.status"),
    ("a conformance result judged against nothing", trace(artifacts=[art("ConformanceResult", {"reference_artifact_id": "", "target_artifact_id": "s", "status": "passed"})]),
     "artifacts[0].payload.reference_artifact_id"),
    ("an observation with no source", trace(artifacts=[art("Observation", {"statement": "s"})]), "artifacts[0].payload"),
    ("an action category outside the four families", trace(actions=[{"id": 1, "type": "ReadFile", "category": "research"}]), "actions[0].category"),
    ("an action id that is not an integer", trace(actions=[{"id": "1", "type": "ReadFile"}]), "actions[0].id"),
    ("a goal status", trace(goals=[{"id": "g1", "intent": "x", "acceptance": [], "status": "replaced"}]), "goals[0].status"),
    ("reproducibility in the canonical model's spelling", trace(reproducibility={"status": "PartiallyReproducible"}), "reproducibility.status"),
    ("a carried-forward basis in snake_case (merge.py writes it hyphenated)",
     trace(artifacts=[art("CarriedForward", {"result_id": "vr1", "basis": "closure_disjoint"})]), "artifacts[0].payload.basis"),
    ("an evidence strength", trace(artifacts=[art("CommandResult", {"oracle": {"id": "x", "evidence_strength": "strong"}})]),
     "artifacts[0].payload.oracle.evidence_strength"),
    ("no trace_id", {"actions": [], "artifacts": []}, "(trace)"),
])
def test_a_value_the_spec_does_not_have_is_refused_where_it_is(label, t, where):
    errs = errors_of(t)
    assert any(e.startswith(f"schema: {where}:") for e in errs), (label, errs)


def test_an_option_may_be_null_and_a_list_is_a_list():
    ok = trace(artifacts=[art("FormalModel", {"model_language": "iml", "formal_code": "x", "scope": None}, supersedes=None, content_ref=None)],
               reproducibility=None, trace_lineage=None)
    assert errors_of(ok) == []
    assert any("artifacts[0].derived_from" in e for e in errors_of(trace(artifacts=[art("Plan", {}, derived_from=None)])))


def test_extra_fields_are_allowed_on_the_wire_and_listed_by_the_strict_variant():
    t = trace(artifacts=[art("VerificationResult", {"status": "proved", "legacy_id": "x"})], producer_note="x")
    assert errors_of(t) == []
    strict = jsonschema.Draft202012Validator(strict_schema.strict(schema.load()))
    extras = {e.message for e in strict.iter_errors(t)}
    assert any("legacy_id" in m for m in extras) and any("producer_note" in m for m in extras)


def test_a_criterion_component_names_any_subject_by_design():
    goal = {"id": "g1", "intent": "x", "acceptance": [{"id": "c1", "component": {"endpoint": "POST /pay"}, "evidence": {"artifact": "TestResult"}}]}
    t = trace(goals=[goal])
    assert errors_of(t) == []
    strict = jsonschema.Draft202012Validator(strict_schema.strict(schema.load()))
    assert list(strict.iter_errors(t)) == []


# ---- trace validate ---------------------------------------------------------------------------

def _validate(tmp_path, t, capsys, **flags):
    f = tmp_path / "t.json"
    f.write_text(json.dumps(t))
    rc = trace_mod.cmd_validate(argparse.Namespace(**{"trace_file": str(f), "strict": False, "all": False, "no_schema": False, **flags}))
    return rc, capsys.readouterr().out


def test_trace_validate_reports_what_the_schema_finds_and_can_skip_it(tmp_path, capsys):
    bad = trace(trigger={"type": "TaskReceived"}, outcome={"type": "ProcessCompleted"},
                actions=[{"id": 1, "type": "ReadFile", "category": "research", "rationale": "r"}])
    rc, out = _validate(tmp_path, bad, capsys)
    assert rc == 1 and "schema: actions[0].category" in out and "§16.1 General rule" in out
    rc, out = _validate(tmp_path, bad, capsys, **{"no_schema": True})
    assert rc == 0 and "schema:" not in out


def test_without_jsonschema_the_check_is_said_to_be_skipped_never_passed(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(schema, "available", lambda: False)
    rc, out = _validate(tmp_path, trace(trigger={"type": "TaskReceived"}, outcome={"type": "ProcessCompleted"}), capsys)
    assert rc == 0 and "not checked against the wire schema" in out


def test_trace_schema_prints_the_schema_or_its_path(capsys):
    trace_mod.cmd_schema(argparse.Namespace(path=True))
    assert capsys.readouterr().out.strip() == str(schema.SCHEMA_PATH)
    trace_mod.cmd_schema(argparse.Namespace(path=False))
    assert json.loads(capsys.readouterr().out)["$ref"] == "#/$defs/trace"


# ---- 1.15: what it adds, and that 1.14 stays valid -----------------------------------------------

def test_the_1_14_projection_is_still_shipped_and_every_trace_valid_under_it_is_valid_under_1_15():
    v14 = json.loads(schema.V1_14_PATH.read_text())
    jsonschema.Draft202012Validator.check_schema(v14)
    assert v14["$ref"] == "#/$defs/trace" and schema.SPEC_VERSION == trace_mod.TRACE_SPEC_VERSION == "1.15"
    valid14 = [p.values[0] for p in SHIPPED if not schema.schema_errors(p.values[0], v14)]
    assert len(valid14) >= 8 and all(errors_of(t) == [] for t in valid14)


@pytest.mark.parametrize("label,t", [
    ("a residual about a symbol, with the file that declares it",
     trace(artifacts=[art("Residual", {"kind": "assumption", "statement": "x", "residual_id": "r1",
                                       "target": {"target_type": "symbol", "target_id": "Cron.nextRun", "path": "src/croner.ts"}})])),
    ("a residual about a file", trace(artifacts=[art("Residual", {"kind": "limitation", "statement": "x", "target": {"target_type": "file", "target_id": "src/a.ts"}})])),
    ("a residual about a declared subject, with its kind",
     trace(artifacts=[art("Residual", {"kind": "assumption", "statement": "x",
                                       "target": {"target_type": "subject", "target_id": "z3 async calls", "subject_kind": "protocol"}})])),
    ("a superseded goal, naming the one that replaced it, with its ticket and a criterion's key",
     trace(goals=[{"id": "g1", "intent": "x", "status": "superseded", "superseded_by": "g2", "ticket": "#48",
                   "acceptance": [{"id": "c1", "key": "sum", "statement": "s"}]}])),
    ("a result within bounds, with its bounds and who witnessed it",
     trace(artifacts=[art("VerificationResult", {"status": "bounded", "bounds": ["runs of length up to 10"], "engine": "apalache",
                                                 "witnessed_by": "grounds", "model_checksum": "c25c", "verification_id": "vf_1",
                                                 "formula": "fun x -> x >= 0", "job_ref": "task:1",
                                                 "result": {"bounded": {"bounds": ["runs of length up to 10"]}}})])),
    ("a goal stated in words, about a subject", trace(artifacts=[art("VerificationGoal", {"statement": "never negative", "within_subject": "fees"})])),
    ("a model with its declarations, engine and witness",
     trace(artifacts=[art("FormalModel", {"model_language": "iml", "engine": "imandrax", "witnessed_by": "grounds",
                                          "declarations": [{"name": "fee", "type": "int -> int"}]})])),
    ("a model's inputs: code, a document, a requirement, a package",
     trace(artifacts=[art("SourceCode", {"kind": "code", "input_id": "i1", "input_of": "formalization", "grain": "declaration", "checksum": "b3",
                                         "read_at": "7f37", "why": "the lookup", "file": "src/a.ts", "target_symbol": "f"}),
                      art("Documentation", {"kind": "document", "input_id": "i2", "grain": "file", "section": "limits", "file": "config.toml"}),
                      art("UserInstruction", {"kind": "requirement", "input_id": "i3", "grain": "text", "ref": "goal"}),
                      art("SourceCode", {"kind": "package", "input_id": "i4", "package": "dinero.js", "version": "2.0.0", "ecosystem": "npm"})])),
    ("a search with its query, scope, commit and hits",
     trace(artifacts=[art("SearchResults", {"query": "toCents", "scope": [], "commit": "21b7", "matches": 13,
                                            "hits": [{"path": "README.md", "line": 6, "text": "toCents"}]})])),
    ("a plan with its approach and files", trace(artifacts=[art("Plan", {"approach": "tests first", "intended_files": ["src/a.ts"]})])),
    ("a conformance run with its command, counts and interface check",
     trace(artifacts=[art("ConformanceResult", {"reference_artifact_id": "fm-1", "target_artifact_id": "d-1", "status": "passed",
                                                "command": "pytest", "passed": 9, "failed": 0, "interface": {"match": None, "reason": "unchecked"}})])),
    ("regions with their checked invariant and a sample",
     trace(artifacts=[art("StateSpaceAnalysisResult", {"verification_id": "vf_2", "regions": [
         {"constraints": ["x <= 1"], "invariant": "0", "invariant_checked": True, "sample": {"x": "1"}, "sample_output": "0"}]})])),
    ("an edit that created the file", trace(actions=[{"id": 1, "type": "EditFile", "category": "activity", "created": True}])),
])
def test_what_1_15_adds_validates_and_is_spec_not_extra(label, t):
    assert errors_of(t) == [], label
    strict = jsonschema.Draft202012Validator(strict_schema.strict(schema.load()))
    assert [e.message for e in strict.iter_errors(t)] == [], label


def test_bounded_is_never_counted_as_proved():
    from ponens import blame, goals, oracles, transitions
    vr = art("VerificationResult", {"status": "bounded", "bounds": ["depth 10"]})
    # The structural check accepts it; evidence-wise it neither meets nor blocks a criterion.
    errs, _ = trace_mod.validate_trace(trace(artifacts=[vr]))
    assert not any("invalid status" in e for e in errs)
    assert goals._evidence_verdict(vr) == "inconclusive"
    # It established something within its bounds, at sat strength - never proof.
    assert "bounded" in blame._ESTABLISHED and oracles._STATUS_STRENGTH["bounded"] == "sat"
    assert oracles._verdict_of({"verified_upto": {"depth": 5}}) == "bounded"
    assert oracles._aggregate(["proved", "bounded"]) == "bounded"
    assert "bounded" in next(t for t in transitions.TRANSITIONS if t.spec_type == "verification_result_status").states
    # A policy's `proved` matches only a proof.
    from ponens.policy_compiler import Atom
    step = {"id": 1, "type": "Verify", "vg_result": {"status": "bounded"}}
    assert trace_mod.evaluate_formula(Atom("proved"), trace(actions=[step]), {"action": step}) is False

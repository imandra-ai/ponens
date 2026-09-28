"""Typed criteria across the use cases people actually write - one table, held to the answer each
should get from `trace overview`.

A criterion is `component` + `evidence: {artifact}` (+ an optional `property` or `reference`). Each row
is the smallest record that poses one question and the state a reader should see. The rows are the
point: a resolution rule that fixes one use case by breaking another shows up here as a changed row,
not as a surprise in someone's review.

Covered: proofs (and two properties of one function), decompositions, tests (and two properties of one
function), a person's review (approved, rejected, changes requested), conformance to a reference,
module-qualified names, a FILE as the subject, a named SUBJECT (endpoint / table / dependency), a
confirmed and an unconfirmed search, a runtime observation, a project-level criterion, and a diff.
"""

import pytest

from ponens.overview import overview
from ponens.trace import normalize_trace

# The rank each producer stamps. ponens has no rank of its own for a person's review; "attested" is it.
STRENGTH = {"VerificationResult": ("reasoner", "proof"), "StateSpaceAnalysisResult": ("reasoner", "proof"),
            "TestResult": ("tester", "tests"), "ConformanceResult": ("tester", "tests"),
            "SearchResults": ("hub", "static_analysis"), "Observation": ("monitor", "tests"),
            "UserApproval": ("reviewer", "attested"), "Diff": ("hub", "attested")}


def art(aid, typ, **payload):
    if typ in STRENGTH:
        kind, strength = STRENGTH[typ]
        payload.setdefault("oracle", {"id": kind, "oracle_type": kind, "evidence_strength": strength})
    return {"artifact_id": aid, "artifact_type": typ, "name": aid, "payload": payload,
            "producer_action_id": 1, "derived_from": payload.pop("_from", [])}


def vg(aid, sym, desc):
    return art(aid, "VerificationGoal", target_symbol=sym, description=desc)


def state(criterion, artifacts):
    t = {"trace_id": "t", "spec_version": "1.14", "trigger": {"type": "TaskReceived", "description": "x"},
         "goals": [{"id": "g1", "intent": "x", "intent_author": "human", "status": "active", "scope": [],
                    "acceptance": [{"id": "c1", "label": "it holds", "required": True, **criterion}]}],
         "actions": [{"id": 1, "type": "EditFile", "category": "activity", "label": "edit", "rationale": "r",
                      "inputs": [], "outputs": [a["artifact_id"] for a in artifacts], "result_summary": "completed"}],
         "artifacts": artifacts, "residuals": [], "outcome": {"type": "ProcessCompleted"}}
    normalize_trace(t)
    return overview(t)["requirements"][0]["state"]


fn = lambda s: {"component": {"function": s}}
ev = lambda t: {"evidence": {"artifact": t}}
FEE = "fee_for"

CASES = [
    # proofs
    ("proof proved", {**fn(FEE), **ev("VerificationResult")}, [art("v", "VerificationResult", target_symbol=FEE, status="proved")], "met"),
    ("proof refuted", {**fn(FEE), **ev("VerificationResult")}, [art("v", "VerificationResult", target_symbol=FEE, status="refuted")], "failed"),
    ("proof of another function", {**fn(FEE), **ev("VerificationResult")}, [art("v", "VerificationResult", target_symbol="payout", status="proved")], "open"),
    ("proof: property asked is the one proved", {**fn(FEE), **ev("VerificationResult"), "property": "never negative"},
     [vg("g", FEE, "fee_for is never negative"), art("v", "VerificationResult", target_symbol=FEE, status="proved", goal_artifact_id="g")], "met"),
    ("proof: property asked is not the one proved", {**fn(FEE), **ev("VerificationResult"), "property": "within the ceiling"},
     [vg("g", FEE, "fee_for is never negative"), art("v", "VerificationResult", target_symbol=FEE, status="proved", goal_artifact_id="g")], "open"),
    ("proof of an unnamed goal does not answer a named property", {**fn(FEE), **ev("VerificationResult"), "property": "never negative"},
     [art("v", "VerificationResult", target_symbol=FEE, status="proved")], "open"),
    # decompositions assert no property: any property of their function
    ("decomposition + property", {**fn("should_retry"), **ev("Decomposition"), "property": "False for 4xx"},
     [art("d", "StateSpaceAnalysisResult", target_symbol="should_retry")], "met"),
    # tests
    ("tests passed", {**fn(FEE), **ev("TestResult")}, [art("t", "TestResult", target_symbol=FEE, status="passed")], "met"),
    ("tests failed", {**fn(FEE), **ev("TestResult")}, [art("t", "TestResult", target_symbol=FEE, status="failed")], "failed"),
    ("tests named for property A answer A", {**fn(FEE), **ev("TestResult"), "property": "never negative"},
     [art("t", "TestResult", target_symbol=FEE, status="passed", description="fee_for is never negative (property test)")], "met"),
    ("tests named for property B do not answer A", {**fn(FEE), **ev("TestResult"), "property": "never negative"},
     [art("t", "TestResult", target_symbol=FEE, status="passed", description="fee_for stays within the ceiling")], "open"),
    ("tests that name no property answer any property of their function", {**fn(FEE), **ev("TestResult"), "property": "never negative"},
     [art("t", "TestResult", target_symbol=FEE, status="passed")], "met"),
    # a person's review
    ("review approved", {**fn(FEE), **ev("UserApproval")}, [art("u", "UserApproval", target_symbol=FEE, status="approved")], "met"),
    ("review rejected", {**fn(FEE), **ev("UserApproval")}, [art("u", "UserApproval", target_symbol=FEE, status="rejected")], "failed"),
    ("review: changes requested", {**fn(FEE), **ev("UserApproval")}, [art("u", "UserApproval", target_symbol=FEE, status="changes_requested")], "failed"),
    # conformance to a reference
    ("conformance to the named reference", {**fn(FEE), **ev("ConformanceResult"), "reference": "ref:spec@1"},
     [art("c", "ConformanceResult", target_symbol=FEE, status="passed", reference_artifact_id="ref:spec@1")], "met"),
    ("conformance to another reference", {**fn(FEE), **ev("ConformanceResult"), "reference": "ref:spec@1"},
     [art("c", "ConformanceResult", target_symbol=FEE, status="passed", reference_artifact_id="ref:other@1")], "open"),
    ("project-level: reference, no component", {**ev("ConformanceResult"), "reference": "ref:spec@1"},
     [art("c", "ConformanceResult", status="passed", reference_artifact_id="ref:spec@1")], "met"),
    # names
    ("module-qualified name", {**fn("pricing.fee_for"), **ev("TestResult")}, [art("t", "TestResult", target_symbol=FEE, status="passed")], "met"),
    # a file as the subject
    ("file: the migration is tested", {"component": {"file": "db/migrations/0042.sql"}, **ev("TestResult")},
     [art("t", "TestResult", file="db/migrations/0042.sql", status="passed")], "met"),
    ("file: a test of another file", {"component": {"file": "db/migrations/0042.sql"}, **ev("TestResult")},
     [art("t", "TestResult", file="db/migrations/0041.sql", status="passed")], "open"),
    ("file: a glob", {"component": {"file": "db/migrations/*.sql"}, **ev("TestResult")},
     [art("t", "TestResult", files=["db/migrations/0042.sql"], status="passed")], "met"),
    ("file: through lineage (a test derived from the diff)", {"component": {"file": "fees.py"}, **ev("TestResult")},
     [art("d", "Diff", file="fees.py"), art("t", "TestResult", status="passed", _from=["d"])], "met"),
    # a named subject
    ("endpoint: the API still conforms", {"component": {"endpoint": "POST /v1/charge"}, **ev("ConformanceResult")},
     [art("c", "ConformanceResult", endpoint="POST /v1/charge", status="passed")], "met"),
    ("endpoint: another endpoint", {"component": {"endpoint": "POST /v1/charge"}, **ev("ConformanceResult")},
     [art("c", "ConformanceResult", endpoint="POST /v1/refund", status="passed")], "open"),
    ("dependency: license checked", {"component": {"dependency": "left-pad"}, **ev("Observation")},
     [art("o", "Observation", dependencies=["left-pad", "lodash"], status="passed")], "met"),
    # negative claims
    ("a confirmed search", {**fn("charge_fee"), **ev("SearchResults")},
     [art("s", "SearchResults", target_symbol="charge_fee", query="charge_fee(", confirmed=True, matches=0)], "met"),
    ("a search nobody could reproduce", {**fn("charge_fee"), **ev("SearchResults")},
     [art("s", "SearchResults", target_symbol="charge_fee", query="charge_fee(", confirmed=False)], "open"),
    # runtime evidence
    ("an observation", {**fn("settle"), **ev("Observation"), "property": "p99 under 50ms"},
     [art("o", "Observation", target_symbol="settle", status="passed", description="settle p99 under 50ms over 24h")], "met"),
    ("an observation that failed", {**fn("settle"), **ev("Observation")}, [art("o", "Observation", target_symbol="settle", status="failed")], "failed"),
    # a change
    ("the change exists", {**fn(FEE), **ev("Diff")}, [art("d", "Diff", target_symbol=FEE, file="fees.py")], "met"),
]


@pytest.mark.parametrize("name,criterion,artifacts,want", CASES, ids=[c[0] for c in CASES])
def test_typed_criterion(name, criterion, artifacts, want):
    assert state(criterion, artifacts) == want

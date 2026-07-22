"""Golden test: the Stripe payment-flow demo, run end-to-end through `ponens trace enrich`.

This pins the *reasoning record* half of the demo (everything downstream of the LLM is
deterministic): the raw trace the agent published + the authored goal go through `enrich`, and we
assert the derived record -- resolved acceptance, progress, relevance cone, residual summary, and
the exploration set -- matches the demo story. The fixture (tests/fixtures/stripe-demo-trace.json)
is the seed `stripe-trace.json` with the demo goal injected, exactly as the desktop enriches it.
"""

import json
import os

from ponens.goals import enrich

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "stripe-demo-trace.json")


def _load():
    with open(FIXTURE) as f:
        return json.load(f)


def _art(trace, aid):
    return next(a for a in trace["artifacts"] if a["artifact_id"] == aid)


def test_input_is_the_demo_lineage():
    """The find-bug -> fix -> prove lineage the demo hinges on."""
    t = _load()
    # The amount invariant is first REFUTED (a5), the model is fixed (a8 supersedes the original a3),
    # and the invariants are then PROVED (a10); conformance to the Stripe reference model is PROVED.
    assert _art(t, "a5")["payload"]["status"] == "refuted"
    assert _art(t, "a8")["supersedes"] == "a3"
    assert _art(t, "a10")["payload"]["status"] == "proved"
    assert _art(t, "a23")["artifact_type"] == "VerificationResult"
    assert _art(t, "a23")["payload"]["status"] == "proved"
    # 84 exhaustive regions + 84 generated tests from the decomposition.
    assert _art(t, "a17")["artifact_type"] == "Decomposition"
    assert _art(t, "a18")["artifact_type"] == "GeneratedTests"


def test_enrich_resolves_the_goal():
    e = enrich(_load())
    g = e["goals"][0]
    # 6 of 10 acceptance items done -> 60% progress; two required items still open (the gap items).
    assert g["progress"] == 0.6
    assert g["open_gaps"] == 2
    statuses = {a["id"]: a["status"] for a in g["acceptance"]}
    assert statuses == {
        "s1": "done", "s2": "done", "s3": "done", "s4": "done", "s5": "done", "s6": "done",
        "s7": "todo", "s8": "todo", "s9": "todo", "s10": "todo",
    }


def test_grounded_overrides_asserted():
    """The point of the tool: evidence decides, not self-report. s6 was authored 'blocked' (its
    property was refuted), but enrich re-resolves it to 'done' against the proving artifact a16."""
    t = _load()
    assert next(a for a in t["goals"][0]["acceptance"] if a["id"] == "s6")["status"] == "blocked"
    e = enrich(t)
    s6 = next(a for a in e["goals"][0]["acceptance"] if a["id"] == "s6")
    assert s6["status"] == "done"
    assert s6["evidence"] == "a16"


def test_acceptance_binds_to_the_right_evidence():
    e = enrich(_load())
    ev = {a["id"]: a.get("evidence") for a in e["goals"][0]["acceptance"]}
    # Properties resolve to their proving VerificationResults; gaps resolve to their residuals.
    assert ev["s2"] == "a7"     # change -> the bug-fix diff
    assert ev["s4"] == "a16" and ev["s5"] == "a16" and ev["s6"] == "a16"
    assert ev["s9"] == "r2" and ev["s10"] == "r1"


def test_summary_counts():
    e = enrich(_load())
    assert e["summary"] == {
        "policy_violations": 0,
        "open_residuals": 3,
        "open_high": 1,       # r1: amount invariant unproved under concurrency
        "stale_evidence": 0,  # the fix was clean: no proved-then-edited symbols left dangling
        "goals_total": 1,
        "goals_met": 0,             # gap items still open -> not fully met
        "goals_certified": 0,       # no criteria_review on this fixture
        "goals_weakly_specified": 0,  # backed by proofs, not just edits
    }


def test_relevance_cone_and_exploration():
    e = enrich(_load())
    cone = e["goals"][0]["cone"]
    exploration = e["exploration_actions"]
    # The goal's cone is the lineage of the resolving artifacts; the off-goal tail (test run, the
    # follow-up python edit, commit) is exploration, not part of what proves the goal.
    assert exploration == [31, 40, 41, 42]
    assert set(cone).isdisjoint(exploration)
    assert len(cone) == 19


def test_residuals_present():
    e = enrich(_load())
    res = {r["residual_id"]: r for r in e["residuals"]}
    assert set(res) == {"r1", "r2", "r3"}
    assert res["r1"]["severity"] == "high"


def test_meta_actions_narrate_the_five_phases():
    """The session's intent-level narrative (§8.4): check -> fix -> introduce security
    features -> verify -> generate tests. Every atomic action belongs to exactly one phase."""
    t = _load()
    metas = t["meta_actions"]
    assert [m["id"] for m in metas] == ["m1", "m2", "m3", "m4", "m5"]
    assert [m["title"] for m in metas] == [
        "Check the logic",
        "Fix the over-refund bug",
        "Introduce 3DS/SCA + high-risk security features",
        "Verify the new security properties",
        "Generate tests & confirm conformance",
    ]
    # Coverage: the phases partition the timeline — every action in exactly one, no overlap.
    grouped = [aid for m in metas for aid in m["action_ids"]]
    assert sorted(grouped) == sorted(a["id"] for a in t["actions"])
    assert len(grouped) == len(set(grouped))
    # Each action back-references its enclosing phase, consistently with the phase's action_ids.
    by_action = {a["id"]: a.get("meta_action_id") for a in t["actions"]}
    for m in metas:
        for aid in m["action_ids"]:
            assert by_action[aid] == m["id"]
    # The check phase found the bug (its verify refuted); the verify phase carries the open gaps.
    assert "a5" in metas[0]["produced_artifact_ids"]  # the refuted result
    assert set(metas[3]["residual_ids"]) == {"r1", "r2", "r3"}
    # enrich preserves the overlay untouched.
    assert enrich(t)["meta_actions"] == metas

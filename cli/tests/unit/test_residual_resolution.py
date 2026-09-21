"""`ponens trace residual resolve`: closing a gap by APPENDING the decision, never by editing it out.

Editing `status` in place is indistinguishable from never having declared the gap - the record loses
who decided, on what grounds, and at which point in the work, and a reader cannot tell a reasoned
waiver from a quiet deletion. These pin the append-only property itself, not just the derived status.
"""
import json
import types

import pytest

from ponens import lineage
from ponens.trace import cmd_residual_add, cmd_residual_resolve, validate_trace


def _trace_file(tmp_path):
    t = {"trace_id": "t", "spec_version": "1.13",
         "actions": [{"id": 1, "type": "Formalize", "category": "reasoning", "rationale": "r",
                      "inputs": [], "outputs": ["a1"]}],
         "artifacts": [{"artifact_id": "a1", "artifact_type": "IMLModel", "name": "m",
                        "producer_action_id": 1}],
         "outcome": {"type": "ProcessCompleted", "summary": "done"}}
    f = tmp_path / "t.json"
    f.write_text(json.dumps(t))
    return f


def _add(f, **over):
    a = dict(trace_file=str(f), kind="assumption", severity="high", statement="assumes X",
             target_type=None, target_id=None, suggested_check=None, related=None,
             introduced_by=1, status="open", tag=None)
    a.update(over)
    assert cmd_residual_add(types.SimpleNamespace(**a)) == 0


def _resolve(f, rid="r1", **over):
    a = dict(trace_file=str(f), residual_id=rid, status="waived", justification="because",
             evidence=None, by=None, at=None)
    a.update(over)
    return cmd_residual_resolve(types.SimpleNamespace(**a))


def _load(f):
    return json.loads(f.read_text())


def test_resolving_never_touches_the_residual(tmp_path):
    f = _trace_file(tmp_path)
    _add(f)
    before = next(a for a in _load(f)["artifacts"] if a["artifact_type"] == "Residual")
    assert _resolve(f, by="someone", justification="accepted, documented in the runbook") == 0
    after = next(a for a in _load(f)["artifacts"] if a["artifact_type"] == "Residual")
    assert after == before, "the gap as its producer declared it must survive verbatim"


def test_the_decision_is_appended_as_an_action_and_an_artifact(tmp_path):
    f = _trace_file(tmp_path)
    _add(f)
    assert _resolve(f, by="someone", evidence=["a1"], status="addressed",
                    justification="closed by the model in a1") == 0
    t = _load(f)
    res = next(a for a in t["artifacts"] if a["artifact_type"] == "ResidualResolution")
    act = next(a for a in t["actions"] if a["id"] == res["producer_action_id"])
    assert res["payload"]["residual_id"] == "r1"
    assert res["payload"]["justification"] == "closed by the model in a1"
    assert res["payload"]["by"] == "someone"
    assert res["payload"]["evidence_artifact_ids"] == ["a1"]
    assert res["payload"]["at"]                      # stamped even when not supplied
    # It hangs off the gap it closes, so the lineage DAG shows the closure on the residual.
    assert res["derived_from"][0] == "r1"
    # And the decision is a step in the narrative, carrying the justification as its rationale.
    assert act["type"] == "Decision" and act["rationale"] == "closed by the model in a1"
    assert "r1" in act["inputs"] and res["artifact_id"] in act["outputs"]


def test_effective_status_is_derived_not_stored(tmp_path):
    f = _trace_file(tmp_path)
    _add(f)
    _resolve(f, status="waived", justification="accepted")
    t = _load(f)
    r = next(x for x in lineage.residual_surface(t) if x["residual_id"] == "r1")
    assert r["status"] == "waived"          # what every existing consumer reads
    assert r["declared_status"] == "open"   # what the producer actually wrote
    assert r["resolution"]["justification"] == "accepted"
    # The stored payload still says open - the derivation is the only thing that moved.
    art = next(a for a in t["artifacts"] if a["artifact_id"] == "r1")
    assert art["payload"]["status"] == "open"


def test_a_later_resolution_wins_and_the_earlier_one_stays(tmp_path):
    f = _trace_file(tmp_path)
    _add(f)
    _resolve(f, status="waived", justification="accepted as permanent")
    _resolve(f, status="acknowledged", justification="reopened, legal wants it written down")
    r = next(x for x in lineage.residual_surface(_load(f)) if x["residual_id"] == "r1")
    assert r["status"] == "acknowledged"
    assert [x["status"] for x in r["resolutions"]] == ["waived", "acknowledged"]
    assert "permanent" in r["resolutions"][0]["justification"], "the reversed waiver is still readable"


def test_resolutions_apply_in_action_order_not_list_order(tmp_path):
    # Ordering by the deciding ACTION is what makes "latest wins" mean latest in the work. A trace
    # whose artifacts were appended out of order (a merge, a hand edit) must still resolve the same.
    f = _trace_file(tmp_path)
    _add(f)
    _resolve(f, status="waived", justification="first")
    _resolve(f, status="addressed", justification="second")
    t = _load(f)
    t["artifacts"].reverse()
    r = next(x for x in lineage.residual_surface(t) if x["residual_id"] == "r1")
    assert r["status"] == "addressed"


def test_unknown_residual_is_refused_and_nothing_is_written(tmp_path):
    f = _trace_file(tmp_path)
    _add(f)
    before = f.read_text()
    assert _resolve(f, rid="r9") == 1
    assert f.read_text() == before


def test_unknown_evidence_is_refused_and_nothing_is_written(tmp_path):
    # `addressed` cites what closed the gap. A pointer to an artifact that isn't there is a dangling
    # claim of evidence, which is worse than no pointer.
    f = _trace_file(tmp_path)
    _add(f)
    before = f.read_text()
    assert _resolve(f, status="addressed", evidence=["nope"]) == 1
    assert f.read_text() == before


def test_a_resolved_trace_still_validates(tmp_path):
    f = _trace_file(tmp_path)
    _add(f)
    _resolve(f, status="waived", justification="accepted")
    errors, _ = validate_trace(_load(f))
    assert errors == []


@pytest.mark.parametrize("status", list(lineage.RESOLUTION_STATUSES))
def test_every_resolution_status_is_a_valid_residual_status(status):
    # The derived status lands in `status`, which the validator checks against RESIDUAL_STATUSES -
    # a resolution vocabulary that drifted from it would make resolving a trace invalidate it.
    from ponens.trace import RESIDUAL_STATUSES
    assert status in RESIDUAL_STATUSES


def test_open_is_not_a_resolution(tmp_path):
    # A residual is born open; re-opening is a new decision back to `acknowledged`, not a pretence
    # that it was never closed.
    assert "open" not in lineage.RESOLUTION_STATUSES


# --- invalidating a justification -------------------------------------------------------------------
#
# A justification is a CLAIM. The way a claim is attacked in this model is a Defeater (§13.2), not a
# deletion: both the waiver and the reason it does not hold stay in the record, and while the defeater
# is open the closure is not in force.

def _contest(f, resolution_id="rr1", **over):
    a = dict(trace_file=str(f), resolution_id=resolution_id, reason="the premise is false",
             defeater_kind="undermines", severity="high", by=None)
    a.update(over)
    from ponens.trace import cmd_residual_contest
    return cmd_residual_contest(types.SimpleNamespace(**a))


def test_an_open_defeater_against_a_resolution_reopens_the_gap(tmp_path):
    f = _trace_file(tmp_path)
    _add(f)
    _resolve(f, status="waived", justification="cannot happen in practice")
    assert _contest(f, by="reviewer") == 0
    r = next(x for x in lineage.residual_surface(_load(f)) if x["residual_id"] == "r1")
    assert r["status"] == "open", "a contested closure closes nothing"
    assert r["resolution_contested_by"] == ["r2"]
    # The justification itself is untouched - invalidated, not removed.
    assert r["resolutions"][0]["justification"] == "cannot happen in practice"
    assert r["resolutions"][0]["contested_by"] == ["r2"]


def test_withdrawing_the_objection_restores_the_closure(tmp_path):
    f = _trace_file(tmp_path)
    _add(f)
    _resolve(f, status="waived", justification="cannot happen in practice")
    _contest(f)
    _resolve(f, rid="r2", status="addressed", justification="checked with the team; the premise holds")
    r = next(x for x in lineage.residual_surface(_load(f)) if x["residual_id"] == "r1")
    assert r["status"] == "waived", "the defeater is closed, so the closure stands again"
    assert not r.get("resolution_contested_by")
    # And the whole exchange is still readable.
    d = next(x for x in lineage.residual_surface(_load(f)) if x["residual_id"] == "r2")
    assert d["kind"] == "defeater" and d["status"] == "addressed"


def test_contesting_records_the_objection_as_its_own_step(tmp_path):
    f = _trace_file(tmp_path)
    _add(f)
    _resolve(f, status="waived", justification="cannot happen")
    _contest(f, reason="the gateway does not serialise these")
    t = _load(f)
    d = next(a for a in t["artifacts"] if a["artifact_id"] == "r2")
    assert d["payload"]["kind"] == "defeater"
    assert d["payload"]["defeater_kind"] == "undermines"
    assert d["payload"]["target"] == {"target_type": "artifact", "target_id": "rr1"}
    act = next(a for a in t["actions"] if a["id"] == d["producer_action_id"])
    assert act["type"] == "Decision" and act["rationale"] == "the gateway does not serialise these"


def test_a_later_uncontested_resolution_still_wins_over_a_contested_one(tmp_path):
    f = _trace_file(tmp_path)
    _add(f)
    _resolve(f, status="waived", justification="first, on bad grounds")
    _contest(f, resolution_id="rr1")
    _resolve(f, status="addressed", justification="second, on the evidence")
    r = next(x for x in lineage.residual_surface(_load(f)) if x["residual_id"] == "r1")
    assert r["status"] == "addressed"
    assert r["resolutions"][0]["contested_by"] == ["r2"]     # the bad one is still marked
    assert r["resolutions"][1]["contested_by"] == []


def test_contesting_something_that_is_not_a_resolution_is_refused(tmp_path):
    f = _trace_file(tmp_path)
    _add(f)
    before = f.read_text()
    assert _contest(f, resolution_id="r1") == 1              # r1 is the gap, not a decision about it
    assert f.read_text() == before


def test_a_cycle_of_contested_closures_reads_against_closure(tmp_path):
    # Two waivers, each contested by a defeater the other waiver's contest closes - an argument with
    # no fixpoint. It must not settle in favour of "closed": an unresolvable dispute about whether a
    # gap is closed is not a closed gap.
    f = _trace_file(tmp_path)
    _add(f)
    _add(f, statement="assumes Y")
    _resolve(f, rid="r1", status="waived", justification="a")
    _resolve(f, rid="r2", status="waived", justification="b")
    t = _load(f)
    # r3 defeats r1's closure; r4 defeats r2's closure; each defeater is itself "closed" by a
    # resolution the other defeater contests.
    t["artifacts"] += [
        {"artifact_id": "r3", "artifact_type": "Residual", "producer_action_id": 1,
         "payload": {"kind": "defeater", "status": "open", "statement": "x",
                     "target": {"target_type": "artifact", "target_id": "rr1"}}},
        {"artifact_id": "r4", "artifact_type": "Residual", "producer_action_id": 1,
         "payload": {"kind": "defeater", "status": "open", "statement": "y",
                     "target": {"target_type": "artifact", "target_id": "rr2"}}},
        {"artifact_id": "rr3", "artifact_type": "ResidualResolution", "producer_action_id": 1,
         "derived_from": ["r3"], "payload": {"residual_id": "r3", "status": "addressed", "justification": "c"}},
        {"artifact_id": "rr4", "artifact_type": "ResidualResolution", "producer_action_id": 1,
         "derived_from": ["r4"], "payload": {"residual_id": "r4", "status": "addressed", "justification": "d"}},
        {"artifact_id": "r5", "artifact_type": "Residual", "producer_action_id": 1,
         "payload": {"kind": "defeater", "status": "open", "statement": "z",
                     "target": {"target_type": "artifact", "target_id": "rr3"}}},
        {"artifact_id": "r6", "artifact_type": "Residual", "producer_action_id": 1,
         "payload": {"kind": "defeater", "status": "open", "statement": "w",
                     "target": {"target_type": "artifact", "target_id": "rr4"}}},
    ]
    surface = {x["residual_id"]: x for x in lineage.residual_surface(t)}
    # r5/r6 are open and uncontested, so rr3/rr4 do not hold, so r3/r4 stay open, so rr1/rr2 do not
    # hold: both gaps are open. Whatever the iteration does, it must not report them closed.
    assert surface["r1"]["status"] == "open"
    assert surface["r2"]["status"] == "open"

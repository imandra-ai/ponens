"""Properties that must hold after ANY sequence of operations on a record.

Every hole found in this area was found by a different kind of check - reading a demo, following a
click, sweeping commands over fixtures, a round-trip test, enumerating state transitions - and each
kind found a class the others could not. That is the problem: every check is a specific assertion
someone thought to write, so the next hole waits for the next person to think of the right question.

These checks are not specific. They take the operations an agent can actually perform, compose them
at random, and assert the properties that must hold no matter what - so a NEW operation, or a change
to an old one, is checked against them without anyone writing a test for it.

The properties are the shape every hole so far has had:

  RECOVERABLE   Nothing ever declared may become unreadable. A gap, a criterion, a decision - once
                stated, it stays in the record even after it stops being in force.
  EARNED        The record's apparent standing may improve only by adding evidence or by a RECORDED
                decision. This is the one that matters: `goal drop` moved the Stripe demo from 88% to
                100% by deleting the criterion that was not met, and nothing anywhere objected.
  READABLE      Every reader still runs. A record the tools crash on is not a record.
  STABLE        Writing and re-reading changes nothing.

Seeds are printed on failure so any counterexample replays exactly.
"""
import copy
import json
import random
import types

import pytest

from ponens import goals as goalops
from ponens import lineage
from ponens import trace as T


# ── the record's observable standing ────────────────────────────────────────────────────────────

def _progress(trace):
    """Total progress across goals, the number a reader takes as 'how done is this'."""
    enriched = goalops.enrich(copy.deepcopy(trace))
    gs = enriched.get("goals") or []
    return round(sum(g.get("progress", 0.0) for g in gs), 6) if gs else 0.0


def _declared_residuals(trace):
    """Every residual id the record has ever carried."""
    return {r.get("residual_id") for r in lineage.residual_surface(trace)}


def _declared_criteria(trace):
    """Every acceptance criterion ever asked for: the ones still in the definition of done, PLUS the
    ones withdrawn from it. A withdrawal is allowed; forgetting that it happened is not."""
    out = set()
    for g in trace.get("goals") or []:
        for it in g.get("acceptance") or []:
            out.add((g.get("id"), it.get("id")))
    for a in lineage.amendments_of(trace):
        if a.get("change") == "item_withdrawn":
            out.add((a.get("goal_id"), a.get("item_id")))
        elif a.get("change") in ("goal_withdrawn", "goal_replaced"):
            for it in ((a.get("was") or {}).get("acceptance") or []):
                out.add((a.get("goal_id"), it.get("id")))
    return out


def _evidence_count(trace):
    return len(trace.get("artifacts") or [])


def _decisions(trace):
    """Recorded decisions: the appends that are allowed to change the record's standing."""
    return len(lineage.amendments_of(trace)) + sum(
        len(v) for v in lineage.resolutions_of(trace).values())


# ── the operations an agent can perform ─────────────────────────────────────────────────────────

def _ns(**kw):
    return types.SimpleNamespace(**kw)


def _seed_trace(tmp_path):
    t = {
        "trace_id": "inv", "spec_version": "1.14",
        "actions": [{"id": 1, "type": "Formalize", "category": "reasoning", "rationale": "r",
                     "inputs": [], "outputs": ["a1"]}],
        "artifacts": [{"artifact_id": "a1", "artifact_type": "IMLModel", "name": "m",
                       "producer_action_id": 1, "payload": {"symbols": ["f"]}}],
        "goals": [{"id": "g", "intent": "ship it", "scope": [], "status": "active", "acceptance": []}],
        "outcome": {"type": "ProcessCompleted", "summary": "d"},
    }
    f = tmp_path / "inv.json"
    f.write_text(json.dumps(t))
    return f


def _ops(f, rnd, state):
    """The operation set, as closures. Each returns a short name for the failure trail."""

    def add_residual():
        state["r"] += 1
        T.cmd_residual_add(_ns(trace_file=str(f), kind=rnd.choice(sorted(T.RESIDUAL_KINDS - {"defeater"})),
                               severity=rnd.choice(["low", "medium", "high"]),
                               statement=f"gap {state['r']}", target_type=None, target_id=None,
                               suggested_check="check it", related=None, introduced_by=1,
                               status="open", tag=None))
        return "residual add"

    def resolve_residual():
        ids = sorted(_declared_residuals(json.loads(f.read_text())))
        if not ids:
            return None
        T.cmd_residual_resolve(_ns(trace_file=str(f), residual_id=rnd.choice(ids),
                                   status=rnd.choice(["waived", "addressed", "acknowledged"]),
                                   justification="because", evidence=None, by="tester", at=None))
        return "residual resolve"

    def contest_resolution():
        t = json.loads(f.read_text())
        rr = [a["artifact_id"] for a in t.get("artifacts") or [] if lineage.is_resolution(a)]
        if not rr:
            return None
        T.cmd_residual_contest(_ns(trace_file=str(f), resolution_id=rnd.choice(rr),
                                   reason="the grounds do not hold", defeater_kind="undermines",
                                   severity="high", by="reviewer"))
        return "residual contest"

    def add_criterion():
        state["s"] += 1
        T.cmd_goal_accept(_ns(trace_file=str(f), goal="g", kind="property",
                              label=f"criterion {state['s']}", symbol="f", property="p",
                              policy_id=None, residual_id=None, file=None, covers=None,
                              optional=False, author="agent", id=None))
        return "goal accept"

    def drop_criterion():
        t = json.loads(f.read_text())
        g = next((x for x in t.get("goals") or [] if x.get("id") == "g"), None)
        items = [i["id"] for i in (g or {}).get("acceptance") or []]
        if not items:
            return None
        T.cmd_goal_drop(_ns(trace_file=str(f), goal="g", item_id=rnd.choice(items),
                            reason="no longer part of done", by="tester"))
        return "goal drop"

    def replace_goal():
        if not (json.loads(f.read_text()).get("goals") or []):
            return None
        T.cmd_goal_set(_ns(trace_file=str(f), intent="ship it differently", scope=None, clause=None,
                           intent_author="human", id="g", json=None,
                           reason="scope changed", by="tester"))
        return "goal set (replace)"

    def withdraw_goal():
        if not (json.loads(f.read_text()).get("goals") or []):
            return None
        T.cmd_goal_rm(_ns(trace_file=str(f), goal="g", reason="superseded", by="tester"))
        return "goal rm"

    def certify():
        if not (json.loads(f.read_text()).get("goals") or []):
            return None
        T.cmd_goal_certify(_ns(trace_file=str(f), goal="g", by="reviewer",
                               verdict=rnd.choice(["approved", "changes-requested"]), note="n"))
        return "goal certify"

    def add_evidence():
        state["a"] += 1
        aid = f"e{state['a']}"
        t = json.loads(f.read_text())
        nid = max([a["id"] for a in t["actions"]] or [0]) + 1
        t["actions"].append({"id": nid, "type": "Verify", "category": "reasoning",
                             "rationale": "r", "inputs": ["a1"], "outputs": [aid]})
        t["artifacts"].append({"artifact_id": aid, "artifact_type": "VerificationResult",
                               "name": aid, "producer_action_id": nid, "derived_from": ["a1"],
                               "payload": {"status": "proved", "target_symbol": "f",
                                           "property": "p", "engine": "imandrax"}})
        f.write_text(json.dumps(t))
        return "add evidence"

    return [add_residual, resolve_residual, contest_resolution, add_criterion, drop_criterion,
            replace_goal, withdraw_goal, certify, add_evidence]


# ── the properties ──────────────────────────────────────────────────────────────────────────────

READERS = ("validate", "residuals", "resolve", "next", "overview", "status", "grade", "blame")


def _check(f, before, after, op, trail):
    where = f"after {op} (trail: {' -> '.join(trail)})"

    # RECOVERABLE - a withdrawal is allowed, forgetting it is not.
    assert _declared_residuals(after) >= before["residuals"], \
        f"{where}: a residual that was declared is no longer readable"
    assert _declared_criteria(after) >= before["criteria"], \
        f"{where}: a criterion that was asked for is no longer readable"

    # EARNED - standing may improve only by evidence or by a recorded decision.
    if _progress(after) > before["progress"] + 1e-9:
        gained_evidence = _evidence_count(after) > before["evidence"]
        recorded = _decisions(after) > before["decisions"]
        assert gained_evidence or recorded, \
            (f"{where}: progress rose {before['progress']} -> {_progress(after)} with no new evidence "
             f"and no recorded decision")

    # READABLE - every reader still runs, on every shape the walk can produce.
    for cmd in READERS:
        fn = {"validate": lambda: T.validate_trace(after),
              "residuals": lambda: lineage.residual_surface(after),
              "resolve": lambda: [goalops.resolve_item(i, after, goal=g)
                                  for g in (after.get("goals") or [])
                                  for i in (g.get("acceptance") or [])],
              "next": lambda: goalops.next_steps(goalops.enrich(copy.deepcopy(after))),
              "overview": lambda: __import__("ponens.overview", fromlist=["overview"]).overview(after),
              "status": lambda: goalops.enrich(copy.deepcopy(after)),
              "grade": lambda: lineage.amendments_of(after),
              "blame": lambda: __import__("ponens.blame", fromlist=["blame"]).blame(after)}[cmd]
        try:
            fn()
        except Exception as e:                       # noqa: BLE001 - the point is that nothing throws
            raise AssertionError(f"{where}: `{cmd}` crashed: {type(e).__name__}: {e}") from e

    # VALID - the walk may not produce a malformed record.
    errors, _ = T.validate_trace(after)
    assert not errors, f"{where}: {errors}"


@pytest.mark.parametrize("seed", range(40))
def test_no_sequence_of_operations_breaks_the_record(tmp_path, seed):
    rnd = random.Random(seed)
    f = _seed_trace(tmp_path)
    state = {"r": 0, "s": 0, "a": 0}
    ops = _ops(f, rnd, state)
    trail = []
    for _ in range(14):
        before_t = json.loads(f.read_text())
        before = {"progress": _progress(before_t), "residuals": _declared_residuals(before_t),
                  "criteria": _declared_criteria(before_t), "evidence": _evidence_count(before_t),
                  "decisions": _decisions(before_t)}
        name = rnd.choice(ops)()
        if name is None:
            continue                                 # precondition not met; not a step
        trail.append(name)
        _check(f, before, json.loads(f.read_text()), name, trail)


def test_writing_and_re_reading_changes_nothing(tmp_path):
    """STABLE. A derived value that shifts on a round trip means something is being stored that
    should be computed, or computed from something that did not survive the write."""
    rnd = random.Random(99)
    f = _seed_trace(tmp_path)
    state = {"r": 0, "s": 0, "a": 0}
    ops = _ops(f, rnd, state)
    for _ in range(12):
        rnd.choice(ops)()
    t1 = json.loads(f.read_text())
    surface1 = lineage.residual_surface(copy.deepcopy(t1))
    f.write_text(json.dumps(t1))
    t2 = json.loads(f.read_text())
    assert lineage.residual_surface(copy.deepcopy(t2)) == surface1
    assert _progress(t2) == _progress(t1)

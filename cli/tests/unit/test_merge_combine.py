"""Unit tests for the two-parent trace COMBINE (ponens.merge.combine).

`combine` materializes `merge()`'s report into a VALID merged trace that `ponens trace
validate`/`enrich`/`check` accept. These tests reuse the trace builders from test_merge and assert the
materialized trace validates, records the two-parent MergeEvent, carries CarriedForward artifacts +
needs_rereasoning/coverage_regression residuals, is total, and enriches cleanly.
"""

import json
import os
import subprocess
import sys

from ponens.merge import combine, merge, _standing_results
from ponens.trace import validate_trace
from ponens import goals as goalops

# The source-tree `cli/` dir (…/cli/tests/unit/this_file → …/cli). CLI subprocesses run with this as
# cwd + on PYTHONPATH so they exercise the SOURCE `ponens`, not any pip-installed copy.
_CLI_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _run_cli(*argv):
    env = dict(os.environ, PYTHONPATH=_CLI_DIR + os.pathsep + os.environ.get("PYTHONPATH", ""))
    return subprocess.run([sys.executable, "-m", "ponens.cli", *argv],
                          capture_output=True, text=True, cwd=_CLI_DIR, env=env)


# ---- trace builders (mirrors test_merge) ----------------------------------

def _model(src, aid="m1", step=1, derived_from=None):
    a = {"artifact_id": aid, "artifact_type": "IMLModel", "producer_action_id": step,
         "payload": {"iml_code": src}}
    if derived_from is not None:
        a["derived_from"] = derived_from
    return a


def _proved(sym, vg="vg1", vr="vr1", step=2, desc=None):
    return [
        {"artifact_id": vg, "artifact_type": "VerificationGoal", "producer_action_id": step,
         "payload": {"goal_id": vg + "-G", "target_symbol": sym,
                     "description": desc or f"property of {sym}"}},
        {"artifact_id": vr, "artifact_type": "VerificationResult", "producer_action_id": step + 1,
         "derived_from": [vg], "payload": {"goal_id": vg + "-G", "goal_artifact_id": vg,
                                           "status": "proved"}},
    ]


def _trace(src, results=None, residuals=None, step=1, tid="t"):
    t = {"trace_id": tid, "artifacts": [_model(src, step=step)]}
    for r in results or []:
        t["artifacts"].extend(r)
    if residuals:
        t["residuals"] = residuals
    return t


SRC = "let g x = x + 1\nlet f x = g x + 2\nlet h x = x * 10\n"


# ---- 1. combine() produces a trace validate accepts ------------------------

def test_combine_validates_disjoint():
    ours = _trace(SRC, results=[_proved("f")], tid="ours")
    theirs = _trace("let g x = x + 1\nlet f x = g x + 2\nlet h x = x * 999\n", tid="theirs")  # only h
    merged = combine(ours, theirs)
    errors, _warnings = validate_trace(merged)
    assert errors == [], errors


def test_combine_validates_rereason():
    ours = _trace(SRC, results=[_proved("f")], tid="ours")
    theirs = _trace("let g x = x + 1\nlet f x = g x + 99\nlet h x = x * 10\n", tid="theirs")  # f changed
    merged = combine(ours, theirs)
    errors, _warnings = validate_trace(merged)
    assert errors == [], errors


# ---- 2. MergeEvent: two parents + base + fresh trace_id --------------------

def test_combine_records_mergeevent():
    ours = _trace(SRC, results=[_proved("f")], tid="ours")
    theirs = _trace(SRC.replace("999", "x"), tid="theirs")
    merged = combine(ours, theirs)
    assert merged["merge"]["parents"] == ["ours", "theirs"]
    assert merged["merge"]["base"] is None
    assert merged["merge"]["kind"] == "merge"
    assert merged["trace_id"] == "merge-ours-theirs"
    assert merged["trace_id"] not in ("ours", "theirs")
    # trace_links records the two-parent lineage too.
    assert any(l.get("kind") == "merge" and l.get("parents") == ["ours", "theirs"]
               for l in merged.get("trace_links", []))


def test_combine_records_base():
    base = _trace(SRC, tid="base")
    ours = _trace(SRC, results=[_proved("f")], tid="ours")
    theirs = _trace("let g x = x + 1\nlet f x = g x + 2\nlet h x = x * 999\n", tid="theirs")
    merged = combine(ours, theirs, base=base)
    assert merged["merge"]["base"] == "base"


# ---- 3. materialized findings ---------------------------------------------

def test_combine_carried_forward_artifact():
    ours = _trace(SRC, results=[_proved("f")], tid="ours")
    theirs = _trace("let g x = x + 1\nlet f x = g x + 2\nlet h x = x * 999\n", tid="theirs")  # only h
    merged = combine(ours, theirs)
    cf = [a for a in merged["artifacts"] if a["artifact_type"] == "CarriedForward"]
    assert [a["artifact_id"] for a in cf] == ["carried-vr1"]
    a = cf[0]
    assert a["derived_from"] == ["vr1"]
    assert a["payload"]["symbol"] == "f"
    assert a["payload"]["basis"] == "closure-disjoint"
    # producer_action_id resolves to a real merge action.
    action_ids = {act["id"] for act in merged["actions"]}
    assert a["producer_action_id"] in action_ids
    merge_actions = [act for act in merged["actions"] if act["type"] == "merge"]
    assert len(merge_actions) == 1


def test_combine_needs_rereasoning_residual():
    ours = _trace(SRC, results=[_proved("f")], tid="ours")
    theirs = _trace("let g x = x + 1\nlet f x = g x + 99\nlet h x = x * 10\n", tid="theirs")  # f changed
    merged = combine(ours, theirs)
    rr = [r for r in merged["residuals"] if r["kind"] == "needs_rereasoning"]
    assert [r["residual_id"] for r in rr] == ["rereason-vr1"]
    assert rr[0]["status"] == "open"
    assert rr[0]["derived"] is True
    assert rr[0]["target"] == {"target_type": "artifact", "target_id": "vr1"}
    # no CarriedForward for a re-reasoned result.
    assert [a for a in merged["artifacts"] if a["artifact_type"] == "CarriedForward"] == []


def test_combine_coverage_regression_residual():
    # OURS has a goal scoped over `newf`; theirs ADDS an in-scope, unproven component `newf`.
    ours = {"trace_id": "ours",
            "artifacts": [_model(SRC)],
            "goals": [{"id": "G", "intent": "cover", "scope": ["newf"]}]}
    theirs = _trace(SRC + "let newf x = x + 7\n", tid="theirs")  # newf added, unproven
    rep = merge(ours, theirs)
    assert rep.get("coverage_regressions"), "fixture should trigger a coverage regression"
    merged = combine(ours, theirs)
    cov = [r for r in merged["residuals"] if r["kind"] == "coverage_regression"]
    assert len(cov) == 1
    assert cov[0]["goal_id"] == "G"
    assert cov[0]["derived"] is True
    errors, _ = validate_trace(merged)
    assert errors == [], errors


# ---- 4. totality ----------------------------------------------------------

def test_combine_totality():
    # two standing results: one carried (h unrelated), one re-reasoned (f touched)
    ours = _trace(SRC,
                  results=[_proved("f", vg="vgf", vr="vrf"),
                           _proved("h", vg="vgh", vr="vrh")],
                  tid="ours")
    theirs = _trace("let g x = x + 1\nlet f x = g x + 99\nlet h x = x * 10\n", tid="theirs")  # f changed
    merged = combine(ours, theirs)
    standing = {r["result_id"] for r in _standing_results(ours)}
    carried = {a["derived_from"][0] for a in merged["artifacts"]
               if a["artifact_type"] == "CarriedForward"}
    rereasoned = set()
    rep = merge(ours, theirs)
    rereasoned = {r["result_id"] for r in rep["rereason"]}
    assert carried | rereasoned == standing
    assert carried.isdisjoint(rereasoned)
    assert carried == {"vrh"}
    assert rereasoned == {"vrf"}


# ---- 5. enrich runs + a carried goal still resolves ------------------------

def test_combine_enriches_and_goal_resolves():
    ours = _trace(SRC, results=[_proved("f")], tid="ours")
    theirs = _trace("let g x = x + 1\nlet f x = g x + 2\nlet h x = x * 999\n", tid="theirs")  # only h
    merged = combine(ours, theirs)
    enriched = goalops.enrich(merged)  # must not raise
    assert enriched is not None
    # the carried result survived into the merged/enriched trace.
    cf = [a for a in enriched["artifacts"] if a["artifact_type"] == "CarriedForward"]
    assert cf and cf[0]["payload"]["symbol"] == "f"


# ---- 6. CLI: --combine -o writes a validate-passing file -------------------

def test_cli_combine_writes_valid_trace(tmp_path):
    ours = _trace(SRC, results=[_proved("f")], tid="ours")
    theirs = _trace("let g x = x + 1\nlet f x = g x + 2\nlet h x = x * 999\n", tid="theirs")
    ours_p = tmp_path / "ours.json"
    theirs_p = tmp_path / "theirs.json"
    merged_p = tmp_path / "merged.json"
    ours_p.write_text(json.dumps(ours))
    theirs_p.write_text(json.dumps(theirs))

    r = _run_cli("trace", "merge", str(ours_p), str(theirs_p), "--combine", "-o", str(merged_p))
    assert r.returncode == 0, r.stderr
    assert merged_p.exists()
    merged = json.loads(merged_p.read_text())
    errors, _ = validate_trace(merged)
    assert errors == [], errors
    assert merged["merge"]["parents"] == ["ours", "theirs"]

    # validate via the CLI too.
    v = _run_cli("trace", "validate", str(merged_p))
    assert v.returncode == 0, v.stderr


def test_cli_merge_default_still_report(tmp_path):
    """Backward-compat: without --combine the CLI still prints the merge REPORT."""
    ours = _trace(SRC, results=[_proved("f")], tid="ours")
    theirs = _trace("let g x = x + 1\nlet f x = g x + 2\nlet h x = x * 999\n", tid="theirs")
    ours_p = tmp_path / "ours.json"
    theirs_p = tmp_path / "theirs.json"
    ours_p.write_text(json.dumps(ours))
    theirs_p.write_text(json.dumps(theirs))
    r = _run_cli("trace", "merge", str(ours_p), str(theirs_p))
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert "carried_forward" in out and "delta" in out
    assert "merge" not in out  # a report, not a trace

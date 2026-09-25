"""Can a replay actually DECIDE whether a verdict came out the same?

Measured against a live ImandraX run, the old answer was no. `cmd_reproduce` compared by substring -
the record's `result_summary` against the engine's raw stdout - and none of `proved`, `refuted`,
`unknown` or `bounded` appears anywhere in that output. Every replay reported DIVERGED on a verdict
that had reproduced exactly, and DIVERGED is the alarming direction.

Recording the JSON-emitting command does not rescue a substring either: `check-vg --json` emits
EVERY verdict key, with `null` for the ones that do not apply, so `"proved" in output` would then be
true always - failing open instead of failing closed, which is worse.

So a record may carry its own check. ponens stays engine-agnostic (a JSON path needs no knowledge of
ImandraX, Lean, or a test runner) while the comparison becomes real.
"""

import pytest

from ponens.trace import _json_path, _replay_ok


PROVED = '{"vg_res_list":[{"vg_res":{"unknown":null,"proved":{"proof_pp":"..."},"refuted":null,' \
         '"verified_upto":null}}]}'
UNKNOWN = '{"vg_res_list":[{"vg_res":{"unknown":{},"proved":null,"refuted":null,' \
          '"verified_upto":null}}]}'


def check(path, **kw):
    return {"kind": "json_path", "path": path, **kw}


# ---- the path resolver ----------------------------------------------------

def test_resolves_dotted_paths_through_lists_and_objects():
    doc = {"a": [{"b": {"c": 1}}]}
    assert _json_path(doc, "a.0.b.c") == 1


def test_a_missing_or_out_of_range_segment_is_absent_not_an_error():
    doc = {"a": [{"b": 1}]}
    assert _json_path(doc, "a.9.b") is None
    assert _json_path(doc, "a.0.nope") is None
    assert _json_path(doc, "a.0.b.c") is None      # descending into a scalar


# ---- the decision ---------------------------------------------------------

def test_a_verdict_that_agrees_reproduces():
    ok, detail = _replay_ok({"check": check("vg_res_list.0.vg_res.proved")}, PROVED, PROVED)
    assert ok is True
    assert "present" in detail


def test_a_verdict_that_changed_diverges_and_says_what_it_looked_for():
    # The engine settled a goal the record left undecided - a real divergence, and the interesting
    # direction: the record UNDERSTATES what is now known.
    ok, detail = _replay_ok({"check": check("vg_res_list.0.vg_res.proved")}, UNKNOWN, UNKNOWN)
    assert ok is False
    assert "vg_res_list.0.vg_res.proved" in detail and "absent" in detail


def test_a_null_verdict_key_does_not_count_as_present():
    # The whole reason a substring cannot work: every key is emitted, most of them null.
    ok, _ = _replay_ok({"check": check("vg_res_list.0.vg_res.refuted")}, PROVED, PROVED)
    assert ok is False


def test_absence_can_be_what_is_asserted():
    ok, _ = _replay_ok({"check": check("vg_res_list.0.vg_res.refuted", present=False)}, PROVED, PROVED)
    assert ok is True


def test_equals_compares_a_value_not_merely_its_presence():
    doc = '{"status":"proved"}'
    assert _replay_ok({"check": check("status", equals="proved")}, doc, doc)[0] is True
    assert _replay_ok({"check": check("status", equals="refuted")}, doc, doc)[0] is False


def test_output_that_is_not_json_diverges_with_a_reason():
    ok, detail = _replay_ok({"check": check("a.b")}, "eval_res: Eval succeed", "eval_res: Eval succeed")
    assert ok is False
    assert "JSON" in detail


# ---- backward compatibility ----------------------------------------------

def test_a_record_with_no_check_still_uses_the_substring_fallback():
    ok, detail = _replay_ok({"result_summary": "12 passed"}, "", "... 12 passed ...")
    assert ok is True and detail is None


def test_the_fallback_still_fails_where_it_always_did():
    # Kept deliberately: older records rely on it, and this is the behaviour that motivated the
    # check field in the first place.
    ok, _ = _replay_ok({"result_summary": "bounded"}, "", "eval_res: Eval succeed POSuccessProof")
    assert ok is False

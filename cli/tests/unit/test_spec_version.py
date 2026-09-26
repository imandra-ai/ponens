"""Version order is numeric, and the guards only ever RAISE.

These were string comparisons, and lexicographic order stops being version order the moment a
component reaches two digits: `"1.14" < "1.8"` is True, because `"1"` sorts before `"8"` at the third
character. Measured on a real record before the fix:

    $ ponens trace residual add t.json --kind limitation --severity low --statement "a note"
    spec_version: 1.14 -> 1.8

A guard written to RAISE the version lowered it, because it read 1.14 as older than 1.8. The same
comparison refused to raise a 1.6 or 1.9 trace to 1.14, so it failed in both directions at once, and
the failures are silent - nothing branches on `spec_version` to parse, so a trace simply misstates
what it is.

The cases below are deliberately heavy on two-digit components, because that is the whole bug.
"""

import pytest

from ponens.trace import parse_spec_version as P, raise_spec_version


# ---- parsing ---------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("1.1", (1, 1)),
    ("1.8", (1, 8)),
    ("1.14", (1, 14)),
    ("1.15.4", (1, 15, 4)),
    ("2.0", (2,)),              # trailing zeros are dropped - see the normalisation test below
    ("v1.14", (1, 14)),          # a stray prefix is still a version
    ("1.14-rc1", (1, 14)),       # ... and so is a suffix
])
def test_parses_to_numeric_components(text, expected):
    assert P(text) == expected


@pytest.mark.parametrize("bad", [None, "", "  ", "not-a-version", {}, []])
def test_unparseable_falls_back_to_the_old_default(bad):
    # `1.1` is what every caller defaulted to when this was a string compare; keeping that means the
    # fix cannot change behaviour for a trace with no version at all.
    assert P(bad) == (1, 1)


def test_a_missing_component_sorts_as_zero():
    assert P("1..3") == (1, 0, 3)


# ---- the orderings the string compare got wrong ----------------------------

@pytest.mark.parametrize("lower,higher", [
    ("1.8", "1.14"),     # THE bug: "1.14" < "1.8" as strings
    ("1.7", "1.14"),
    ("1.9", "1.14"),     # and this one: "1.9" > "1.14" as strings, so 1.9 was never upgraded
    ("1.6", "1.10"),
    ("1.9", "1.10"),
    ("1.1", "1.2"),
    ("1.14", "1.15"),
    ("1.14", "2.0"),
    ("1.15", "1.15.1"),  # a longer version is newer than its prefix
])
def test_numeric_order_where_string_order_lies(lower, higher):
    assert P(lower) < P(higher)
    assert not P(higher) < P(lower)


def test_the_specific_comparisons_the_guards_make():
    # Pinned as literals rather than derived, so a change to the guards has to change this test.
    assert P("1.14") > P("1.8"), "a 1.14 trace must not look older than 1.8"
    assert P("1.14") > P("1.7"), "a 1.14 trace must not look older than 1.7"
    assert P("1.9") < P("1.14"), "a 1.9 trace must be raised to 1.14"
    assert P("1.6") < P("1.14")


@pytest.mark.parametrize("a,b", [
    ("1.15", "1.15.0"),      # the same release written two ways
    ("1.15.0.0", "1.15"),
    ("1", "1.0"),
    ("2.0", "2"),
])
def test_trailing_zeros_carry_no_version_information(a, b):
    # `1.15` and `1.15.0` are one release. A plain tuple compare calls the shorter one OLDER, which
    # would make `raise_spec_version` rewrite the field for no reason - and would disagree with the
    # agent's TS `compareVersions`, which pads to three and reports them equal. Two implementations
    # of one comparison that disagree is the defect this whole fix is about.
    assert P(a) == P(b)


@pytest.mark.parametrize("lower,higher", [
    ("1.15.3", "1.15.4"),     # the release we shipped today
    ("1.15.4", "1.15.10"),    # the two-digit trap, one component further down
    ("1.15.9", "1.15.10"),
    ("1.15.4", "1.16"),
    ("1.15.4", "2.0"),
    ("1.15", "1.15.1"),
])
def test_three_component_versions_order_numerically(lower, higher):
    assert P(lower) < P(higher)
    assert not P(higher) < P(lower)


def test_a_patch_release_does_not_lower_a_trace_at_its_minor(tmp_path=None):
    # If `spec_version` ever carries the PACKAGE version, this is the case that decides it.
    t = {"spec_version": "1.15.4"}
    assert raise_spec_version(t, "1.15") is False
    assert t["spec_version"] == "1.15.4"


def test_equal_versions_are_not_less_than_each_other():
    for v in ("1.1", "1.8", "1.14", "1.15.4"):
        assert not P(v) < P(v)


# ---- the guard ------------------------------------------------------------

def test_raises_an_older_trace():
    t = {"spec_version": "1.6"}
    assert raise_spec_version(t, "1.14") is True
    assert t["spec_version"] == "1.14"


def test_raises_the_two_digit_case_the_string_compare_refused():
    t = {"spec_version": "1.9"}
    assert raise_spec_version(t, "1.14") is True
    assert t["spec_version"] == "1.14"


@pytest.mark.parametrize("current,minimum", [("1.14", "1.8"), ("1.14", "1.7"), ("2.0", "1.14")])
def test_never_lowers_a_newer_trace(current, minimum):
    # The direction that actually corrupted records: writing a 1.8-era construct into a 1.14 trace
    # must not relabel the trace as 1.8.
    t = {"spec_version": current}
    assert raise_spec_version(t, minimum) is False
    assert t["spec_version"] == current


def test_leaves_an_equal_version_alone_and_says_so():
    t = {"spec_version": "1.14"}
    assert raise_spec_version(t, "1.14") is False
    assert t["spec_version"] == "1.14"


def test_a_trace_with_no_version_is_raised():
    t = {}
    assert raise_spec_version(t, "1.14") is True
    assert t["spec_version"] == "1.14"


def test_a_trace_with_junk_is_raised_rather_than_left_broken():
    t = {"spec_version": "banana"}
    assert raise_spec_version(t, "1.8") is True
    assert t["spec_version"] == "1.8"


def test_the_guard_touches_nothing_else():
    t = {"spec_version": "1.6", "artifacts": [1, 2], "goals": ["g"]}
    raise_spec_version(t, "1.14")
    assert t["artifacts"] == [1, 2] and t["goals"] == ["g"]


# ---- no string comparisons left anywhere ----------------------------------

def test_no_string_comparison_of_spec_version_survives_in_the_source():
    # The bug was one idiom repeated at four sites. A fifth would be just as silent, so this asserts
    # the idiom is gone rather than that today's four are fixed.
    import inspect
    import ponens.trace as mod
    src = inspect.getsource(mod)
    for bad in ('spec_version", "1.1") <', "spec_version', '1.1') <"):
        assert bad not in src, f"a string comparison of spec_version is back: {bad}"


# ---- end to end, through the commands that carried the bug -----------------
#
# The unit tests above would not have caught the original defect in its habitat: the idiom was
# inline at four call sites, so there was no function to test. These drive the real commands over a
# real trace file, which is how it was found in the first place.

import json
import subprocess
import sys


def _cli(*args, cwd):
    """Run the CLI from the SOURCE under test, not whatever `ponens` is installed.

    Without this the subprocess resolves `ponens` from site-packages and the test measures the
    released package - which is how this bug survived a release in the first place, and how I first
    "verified" the fix against a binary that did not contain it."""
    import os
    import ponens
    src = os.path.dirname(os.path.dirname(os.path.abspath(ponens.__file__)))
    env = {**os.environ, "PYTHONPATH": src + os.pathsep + os.environ.get("PYTHONPATH", "")}
    return subprocess.run(
        [sys.executable, "-c", "from ponens.cli import main; import sys; sys.exit(main())", *args],
        cwd=cwd, capture_output=True, text=True, env=env)


def _trace(tmp_path, version):
    t = {
        "trace_id": "t", "spec_version": version, "assistant": "x", "model": "m",
        "timestamp": "2026-09-26T00:00:00Z",
        "trigger": {"type": "TaskReceived", "description": "d", "from_user": "u"},
        "outcome": {"type": "ProcessCompleted", "summary": "s"},
        "actions": [{"id": 1, "type": "Formalize", "category": "reasoning", "label": "f",
                     "rationale": "r", "inputs": [], "outputs": []}],
        "artifacts": [], "residuals": [],
    }
    p = tmp_path / "t.json"
    p.write_text(json.dumps(t))
    return p


def _version(p):
    return json.loads(p.read_text())["spec_version"]


def test_declaring_a_residual_does_not_lower_a_newer_trace(tmp_path):
    # The reproduction, verbatim: before the fix this rewrote 1.14 to 1.8.
    p = _trace(tmp_path, "1.14")
    r = _cli("trace", "residual", "add", str(p), "--kind", "limitation",
             "--severity", "low", "--statement", "a note", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert _version(p) == "1.14"


def test_declaring_a_residual_raises_an_older_trace(tmp_path):
    p = _trace(tmp_path, "1.1")
    _cli("trace", "residual", "add", str(p), "--kind", "limitation",
         "--severity", "low", "--statement", "a note", cwd=tmp_path)
    assert _version(p) == "1.8"


def test_a_two_digit_version_is_raised_where_the_string_compare_refused(tmp_path):
    # `"1.9" > "1.14"` lexicographically, so this trace was never raised.
    p = _trace(tmp_path, "1.9")
    _cli("trace", "residual", "add", str(p), "--kind", "limitation",
         "--severity", "low", "--statement", "a note", cwd=tmp_path)
    rid = next(a["artifact_id"] for a in json.loads(p.read_text())["artifacts"]
               if a.get("artifact_type") == "Residual")
    r = _cli("trace", "residual", "resolve", str(p), rid, "--status", "addressed",
             "--justification", "fixed", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert _version(p) == "1.14"


def test_setting_a_goal_does_not_lower_a_newer_trace(tmp_path):
    # The fourth site, guarding 1.7.
    p = _trace(tmp_path, "1.14")
    r = _cli("trace", "goal", "set", str(p), "--intent", "it holds", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert _version(p) == "1.14"

"""The state-transition register is gated against the code and the spec, in both directions.

A register nobody checks is a comment. These make it load-bearing: a new state type in the spec fails
here until it has a row, and a row's claim about HOW a transition is recorded is checked against what
the command actually does - so a transition that quietly goes back to editing in place fails.
"""
import io
import json
import pathlib
import re
import types

import pytest

from ponens import lineage, transitions as X
from ponens import trace as T

ROOT = pathlib.Path(__file__).resolve().parents[3]


def _published_spec_text():
    specs = sorted(
        ((int(m.group(1)), int(m.group(2))), p)
        for p in (ROOT / "spec").glob("TRACE_SPEC_v*.md")
        for m in [re.match(r"TRACE_SPEC_v(\d+)_(\d+)\.md$", p.name)] if m
    )
    return io.open(specs[-1][1], encoding="utf-8").read()


# --- the register covers the spec -------------------------------------------------------------

def test_every_state_type_in_the_spec_has_a_row():
    """Spec -> register. A new `type *_status` with no row here is an uncatalogued transition."""
    text = _published_spec_text()
    declared = set(re.findall(r"^type (\w+_status) =", text, re.M))
    # These are not trace state at all: they classify HOW something was done, and never move.
    not_state = {"reproducibility_status"}
    covered = {t.spec_type for t in X.TRANSITIONS if t.spec_type}
    missing = declared - covered - not_state
    assert not missing, f"state types in the spec with no row in transitions.py: {sorted(missing)}"


def test_every_row_naming_a_spec_type_matches_the_spec_states():
    """Register -> spec. A row whose states drifted from the spec's enum is worse than no row."""
    text = _published_spec_text()
    for t in X.TRANSITIONS:
        if not t.spec_type:
            continue
        m = re.search(r"^type %s =\n((?:\s*\|.*\n)+)" % re.escape(t.spec_type), text, re.M)
        assert m, f"{t.spec_type} is in the register but not in the published spec"
        spec_states = [
            re.sub(r"\s*\(\*.*", "", v).strip(" |").lower().replace("_", "")
            for v in m.group(1).strip().split("\n")
        ]
        spec_states = [c for c in spec_states if c]
        # The spec spells CONSTRUCTORS (`ResidualOpen`, `VrProved`, `UnknownProperty`, `ErrorStatus`);
        # the register uses the wire values that actually land in JSON. A constructor decorates the
        # wire value on either side, so containment is the right test - and the count check below is
        # what stops containment from passing something sloppy.
        assert len(t.states) == len(spec_states), (
            f"{t.spec_type}: register has {len(t.states)} states, spec has {len(spec_states)}")
        for st in t.states:
            wire = st.replace(" ", "").replace("_", "")
            assert any(wire in c for c in spec_states), \
                f"{t.spec_type}: register has '{st}', spec has {sorted(spec_states)}"


def test_the_register_is_internally_well_formed():
    seen = set()
    for t in X.TRANSITIONS:
        assert t.subject not in seen, f"duplicate row: {t.subject}"
        seen.add(t.subject)
        assert t.mode in (X.DERIVED, X.APPENDED, X.APPLIED)
        assert t.states and t.moved_by
        # An APPENDED row must say what the append leaves behind - that artifact IS the record.
        if t.mode == X.APPENDED:
            assert t.recorded_as, f"{t.subject}: appended, but names no record"
        # An APPLIED row must justify itself. An unexplained in-place edit is the thing this file
        # exists to make visible.
        if t.mode == X.APPLIED:
            assert t.note, f"{t.subject}: applied in place with no reason given"


# --- the rows are true of the code ------------------------------------------------------------

def _trace_file(tmp_path):
    t = {"trace_id": "t", "spec_version": "1.14",
         "actions": [{"id": 1, "type": "Formalize", "category": "reasoning", "rationale": "r",
                      "inputs": [], "outputs": ["a1"]}],
         "artifacts": [{"artifact_id": "a1", "artifact_type": "IMLModel", "name": "m",
                        "producer_action_id": 1}],
         "outcome": {"type": "ProcessCompleted", "summary": "d"}}
    f = tmp_path / "t.json"
    f.write_text(json.dumps(t))
    return f


def _ns(**kw):
    return types.SimpleNamespace(**kw)


APPENDED_RECORD_TYPES = {"ResidualResolution", "GoalAmendment"}


def test_every_appended_record_type_is_in_the_policy_vocabulary():
    """A policy must be able to quantify over the record a transition leaves, or the append is only
    half a record - present in the file, invisible to the gate."""
    from ponens.policy_compiler import ARTIFACT_TYPES
    for t in X.TRANSITIONS:
        if t.mode == X.APPENDED and t.recorded_as and not t.recorded_as.startswith("("):
            assert t.recorded_as in ARTIFACT_TYPES, \
                f"{t.subject}: records a {t.recorded_as} that no policy can see"


def test_closing_a_residual_appends_rather_than_edits(tmp_path):
    f = _trace_file(tmp_path)
    T.cmd_residual_add(_ns(trace_file=str(f), kind="assumption", severity="high", statement="s",
                           target_type=None, target_id=None, suggested_check=None, related=None,
                           introduced_by=1, status="open", tag=None))
    before = next(a for a in json.loads(f.read_text())["artifacts"] if a["artifact_type"] == "Residual")
    assert T.cmd_residual_resolve(_ns(trace_file=str(f), residual_id="r1", status="waived",
                                      justification="j", evidence=None, by=None, at=None)) == 0
    after = json.loads(f.read_text())
    assert next(a for a in after["artifacts"] if a["artifact_type"] == "Residual") == before
    assert any(a["artifact_type"] == "ResidualResolution" for a in after["artifacts"])


def test_withdrawing_a_criterion_appends_rather_than_edits(tmp_path):
    f = _trace_file(tmp_path)
    T.cmd_goal_set(_ns(trace_file=str(f), intent="i", scope=None, clause=None, intent_author="human",
                       id="session-goal", json=None, reason=None, by=None))
    T.cmd_goal_accept(_ns(trace_file=str(f), goal="session-goal", kind="change", label="l",
                          symbol=None, property=None, policy_id=None, residual_id=None, file=None,
                          covers=None, optional=False, author="agent", id=None))
    assert T.cmd_goal_drop(_ns(trace_file=str(f), goal="session-goal", item_id="s1",
                               reason="why", by="me")) == 0
    t = json.loads(f.read_text())
    am = lineage.amendments_of(t, "session-goal")
    assert am and am[0]["was"]["label"] == "l", "the withdrawn criterion must survive verbatim"


def _subcommands_offering(option):
    """Every `trace <cmd> [<sub>]` that accepts this option, by dotted name."""
    from ponens.cli import build_parser
    found = []

    def walk(parser, path):
        for a in parser._actions:
            if getattr(a, "choices", None) and isinstance(a.choices, dict):
                for name, sub in a.choices.items():
                    walk(sub, path + [name])
            elif option in (a.option_strings or []):
                found.append(".".join(path))
    walk(build_parser(), [])
    # Only commands that touch a TRACE. `traces ls --status` and `reasoners search --status` take it
    # as a query FILTER over a listing - reading, not asserting.
    return {f for f in found if f.startswith("trace.")}


def test_only_the_appended_transitions_let_a_status_be_asserted():
    """A DERIVED row claims its state is earned, not set. What makes that more than a claim is that
    no command offers to set it: a `--status` on a verification result would quietly turn an earned
    verdict into a declared one. So the set of commands taking `--status` is pinned, and a new one
    has to be justified here."""
    allowed = {
        "trace.residual.add",      # declaring a gap, which is born with a status
        "trace.residual.resolve",  # the appended decision (§13.3a)
        "trace.meta.set",          # the curated narrative layer, not a claim
    }
    got = _subcommands_offering("--status")
    assert got == allowed, (
        f"unexpected command(s) offering --status: {sorted(got - allowed)}; "
        f"missing: {sorted(allowed - got)}. A derived verdict must not become settable.")


def test_the_two_transitions_that_were_edits_are_no_longer(tmp_path):
    """The register's own history: these two rows say they WERE applied in place. If either regresses,
    the note becomes a lie and this fails."""
    residual = next(t for t in X.TRANSITIONS if t.subject == "a residual")
    goal = next(t for t in X.TRANSITIONS if t.subject == "a goal's definition of done")
    assert residual.mode == X.APPENDED and goal.mode == X.APPENDED
    assert "1.14" in residual.note or "APPLIED" in residual.note
    assert "88%" in goal.note, "keep the measurement that motivated it"

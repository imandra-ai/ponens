"""`ponens bind` writes a scorecard into the git note under the Trace-Id line."""
from ponens import sync
from ponens import trace as traceops


def test_note_summary_reads_grade_gate_gaps_and_goals():
    import os
    here = os.path.dirname(__file__)
    t = traceops.load_trace(os.path.join(here, "..", "..", "..", "examples", "stripe_v1_1.json"))
    lines = sync.note_summary(t)
    assert lines[0].startswith("Grade: ")
    assert any(l.startswith("Policies: ") for l in lines)
    assert any(l.startswith("Gaps: ") and "open" in l for l in lines)
    assert any(l.startswith("Goals: ") for l in lines)


def test_note_summary_never_raises_on_a_bare_trace():
    assert sync.note_summary({"trace_id": "x"}) == [] or isinstance(sync.note_summary({"trace_id": "x"}), list)


def test_note_body_keeps_trace_id_first(monkeypatch):
    seen = {}
    monkeypatch.setattr(sync, "_git", lambda *a: (seen.update({"args": a}) or type("R", (), {"returncode": 0})()))
    assert sync.write_trace_note("cl-1", "abc", ["Grade: A (95/100)", "Gaps: 0 open"])
    body = seen["args"][seen["args"].index("-m") + 1]
    assert body.split("\n")[0] == "Trace-Id: cl-1"
    assert "Grade: A (95/100)" in body

"""Smoke test for `ponens agent` — the embedded, self-onboarding workflow guide."""

import types

from ponens.agent import cmd_agent


def test_agent_guide_prints(capsys):
    assert cmd_agent(types.SimpleNamespace(review=False)) == 0
    out = capsys.readouterr().out
    assert "agent guide" in out
    assert "ponens emit" in out and "residual" in out and "grade" in out


def test_review_guide_prints(capsys):
    assert cmd_agent(types.SimpleNamespace(review=True)) == 0
    out = capsys.readouterr().out
    assert "reviewing-agent guide" in out and "reproduce" in out

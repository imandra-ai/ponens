"""`ponens agent` — the embedded, self-onboarding workflow guide, and a contract test that every
command the guide tells an agent to run actually exists in the CLI (so the guide can't drift)."""

import argparse
import re
import types

from ponens.agent import cmd_agent, GUIDE, REVIEW_GUIDE
from ponens.cli import build_parser


def test_agent_guide_prints(capsys):
    assert cmd_agent(types.SimpleNamespace(review=False)) == 0
    out = capsys.readouterr().out
    assert "agent guide" in out
    assert "ponens emit" in out and "residual" in out and "grade" in out


def test_review_guide_prints(capsys):
    assert cmd_agent(types.SimpleNamespace(review=True)) == 0
    out = capsys.readouterr().out
    assert "reviewing-agent guide" in out and "reproduce" in out


# ---- contract: the agent's documented interface matches the real CLI ----------------------------

def _valid_command_paths(parser, prefix=()):
    """Every (sub)command path argparse accepts, e.g. ('trace', 'goal', 'set') — aliases included."""
    out = set()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                out.add(prefix + (name,))
                out |= _valid_command_paths(sub, prefix + (name,))
    return out


def _guide_command_paths(text):
    """The `ponens <sub> <sub> ...` command paths a guide tells the agent to run. Collect the leading
    lowercase subcommand tokens after each `ponens`, stopping at the first arg / flag / file / `ponens`."""
    paths = set()
    for line in text.splitlines():
        toks = line.replace("&&", " ").split()
        i = 0
        while i < len(toks):
            if toks[i] == "ponens":
                path, j = [], i + 1
                while j < len(toks) and toks[j] != "ponens" and re.fullmatch(r"[a-z][a-z0-9-]*", toks[j]):
                    path.append(toks[j])
                    j += 1
                if path:
                    paths.add(tuple(path))
                i = j if j > i else i + 1
            else:
                i += 1
    return paths


def test_every_command_in_the_agent_guides_exists():
    """If the guide names `ponens trace goal set`, that command must be registered — otherwise an agent
    following the guide hits an 'invalid choice' wall. Guards against guide/CLI drift both directions."""
    valid = _valid_command_paths(build_parser())
    referenced = _guide_command_paths(GUIDE) | _guide_command_paths(REVIEW_GUIDE)
    assert referenced, "extractor found no commands in the guides — the guides or the parser changed shape"
    unknown = sorted(p for p in referenced if p not in valid)
    assert not unknown, "agent guide references commands the CLI does not have: " + \
        ", ".join("ponens " + " ".join(p) for p in unknown)


def test_extractor_catches_a_bogus_command():
    """Sanity-check the contract test itself: a fabricated command must be flagged as unknown."""
    valid = _valid_command_paths(build_parser())
    assert ("trace", "definitely-not-a-command") not in valid
    assert _guide_command_paths("run ponens trace definitely-not-a-command foo.json") == \
        {("trace", "definitely-not-a-command")}

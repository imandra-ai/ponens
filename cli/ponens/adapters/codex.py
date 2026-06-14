"""Codex CLI transcript adapter — stub.

Not yet implemented. To add support, mirror `claude_code.py`: read Codex's session
transcript and emit the normalized event stream (directives, todos, and `action` events
with canonical types). Set IMPLEMENTED = True when `parse` is real.
"""
NAME = "codex"
IMPLEMENTED = False

_MSG = "the Codex adapter is not implemented yet — only 'claude-code' is supported today"


def default_transcript():
    return None


def read_entries(path):
    raise NotImplementedError(_MSG)


def parse(entries):
    raise NotImplementedError(_MSG)

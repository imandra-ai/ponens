"""Session-transcript adapters.

Each adapter maps one agent's native transcript format to the normalized event stream
that `emit.build_trace` consumes — so the trace-building core stays agent-agnostic and a
new agent is just a new module here. An adapter module exposes:

    NAME : str
    IMPLEMENTED : bool
    default_transcript() -> str | None
    read_entries(path) -> list
    parse(entries) -> {"events", "model", "assistant", "last_reasoning"}
"""
from . import claude_code, codex, gemini

ADAPTERS = {a.NAME: a for a in (claude_code, gemini, codex)}


def get_adapter(name):
    try:
        return ADAPTERS[name]
    except KeyError:
        raise KeyError(name)


def adapter_names():
    return list(ADAPTERS)

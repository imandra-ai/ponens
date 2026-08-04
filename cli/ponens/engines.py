"""Engine adapters for reproduction replay (Gap 4).

A ReproductionBundle names an ``execution_environment``; an engine adapter turns that environment into
a concrete, safe replay command and PREFLIGHTS whether the engine is actually runnable here (binary on
PATH, credentials present). Pluggable — a new engine (Lean, Z3, …) is one adapter — with a graceful
fallback to the environment's own ``configuration.replay_command`` when no adapter matches.

Keeping the engine specifics HERE (not in the replay loop) is the framework/consumer half of Gap 4:
ponens owns replay execution; ImandraX is just one adapter.
"""
import os
import shutil


class EngineAdapter:
    """Base adapter. Subclasses match an environment, supply a replay command (with a ``{model}``
    placeholder replay substitutes), and preflight the local environment."""

    name = "generic"

    def matches(self, env) -> bool:
        return False

    def replay_command(self, env):
        return ((env or {}).get("configuration") or {}).get("replay_command")

    def preflight(self):
        """Return None if the engine can run here, else a short human reason it cannot."""
        return None


class ImandraXAdapter(EngineAdapter):
    """ImandraX, reached over the Imandra Universe API via ``codelogician-lite`` (a read-only check)."""

    name = "imandrax"
    BINARY = "codelogician-lite"

    def matches(self, env) -> bool:
        env = env or {}
        if env.get("environment_id") == "env-imandrax":
            return True
        name = (env.get("name") or "").lower()
        comps = " ".join((c or {}).get("name", "") for c in env.get("components", []) or []).lower()
        return "imandra" in name or "imandra" in comps

    def replay_command(self, env):
        # Honor an explicit recipe if the trace carries one; otherwise the canonical check command.
        return super().replay_command(env) or f"{self.BINARY} check --with-vgs {{model}}"

    def preflight(self):
        if not shutil.which(self.BINARY):
            return f"{self.BINARY} not on PATH"
        if not (os.environ.get("IMANDRA_UNI_KEY") or os.environ.get("IMANDRAX_API_KEY")):
            return "no Imandra API key (set IMANDRA_UNI_KEY)"
        return None


# Registry — first match wins; register_adapter prepends (tests / a host app override it).
_ADAPTERS = [ImandraXAdapter()]


def register_adapter(adapter):
    _ADAPTERS.insert(0, adapter)


def adapter_for(env):
    for a in _ADAPTERS:
        try:
            if a.matches(env or {}):
                return a
        except Exception:  # noqa: BLE001 — a broken adapter must not abort replay
            continue
    return None

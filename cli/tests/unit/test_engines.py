"""Engine adapters for replay (Gap 4): matching, the replay command (explicit recipe wins over the
default), preflight, the generic fallback, and adapter registration."""
from ponens import engines


def test_imandrax_matches_by_env_id_name_or_component():
    a = engines.ImandraXAdapter()
    assert a.matches({"environment_id": "env-imandrax"})
    assert a.matches({"name": "ImandraX"})
    assert a.matches({"components": [{"name": "imandrax"}]})
    assert not a.matches({"name": "Lean"})


def test_imandrax_replay_command_prefers_explicit_recipe():
    a = engines.ImandraXAdapter()
    # Default when the env carries none.
    assert "codelogician-lite" in a.replay_command({})
    assert "{model}" in a.replay_command({})
    # An explicit recorded recipe wins.
    env = {"configuration": {"replay_command": "custom {model}"}}
    assert a.replay_command(env) == "custom {model}"


def test_imandrax_preflight_reports_missing_key(monkeypatch):
    monkeypatch.delenv("IMANDRA_UNI_KEY", raising=False)
    monkeypatch.delenv("IMANDRAX_API_KEY", raising=False)
    # Pretend the binary exists so we isolate the key check.
    monkeypatch.setattr(engines.shutil, "which", lambda _b: "/usr/bin/codelogician-lite")
    assert "no Imandra API key" in engines.ImandraXAdapter().preflight()


def test_imandrax_preflight_reports_missing_binary(monkeypatch):
    monkeypatch.setattr(engines.shutil, "which", lambda _b: None)
    assert "not on PATH" in engines.ImandraXAdapter().preflight()


def test_imandrax_preflight_ok_when_binary_and_key_present(monkeypatch):
    monkeypatch.setattr(engines.shutil, "which", lambda _b: "/usr/bin/codelogician-lite")
    monkeypatch.setenv("IMANDRA_UNI_KEY", "test-key")
    assert engines.ImandraXAdapter().preflight() is None


def test_adapter_for_falls_back_to_none_for_unknown_engine():
    assert engines.adapter_for({"name": "SomeOtherEngine"}) is None


def test_register_adapter_takes_precedence():
    class Fake(engines.EngineAdapter):
        name = "fake"
        def matches(self, env):
            return True
    fake = Fake()
    engines.register_adapter(fake)
    try:
        assert engines.adapter_for({"name": "ImandraX"}) is fake  # prepended → wins
    finally:
        engines._ADAPTERS.remove(fake)  # keep the registry clean for other tests

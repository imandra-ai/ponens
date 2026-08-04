"""`ponens trace replay` — ReproductionBundle re-execution against the object store (Gap 4).

A bundle references the content-addressed model + the results to reproduce + the engine environment's
replay command. Replay materializes the model from the store and re-runs the command, flagging a
verdict divergence. Dry by default; --run executes the safe-allowlisted command."""
import json
import types

from ponens import objects as ob
from ponens.trace import cmd_replay, _repro_safe


def _args(trace_file, objects_dir, run=False):
    return types.SimpleNamespace(trace_file=str(trace_file), objects_dir=str(objects_dir), run=run)


def _bundle_trace(model_ref, replay_command="codelogician-lite check --with-vgs {model}",
                  expected="proved", env_id="env-test", env_name="TestEngine"):
    # A GENERIC env (no engine adapter matches) → replay runs the env's own replay_command, so the
    # execution tests stay hermetic. Adapter-gated behavior is covered by the ImandraX tests below.
    return {
        "trace_id": "t1",
        "artifacts": [
            {"artifact_id": "m1", "artifact_type": "IMLModel", "content_ref": model_ref, "payload": {}},
            {"artifact_id": "r1", "artifact_type": "VerificationResult",
             "payload": {"status": expected}},
            {"artifact_id": "b1", "artifact_type": "ReproductionBundle", "content_ref": model_ref,
             "payload": {"entry_action_ids": [4], "artifact_ids": ["m1", "r1"],
                         "environment_ids": [env_id]}},
        ],
        "execution_environments": [
            {"environment_id": env_id, "kind": "Service", "name": env_name,
             "configuration": {"replay_command": replay_command}},
        ],
    }


def test_replay_command_verb_is_safe():
    assert _repro_safe("codelogician-lite check --with-vgs model.iml")
    assert not _repro_safe("codelogician check && rm -rf /")  # danger token still vetoes


def test_no_bundles_is_clean(tmp_path):
    f = tmp_path / "t.json"
    f.write_text(json.dumps({"trace_id": "t", "artifacts": [
        {"artifact_id": "x", "artifact_type": "IMLModel"}]}))
    assert cmd_replay(_args(f, tmp_path / "obj")) == 0


def test_dry_run_reports_self_contained_plan(tmp_path, capsys):
    objdir = tmp_path / "obj"
    ref = ob.put_text("let f x = x", str(objdir))  # model IS in the store → self-contained
    f = tmp_path / "t.json"
    f.write_text(json.dumps(_bundle_trace(ref)))
    assert cmd_replay(_args(f, objdir, run=False)) == 0
    out = capsys.readouterr().out
    assert "model=resolved" in out
    assert "would replay" in out


def test_dry_run_flags_missing_object(tmp_path, capsys):
    objdir = tmp_path / "obj"  # empty store → model can't be resolved
    f = tmp_path / "t.json"
    f.write_text(json.dumps(_bundle_trace("sha256:" + "0" * 64)))
    assert cmd_replay(_args(f, objdir, run=False)) == 0  # dry never fails
    assert "model=MISSING" in capsys.readouterr().out


def test_run_missing_object_is_divergence(tmp_path):
    objdir = tmp_path / "obj"
    f = tmp_path / "t.json"
    f.write_text(json.dumps(_bundle_trace("sha256:" + "0" * 64)))
    assert cmd_replay(_args(f, objdir, run=True)) == 1  # can't reproduce → diverged


def test_run_reports_divergence_when_verdict_differs(tmp_path):
    # A safe, deterministic command whose output can't contain the expected verdict → DIVERGED.
    objdir = tmp_path / "obj"
    ref = ob.put_text("let f x = x", str(objdir))
    f = tmp_path / "t.json"
    f.write_text(json.dumps(_bundle_trace(ref, replay_command="git status", expected="proved")))
    assert cmd_replay(_args(f, objdir, run=True)) == 1


def test_run_reproduces_when_output_matches(tmp_path):
    # `ls {model}` echoes the materialized model path; expect a token guaranteed to appear (".iml").
    objdir = tmp_path / "obj"
    ref = ob.put_text("let f x = x", str(objdir))
    f = tmp_path / "t.json"
    f.write_text(json.dumps(_bundle_trace(ref, replay_command="ls {model}", expected=".iml")))
    assert cmd_replay(_args(f, objdir, run=True)) == 0  # output contains ".iml" → reproduced


def test_run_skips_when_engine_not_runnable(tmp_path, monkeypatch, capsys):
    # An ImandraX env with no API key → the adapter preflight blocks replay (not a divergence: we
    # simply can't run the engine here). Exit 0, with a clear "engine not runnable" message.
    monkeypatch.delenv("IMANDRA_UNI_KEY", raising=False)
    monkeypatch.delenv("IMANDRAX_API_KEY", raising=False)
    objdir = tmp_path / "obj"
    ref = ob.put_text("let f x = x", str(objdir))
    f = tmp_path / "t.json"
    f.write_text(json.dumps(_bundle_trace(ref, env_id="env-imandrax", env_name="ImandraX")))
    assert cmd_replay(_args(f, objdir, run=True)) == 0
    assert "engine not runnable here" in capsys.readouterr().out

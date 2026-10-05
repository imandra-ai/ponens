"""A standing result about a SUBJECT - a named scope of code (a service, a module, a protocol), not one definition of
the model - in a merge. Its closure is the model's: the closures of the model symbols its goal maps it to
(`model_symbols`), else every definition of the model. Never the bare subject name, which is in no delta: that carried
such a result forward as untouched when the model it is about changed - falsely fresh."""

from ponens.merge import merge


def _model(src, aid="m1", step=1):
    return {"artifact_id": aid, "artifact_type": "IMLModel", "producer_action_id": step, "payload": {"iml_code": src}}


def _proved(sym, model_symbols=None, vg="vg1", vr="vr1", step=2):
    goal = {"goal_id": vg + "-G", "target_symbol": sym, "description": f"property of {sym}"}
    if model_symbols is not None:
        goal["model_symbols"] = model_symbols
    return [{"artifact_id": vg, "artifact_type": "VerificationGoal", "producer_action_id": step, "payload": goal},
            {"artifact_id": vr, "artifact_type": "VerificationResult", "producer_action_id": step + 1, "derived_from": [vg],
             "payload": {"goal_id": vg + "-G", "goal_artifact_id": vg, "status": "proved"}}]


def _trace(src, results=()):
    t = {"trace_id": "t", "artifacts": [_model(src)]}
    for r in results:
        t["artifacts"].extend(r)
    return t


SRC = "let fee a = if a > 100 then 0 else 3\nlet cap a = if a > 10 then 10 else a\nlet audit x = x\n"


def test_subject_result_rereasoned_when_the_model_changes():
    # "cap rules" is a subject, not a definition. Theirs changes cap: the model it is about changed.
    ours = _trace(SRC, [_proved("cap rules")])
    theirs = _trace(SRC.replace("if a > 10 then 10 else a", "if a < 0 then 0 else if a > 10 then 10 else a"))
    rep = merge(ours, theirs)
    assert rep["delta"]["changed"] == ["cap"]
    assert rep["carried_forward"] == []
    assert [r["result_id"] for r in rep["rereason"]] == ["vr1"]
    assert "about the model as a whole" in rep["rereason"][0]["statement"]
    assert rep["totality_ok"]


def test_subject_mapped_to_model_symbols_carried_when_they_are_untouched():
    # Mapped to fee only: a change to cap does not touch it - carried, with fee's closure.
    ours = _trace(SRC, [_proved("fee rules", model_symbols=["fee"])])
    theirs = _trace(SRC.replace("if a > 10 then 10 else a", "if a < 0 then 0 else if a > 10 then 10 else a"))
    rep = merge(ours, theirs)
    assert [(c["result_id"], c["basis"], c["closure"]) for c in rep["carried_forward"]] == [("vr1", "closure-disjoint", ["fee"])]
    assert rep["rereason"] == []


def test_subject_mapped_to_model_symbols_rereasoned_when_one_changes():
    ours = _trace(SRC, [_proved("fee rules", model_symbols=["fee", "audit"])])
    theirs = _trace(SRC.replace("let audit x = x", "let audit x = x + 0"))
    rep = merge(ours, theirs)
    assert [r["result_id"] for r in rep["rereason"]] == ["vr1"]
    assert rep["rereason"][0]["touched"] == ["audit"]


def test_subject_result_carried_when_nothing_in_the_model_changed():
    ours = _trace(SRC, [_proved("cap rules")])
    rep = merge(ours, _trace(SRC))
    assert [c["result_id"] for c in rep["carried_forward"]] == ["vr1"]


def test_a_definition_keeps_its_own_closure():
    # A result about a definition is unchanged by this: cap's change does not touch fee.
    ours = _trace(SRC, [_proved("fee")])
    theirs = _trace(SRC.replace("if a > 10 then 10 else a", "if a < 0 then 0 else if a > 10 then 10 else a"))
    rep = merge(ours, theirs)
    assert [c["closure"] for c in rep["carried_forward"]] == [["fee"]]

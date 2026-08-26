"""ponens.sdk — a thin runtime SDK for building agents that *speak ponens* natively.

Instead of reconstructing a trace from a transcript after the fact (``ponens emit``), an agent
instruments itself as it runs: open a ``Session``, record actions and artifacts, invoke oracles
for evidence, and on exit get a validated trace that passes ``ponens trace check``.

The SDK is deliberately thin: it builds the same JSON-native trace dict the rest of ``ponens``
already uses (via ``trace.create_empty_trace`` / ``next_action_id`` / ``save_trace``), so there is
exactly one trace model and one code path for constructing artifacts and lineage.

    from ponens.sdk import Session

    with Session(model="claude-opus", assistant="my-agent", path="trace.json",
                 intent="prove charge() is idempotent") as s:
        a = s.action("EditFile", label="edit pricing.py", rationale="fix retry path",
                     evidence=[{"type": "FileRef", "ref": "pricing.py"}])
        model = s.artifact("IMLModel", name="pricing.iml", content=iml_src, format="iml",
                           producer_action_id=a)
        s.verify({"iml_code": iml_src, "goal": "idempotent charge"},
                 oracle="imandra-x", derived_from=model)
"""
from __future__ import annotations

from . import trace as trace_mod
from . import objects as objects_mod
from . import oracles as oracles_mod


class Session:
    """A live reasoning trace under construction.

    Use as a context manager (recommended): on exit it stamps an outcome if none was set,
    validates, externalizes large blobs, and writes ``path`` if one was given.
    """

    def __init__(self, model="example-model", assistant="ponens", path=None,
                 intent=None, trigger=None):
        self.trace = trace_mod.create_empty_trace(model=model, assistant=assistant)
        self.path = path
        if trigger or intent:
            self.trace["trigger"] = {"type": "TaskReceived", "text": trigger or intent}
        if intent:
            self.goal(intent)

    # --- recording primitives ------------------------------------------------

    def action(self, type, label=None, rationale=None, detail=None, category="activity",
               inputs=None, outputs=None, evidence=None):
        """Record a step; returns its integer action id."""
        aid = trace_mod.next_action_id(self.trace)
        act = {
            "id": aid,
            "type": type,
            "category": category,
            "label": label or type,
            "rationale": rationale or "",
            "detail": detail or "",
            "inputs": list(inputs or []),
            "outputs": list(outputs or []),
            "evidence": list(evidence or []),
        }
        self.trace["actions"].append(act)
        return aid

    def artifact(self, artifact_type, name=None, payload=None, derived_from=None,
                 producer_action_id=None, content=None, format=None, role=None):
        """Record a typed artifact; returns its artifact id. Large ``content`` is
        content-addressed into the object store and referenced via ``content_ref``."""
        art_id = trace_mod.next_artifact_id(self.trace)
        art = {
            "artifact_id": art_id,
            "artifact_type": artifact_type,
            "name": name or art_id,
            "derived_from": _as_list(derived_from),
        }
        if role:
            art["artifact_role"] = role
        if format:
            art["format"] = format
        if producer_action_id is not None:
            art["producer_action_id"] = producer_action_id
            for a in self.trace["actions"]:
                if a["id"] == producer_action_id and art_id not in a["outputs"]:
                    a["outputs"].append(art_id)
        if payload is not None:
            art["payload"] = payload
        if content is not None:
            art["content_ref"] = objects_mod.put_text(content)
        self.trace["artifacts"].append(art)
        return art_id

    def goal(self, intent, scope=None, acceptance=None):
        """Declare a goal (intent + optional scope/acceptance). Returns its id."""
        gid = f"g{len(self.trace.get('goals', [])) + 1}"
        self.trace.setdefault("goals", []).append({
            "id": gid,
            "intent": intent,
            "scope": list(scope or []),
            "status": "in_progress",
            "acceptance": list(acceptance or []),
        })
        return gid

    def residual(self, kind, statement, severity="medium", status="open",
                 suggested_check=None, derived_from=None):
        """Declare negative space (an assumption, gap, limitation, ...) as a Residual artifact."""
        payload = {"kind": kind, "severity": severity, "status": status, "statement": statement}
        if suggested_check:
            payload["suggested_check"] = suggested_check
        return self.artifact("Residual", name=f"residual:{kind}", payload=payload,
                             derived_from=derived_from, role="ResidualRole")

    def verify(self, target, oracle, derived_from=None, label=None, rationale=None):
        """Invoke an oracle for evidence and record it.

        ``oracle`` is an oracle id (resolved from the registry) or an ``Oracle`` instance.
        Records a ``Verify`` action and appends the oracle's evidence artifact(s), wiring lineage
        from ``derived_from``. Returns the list of new artifact ids.
        """
        oc = oracle if isinstance(oracle, oracles_mod.Oracle) else oracles_mod.get_oracle(oracle)
        if oc is None:
            raise ValueError(f"unknown oracle: {oracle!r} (see `ponens oracle list`)")
        aid = self.action(
            "Verify", category="reasoning",
            label=label or f"verify with {oc.name}",
            rationale=rationale or f"produce {oc.evidence_strength}-strength evidence via {oc.name}",
            inputs=_as_list(derived_from),
        )
        new_ids = []
        for art in oc.invoke(target):
            art = dict(art)
            art.setdefault("derived_from", _as_list(derived_from))
            aid_art = self.artifact(
                art.pop("artifact_type"),
                name=art.pop("name", None),
                payload=art.pop("payload", None),
                derived_from=art.pop("derived_from", None),
                producer_action_id=aid,
                format=art.pop("format", None),
                role=art.pop("artifact_role", None),
            )
            new_ids.append(aid_art)
        return new_ids

    def outcome(self, type="ProcessCompleted", summary=None):
        self.trace["outcome"] = {"type": type}
        if summary:
            self.trace["outcome"]["summary"] = summary

    # --- lifecycle -----------------------------------------------------------

    def validate(self):
        """Return (errors, warnings) from the structural validator."""
        return trace_mod.validate_trace(self.trace)

    def save(self, path=None, strict=True):
        """Externalize blobs, validate, and write the trace.

        With ``strict`` (the default) structural errors raise. On an aborted run the SDK saves
        with ``strict=False`` so a partial trace is never lost and the original exception is never
        masked."""
        target = path or self.path
        if not target:
            raise ValueError("no path given to save()")
        objects_mod.externalize(self.trace)
        if strict:
            errors, _ = self.validate()
            if errors:
                raise ValueError("trace has structural errors: " + "; ".join(errors))
        trace_mod.save_trace(target, self.trace)
        return target

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            # Record how the run ended and persist the partial trace, but never mask the
            # original exception (best-effort, non-strict save) and never swallow it.
            if not self.trace.get("outcome", {}).get("type"):
                self.outcome("ProcessAborted", summary=str(exc))
            if self.path:
                try:
                    self.save(strict=False)
                except Exception:
                    pass
            return False
        if not self.trace.get("outcome", {}).get("type"):
            self.outcome("ProcessCompleted")
        if self.path:
            self.save()
        return False


def _as_list(x):
    if x is None:
        return []
    return list(x) if isinstance(x, (list, tuple, set)) else [x]

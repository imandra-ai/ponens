"""Oracles — invocable evidence producers, the supertype of *reasoner*.

An **oracle** is anything that produces evidence about a target and returns it as trace
artifacts: a formal reasoner (ImandraX, an SMT solver, a model checker), a test runner, a
static analyzer, an LLM-judge, or a human attestor. This aligns the code with the paper's
vocabulary ("which oracle produced it, under what assumptions") — a *reasoner* is simply the
formal, proof-producing subtype of oracle.

Two orthogonal classifiers:
  - ``oracle_type``       — the *mechanism*  (reasoner | tester | analyzer | judge | attestor)
  - ``evidence_strength`` — the *guarantee*  (proof > sat > tests > static_analysis > attested)

The gallery/catalog side (reference metadata, remote registry) lives in ``reasoners.py`` and is
retained; this module adds the *invocable* runtime side — the ``Oracle`` an SDK ``Session`` can
call to actually produce evidence. See ``spec/ORACLE_SPEC_v0_1.md``.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile

# --- taxonomy ---------------------------------------------------------------

# Mechanism of an oracle. "reasoner" is the formal, proof-producing subtype.
ORACLE_TYPES = ("reasoner", "tester", "analyzer", "judge", "attestor")

# Guarantee carried by an oracle's output, strongest first. `strength_rank` lets callers
# compare/sort evidence (a policy can demand "at least `tests`", a merge can prefer stronger).
EVIDENCE_STRENGTH = ("proof", "sat", "tests", "static_analysis", "attested")

# Legacy `reasoners` catalog `kind` -> oracle_type (all current reasoners are the formal subtype).
_KIND_TO_TYPE = {
    "formal_verification": "reasoner",
    "smt": "reasoner",
    "model_checking": "reasoner",
}


def strength_rank(s: str) -> int:
    """Rank of an evidence strength (0 = strongest). Unknown strengths sort last."""
    return EVIDENCE_STRENGTH.index(s) if s in EVIDENCE_STRENGTH else len(EVIDENCE_STRENGTH)


def oracle_type_for_kind(kind: str | None) -> str:
    """Map a legacy reasoner ``kind`` to an ``oracle_type`` (defaults to ``reasoner``)."""
    return _KIND_TO_TYPE.get(kind or "", "reasoner")


# --- the Oracle base --------------------------------------------------------

class Oracle:
    """Base class for an invocable evidence producer.

    Subclasses set the class attributes and implement ``invoke(target, context) -> [artifact]``,
    returning a list of artifact dicts (without ``artifact_id``/``producer_action_id`` — the SDK
    assigns those). Each artifact's payload should carry ``evidence_strength``.
    """

    id: str = "oracle"
    name: str = "Oracle"
    oracle_type: str = "reasoner"
    evidence_strength: str = "attested"
    produces: tuple[str, ...] = ()
    vendor: str = ""
    description: str = ""

    def invoke(self, target, context=None):  # pragma: no cover - abstract
        raise NotImplementedError

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "oracle_type": self.oracle_type,
            "evidence_strength": self.evidence_strength,
            "produces": list(self.produces),
            "vendor": self.vendor,
            "description": self.description,
        }


# --- the CodeLogician oracle (oracle #1: proof strength) --------------------
# Drives Imandra's `codelogician-lite` CLI (the LLM-friendly front end to the ImandraX engine),
# not the raw engine: `codelogician-lite check-vg <file> --json` executes the `verify`/`instance`
# goals in an IML model and returns per-goal proved / refuted (with counterexample) / bounded / unknown.


def _codelogician_bin():
    """The codelogician-lite command: env override (CODELOGICIAN_CLI) then PATH."""
    return os.environ.get("CODELOGICIAN_CLI") or shutil.which("codelogician-lite")


def _eval_ok(eval_res) -> bool:
    """Did the model admit? `eval_res` is "Success" (string) or {success: bool, ...}."""
    if isinstance(eval_res, str):
        return "success" in eval_res.lower()
    if isinstance(eval_res, dict):
        return eval_res.get("success") is True
    return False


def _verdict_of(vg_res) -> str:
    """Per-goal verdict from a `check-vg` `vg_res` object (proved > refuted > sat > unknown)."""
    if not isinstance(vg_res, dict):
        return "unknown"
    if vg_res.get("refuted"):
        return "refuted"
    if vg_res.get("proved"):
        return "proved"
    if vg_res.get("verified_upto"):
        return "sat"          # bounded — verified up to a depth, not a full proof
    return "unknown"


def _counterexample(vg_res):
    r = vg_res.get("refuted") if isinstance(vg_res, dict) else None
    if isinstance(r, dict):
        return r.get("model_str") or r.get("model") or r.get("src")
    return str(r) if r else None


def _aggregate(verdicts) -> str:
    """Fold per-goal verdicts into one result status (a refutation dominates)."""
    if not verdicts:
        return "unknown"
    if "refuted" in verdicts:
        return "refuted"
    if all(v == "proved" for v in verdicts):
        return "proved"
    if all(v in ("proved", "sat") for v in verdicts):
        return "sat"
    return "unknown"


def _codelogician_lite_runner(target, context=None):
    """Run `codelogician-lite check-vg <file> --json` and aggregate the verdicts.

    `target` is a dict carrying `iml_code` (the model + its verify/instance goals). Returns the
    fields of a VerificationResult payload. Dependency-injectable so tests / CLI-less environments
    don't require the tool. ImandraX (over the CodeLogician CLI) is the engine.
    """
    iml = target.get("iml_code") if isinstance(target, dict) else None
    fingerprint = hashlib.sha256((iml or "").encode("utf-8")).hexdigest()[:16] if iml else None
    binp = _codelogician_bin()
    if not binp or not iml:
        return {"status": "unknown", "engine": "imandrax",
                "result": "codelogician-lite or iml_code unavailable",
                "reasoning_fingerprint": fingerprint}
    fd, path = tempfile.mkstemp(suffix=".iml")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(iml)
        proc = subprocess.run([binp, "check-vg", path, "--json"],
                              capture_output=True, text=True, timeout=600)
        try:
            data = json.loads(proc.stdout)
        except (ValueError, TypeError):
            return {"status": "unknown", "engine": "imandrax",
                    "result": ((proc.stdout or "") + (proc.stderr or "")).strip()[-2000:],
                    "reasoning_fingerprint": fingerprint}
        if not _eval_ok(data.get("eval_res")):
            return {"status": "unknown", "engine": "imandrax",
                    "result": f"admit failed: {data.get('eval_res')}",
                    "reasoning_fingerprint": fingerprint}
        vgs = data.get("vg_res_list") or []
        verdicts = [_verdict_of(v.get("vg_res")) for v in vgs]
        cex = next((_counterexample(v.get("vg_res")) for v in vgs
                    if _verdict_of(v.get("vg_res")) == "refuted"), None)
        return {"status": _aggregate(verdicts), "engine": "imandrax",
                "result": (f"{len(vgs)} VG(s): " + ", ".join(verdicts)) if verdicts
                          else "no verification goals",
                "reasoning_fingerprint": fingerprint, "counterexample": cex}
    except (subprocess.SubprocessError, OSError) as ex:
        return {"status": "unknown", "engine": "imandrax",
                "result": f"codelogician-lite error: {ex}", "reasoning_fingerprint": fingerprint}
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


# Status -> the honest strength of the established evidence (None when nothing was established,
# so an `unknown`/error result never masquerades as graded evidence).
_STATUS_STRENGTH = {"proved": "proof", "refuted": "proof", "sat": "sat"}


class CodeLogicianOracle(Oracle):
    """CodeLogician (ImandraX engine, via `codelogician-lite`) — a proof-strength reasoner oracle.

    `invoke(target)` runs the target's verify/instance goals and returns a `VerificationResult`
    whose `evidence_strength` reflects the *actual* verdict (proved/refuted → proof, bounded → sat,
    otherwise unestablished and unlabeled). The runner is injectable for testing / CLI-less use.
    """

    id = "codelogician"
    name = "CodeLogician"
    oracle_type = "reasoner"
    evidence_strength = "proof"
    produces = ("VerificationResult", "StateSpaceAnalysisResult")
    vendor = "Imandra"
    description = "CodeLogician drives ImandraX (via codelogician-lite) — proof-strength verification."

    def __init__(self, runner=None):
        self.runner = runner or _codelogician_lite_runner

    def invoke(self, target, context=None):
        res = self.runner(target, context)
        goal = target.get("goal") if isinstance(target, dict) else None
        symbol = target.get("target_symbol") if isinstance(target, dict) else None
        status = res.get("status", "unknown")
        payload = {
            "status": status,
            "engine": res.get("engine", "imandrax"),
            "result": res.get("result", ""),
            "reasoning_fingerprint": res.get("reasoning_fingerprint"),
        }
        strength = _STATUS_STRENGTH.get(status)
        if strength:
            payload["evidence_strength"] = strength
        if res.get("counterexample"):
            payload["counterexample"] = res["counterexample"]
        if symbol:
            payload["target_symbol"] = symbol
        return [{
            "artifact_type": "VerificationResult",
            "artifact_role": "CounterexampleRole" if status == "refuted" else "ProofRole",
            "name": f"verify:{goal or symbol or 'target'}",
            "format": "json",
            "payload": payload,
        }]


# --- in-process registry (the invocable oracles) ----------------------------

_REGISTRY: dict[str, Oracle] = {}


def register_oracle(oracle: Oracle) -> None:
    _REGISTRY[oracle.id] = oracle


def get_oracle(oracle_id: str) -> Oracle | None:
    return _REGISTRY.get(oracle_id)


def list_oracles() -> list[Oracle]:
    return list(_REGISTRY.values())


# Built-in oracles available out of the box.
register_oracle(CodeLogicianOracle())


# --- CLI: `ponens oracle list|show` -----------------------------------------

def register(subparsers):
    from .formatting import heading, table, gray, cyan, blue, magenta

    op = subparsers.add_parser(
        "oracle", help="Inspect invocable oracles (reasoner is the formal subtype)")
    sub = op.add_subparsers(dest="oracle_command", required=True)

    def cmd_list(args):
        import json as _json
        rows = [o.as_dict() for o in list_oracles()]
        if getattr(args, "json", False):
            print(_json.dumps(rows, indent=2, ensure_ascii=False))
            return 0
        heading(f"Oracles ({len(rows)})")
        if not rows:
            print(gray("  none registered"))
            return 0
        table(rows, [
            {"label": "ID", "get": lambda e: e["id"], "color": cyan},
            {"label": "Name", "get": lambda e: e.get("name", "")},
            {"label": "Type", "get": lambda e: e.get("oracle_type", ""), "color": magenta},
            {"label": "Evidence", "get": lambda e: e.get("evidence_strength", ""), "color": blue},
            {"label": "Produces", "get": lambda e: ", ".join(e.get("produces", []))},
        ])
        print(gray("\n  a reasoner is the formal, proof-producing subtype of oracle"))
        return 0

    p = sub.add_parser("list", aliases=["ls"], help="List invocable oracles")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_list)

    def cmd_show(args):
        import json as _json
        o = get_oracle(args.oracle_id)
        if not o:
            print(gray(f"  no such oracle: '{args.oracle_id}'"))
            return 1
        print(_json.dumps(o.as_dict(), indent=2, ensure_ascii=False))
        return 0

    p = sub.add_parser("show", help="Show an oracle's definition")
    p.add_argument("oracle_id")
    p.set_defaults(func=cmd_show)

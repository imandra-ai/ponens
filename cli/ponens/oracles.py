"""Oracles - the generic evidence producer (ORACLE_SPEC v0.2).

An **oracle** is anything that answers a question about a target with evidence that lands in the
trace as typed artifacts: a formal reasoner (ImandraX, an SMT solver, a model checker), a test
runner, a static analyzer, **a database or reference-data store queried for a fact**, an LLM judge,
or a human attestor. The framework fixes the *contract* (``invoke``, optionally ``probe``), not the
mechanism. A *reasoner* is simply the formal, proof-producing subtype of oracle.

Two orthogonal classifiers travel with every oracle and with every artifact it produces:
  - ``oracle_type``       - the *mechanism*, an OPEN set of standard names
                            (reasoner | tester | analyzer | monitor | judge | attestor)
  - ``evidence_strength`` - the *guarantee*, a FIXED total order
                            (proof > sat > tests > static_analysis > attested)

Every result carries an attribution block ``payload.oracle`` (§3) and SHOULD carry an evidence
fingerprint ``payload.fingerprint`` (§4) - the subject it answered about - so freshness is defined
for any oracle's evidence, not only a reasoner's.

The gallery/catalog side (reference metadata, remote registry) lives in ``reasoners.py`` and is
retained; this module is the *invocable* runtime side. See ``spec/ORACLE_SPEC_v0_2.md``.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import shutil
import subprocess
import tempfile

# --- taxonomy ---------------------------------------------------------------

# The STANDARD mechanism names. This is a classification, not a closed enumeration (§1.1): a
# consumer must accept a name it does not recognize (it may warn); a producer may register a finer
# name that `specializes` one of these. "reasoner" is the formal, proof-producing subtype.
ORACLE_TYPES = ("reasoner", "tester", "analyzer", "monitor", "judge", "attestor")

# Guarantee carried by an oracle's output, strongest first. LOCKED as of 0.2: it propagates into
# policies, merge and goal resolution. `strength_rank` lets callers compare/sort evidence.
EVIDENCE_STRENGTH = ("proof", "sat", "tests", "static_analysis", "attested")

# The action an invocation is recorded under, by oracle type (§2). Consumers key on the artifact's
# attribution block, not on this name; a producer that cannot distinguish may record `Verify`.
ACTION_FOR_TYPE = {
    "reasoner": "Verify",
    "tester": "Test",
    "analyzer": "Analyze",
    "monitor": "Observe",
    "judge": "Judge",
    "attestor": "Attest",
}

# The freshness verdicts (TRACE_SPEC §18.3, generalized in 1.12).
FRESH, STALE, DETACHED, UNKNOWN = "fresh", "stale", "detached", "unknown"

# Legacy `reasoners` catalog `kind` -> oracle_type (all current reasoners are the formal subtype).
_KIND_TO_TYPE = {
    "formal_verification": "reasoner",
    "smt": "reasoner",
    "model_checking": "reasoner",
}


def strength_rank(s: str) -> int:
    """Rank of an evidence strength (0 = strongest). Unknown / absent strengths sort last."""
    return EVIDENCE_STRENGTH.index(s) if s in EVIDENCE_STRENGTH else len(EVIDENCE_STRENGTH)


def strength_at_least(s, minimum: str) -> bool:
    """Is strength `s` at least as strong as `minimum`? False when `s` is absent or unknown."""
    if s not in EVIDENCE_STRENGTH:
        return False
    return strength_rank(s) <= strength_rank(minimum)


def is_standard_oracle_type(t) -> bool:
    return t in ORACLE_TYPES


def check_oracle_type(t, specializes=None):
    """Validate an `oracle_type` under the OPEN-set rule (§1.1). Returns a warning string or None -
    never an error: an unrecognized mechanism name is admissible so long as the evidence it emits is
    graded honestly by `evidence_strength`."""
    if not t:
        return "missing oracle_type"
    if is_standard_oracle_type(t):
        return None
    if specializes and is_standard_oracle_type(specializes):
        return None
    return (f"non-standard oracle_type '{t}' (standard: {', '.join(ORACLE_TYPES)}); "
            f"declare `specializes` so type filters and policies still match")


def oracle_type_for_kind(kind: str | None) -> str:
    """Map a legacy reasoner ``kind`` to an ``oracle_type``. Reasoner kinds map to `reasoner`; any
    other catalog kind is taken as the oracle_type itself (defaults to ``reasoner`` when absent)."""
    if not kind:
        return "reasoner"
    return _KIND_TO_TYPE.get(kind, kind if kind in ORACLE_TYPES else "reasoner")


def action_type_for(oracle_type, specializes=None) -> str:
    """The action type an invocation of this oracle type is recorded under (§2)."""
    return ACTION_FOR_TYPE.get(oracle_type) or ACTION_FOR_TYPE.get(specializes or "") or "Verify"


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(s):
    if not s or not isinstance(s, str):
        return None
    try:
        d = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=_dt.timezone.utc)
        return d
    except ValueError:
        return None


def subject_checksum(*parts) -> str:
    """A strong, canonical checksum over the parts that make up an evidence SUBJECT (§4): JSON with
    sorted keys, so two producers hashing the same source/query/value agree byte-for-byte."""
    h = hashlib.sha256()
    for p in parts:
        h.update(json.dumps(p, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8"))
        h.update(b"\x00")
    return "sha256:" + h.hexdigest()


# --- attribution and fingerprints (§3, §4) ---------------------------------

def attribution_of(payload) -> dict | None:
    """The attribution block of an evidence payload: `payload.oracle` when present, else DERIVED from
    the reasoner-profile fields of a 0.1 / pre-1.12 payload (`engine` -> id, type `reasoner`,
    `engine_version` -> version, top-level `evidence_strength`). None when nothing attributes it."""
    if not isinstance(payload, dict):
        return None
    block = payload.get("oracle")
    if isinstance(block, dict) and block.get("id"):
        out = dict(block)
        if "evidence_strength" not in out and payload.get("evidence_strength"):
            out["evidence_strength"] = payload["evidence_strength"]
        return out
    fp = payload.get("fingerprint") if isinstance(payload.get("fingerprint"), dict) else {}
    engine = payload.get("engine") or fp.get("engine")
    if not engine:
        return None
    out = {"id": engine, "oracle_type": "reasoner"}
    ver = payload.get("engine_version") or fp.get("engine_version")
    if ver:
        out["version"] = ver
    if payload.get("evidence_strength"):
        out["evidence_strength"] = payload["evidence_strength"]
    return out


def strength_of(payload):
    """The honest strength of THIS result, or None (unranked)."""
    att = attribution_of(payload)
    s = (att or {}).get("evidence_strength") or (payload or {}).get("evidence_strength")
    return s if s in EVIDENCE_STRENGTH else None


def fingerprint_of(payload) -> dict | None:
    """The evidence fingerprint of a payload in GENERIC names (§4), folding the reasoner profile
    (`task_checksum` / `task_shape` / `target_symbol` / `engine` / `engine_version`) onto
    `subject_checksum` / `subject_shape` / `subject_ref` / `oracle_id` / `oracle_version`. None when
    the payload carries no fingerprint with a checksum."""
    if not isinstance(payload, dict):
        return None
    fp = payload.get("fingerprint")
    if not isinstance(fp, dict):
        return None
    out = dict(fp)
    if not out.get("subject_checksum") and out.get("task_checksum"):
        out["subject_checksum"] = out["task_checksum"]
    if not out.get("subject_shape") and out.get("task_shape"):
        out["subject_shape"] = out["task_shape"]
    if not out.get("subject_ref") and out.get("target_symbol"):
        out["subject_ref"] = out["target_symbol"]
    if not out.get("oracle_id") and out.get("engine"):
        out["oracle_id"] = out["engine"]
    if not out.get("oracle_version") and out.get("engine_version"):
        out["oracle_version"] = out["engine_version"]
    if not out.get("subject_checksum"):
        return None
    return out


def make_fingerprint(subject_checksum_, subject_ref=None, oracle=None, subject_shape=None,
                     observed_at=None, valid_until=None) -> dict:
    """Build a generic evidence fingerprint (§4)."""
    fp = {"subject_checksum": subject_checksum_}
    if subject_shape:
        fp["subject_shape"] = subject_shape
    if subject_ref:
        fp["subject_ref"] = subject_ref
    if oracle is not None:
        fp["oracle_id"] = oracle.id
        if getattr(oracle, "version", None):
            fp["oracle_version"] = oracle.version
    if observed_at:
        fp["observed_at"] = observed_at
    if valid_until:
        fp["valid_until"] = valid_until
    return fp


def freshness_of(payload, current=None, now=None, current_oracle_version=None) -> str:
    """The derived freshness verdict for evidence with a generic fingerprint (§4, TRACE_SPEC §18.3):

      1. no current fingerprint and no `valid_until`            -> UNKNOWN
      2. `current` says the subject no longer resolves          -> DETACHED
      3. now > `valid_until`                                     -> STALE
      4. current oracle version advanced past the stored one     -> STALE
      5. `current.subject_checksum` == stored                    -> FRESH, else STALE

    `current` is the CURRENT fingerprint of the subject - from a `probe` or a recomputation - or
    `{"detached": True}` when the subject is gone, or None when it could not be obtained. Reasoner
    results without any fingerprint are NOT decided here (the caller keeps the 1.7 heuristic)."""
    fp = fingerprint_of(payload)
    if not fp:
        return UNKNOWN
    now_dt = _parse_iso(now) if isinstance(now, str) else (now or _dt.datetime.now(_dt.timezone.utc))
    valid_until = _parse_iso(fp.get("valid_until"))
    if current is None and valid_until is None:
        return UNKNOWN
    if isinstance(current, dict) and current.get("detached"):
        return DETACHED
    if valid_until is not None and now_dt is not None and now_dt > valid_until:
        return STALE
    stored_ver = fp.get("oracle_version")
    cur_ver = current_oracle_version or (current.get("oracle_version") if isinstance(current, dict) else None)
    if stored_ver and cur_ver and _version_advanced(cur_ver, stored_ver):
        return STALE
    if current is None:
        return FRESH  # time-boxed only, still within validity
    return FRESH if current.get("subject_checksum") == fp.get("subject_checksum") else STALE


def _version_advanced(cur, stored) -> bool:
    """Has the oracle version advanced? Numeric-dotted versions compare numerically; otherwise any
    difference counts as advanced (a different build may decide differently)."""
    if cur == stored:
        return False

    def parts(v):
        try:
            return [int(x) for x in str(v).strip().lstrip("v").split(".")]
        except ValueError:
            return None
    a, b = parts(cur), parts(stored)
    if a is not None and b is not None:
        return a > b
    return True


# --- the Oracle base --------------------------------------------------------

class Oracle:
    """Base class for an invocable evidence producer (§2).

    Subclasses set the class attributes and implement ``invoke(target, context) -> [artifact]``,
    returning a list of artifact dicts (without ``artifact_id``/``producer_action_id`` - the SDK
    assigns those). Each artifact's payload MUST carry the attribution block (``self.attribution``)
    and SHOULD carry a fingerprint (``make_fingerprint``). ``probe`` is optional: the CURRENT
    fingerprint of a subject the oracle previously answered about, without producing new evidence.
    """

    id: str = "oracle"
    name: str = "Oracle"
    oracle_type: str = "reasoner"
    specializes: str | None = None      # the standard name a non-standard oracle_type refines
    evidence_strength: str = "attested"  # the STRONGEST guarantee this oracle can produce
    produces: tuple[str, ...] = ()
    version: str | None = None
    engine: str | None = None            # the engine this oracle DRIVES, when it is a front end to one
    vendor: str = ""
    description: str = ""

    def invoke(self, target, context=None):  # pragma: no cover - abstract
        raise NotImplementedError

    def probe(self, subject_ref, context=None):
        """The current fingerprint of `subject_ref`, `{"detached": True}` if it no longer resolves,
        or None when this oracle cannot probe (the default)."""
        return None

    @property
    def can_probe(self) -> bool:
        return type(self).probe is not Oracle.probe

    def action_type(self) -> str:
        return action_type_for(self.oracle_type, self.specializes)

    def attribution(self, strength=None) -> dict:
        """The attribution block for a result of THIS oracle (§3). `strength` is the strength of the
        actual result (honesty rule) - absent means unranked (an unknown / errored result)."""
        block = {"id": self.id, "oracle_type": self.oracle_type}
        if self.specializes:
            block["specializes"] = self.specializes
        if self.engine:
            block["engine"] = self.engine
        if strength in EVIDENCE_STRENGTH:
            if strength_rank(strength) < strength_rank(self.evidence_strength):
                raise ValueError(
                    f"oracle {self.id!r} declares capability {self.evidence_strength!r} but graded a "
                    f"result {strength!r} (stronger) - evidence never masquerades as stronger than its oracle")
            block["evidence_strength"] = strength
        if self.version:
            block["version"] = self.version
        return block

    def as_dict(self) -> dict:
        d = {
            "id": self.id,
            "name": self.name,
            "oracle_type": self.oracle_type,
            "evidence_strength": self.evidence_strength,
            "produces": list(self.produces),
            "vendor": self.vendor,
            "description": self.description,
            "can_probe": self.can_probe,
        }
        if self.specializes:
            d["specializes"] = self.specializes
        if self.version:
            d["version"] = self.version
        return d


# --- the CodeLogician oracle (reasoner, proof strength) ---------------------
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
        return "sat"          # bounded - verified up to a depth, not a full proof
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
    """CodeLogician (ImandraX engine, via `codelogician-lite`) - a proof-strength reasoner oracle.

    `invoke(target)` runs the target's verify/instance goals and returns a `VerificationResult`
    whose `evidence_strength` reflects the *actual* verdict (proved/refuted → proof, bounded → sat,
    otherwise unestablished and unlabeled). The runner is injectable for testing / CLI-less use.
    """

    id = "codelogician"
    name = "CodeLogician"
    oracle_type = "reasoner"
    evidence_strength = "proof"
    produces = ("VerificationResult", "StateSpaceAnalysisResult")
    engine = "imandrax"
    vendor = "Imandra"
    description = "CodeLogician drives ImandraX (via codelogician-lite) - proof-strength verification."

    def __init__(self, runner=None, version=None):
        self.runner = runner or _codelogician_lite_runner
        if version:
            self.version = version

    def invoke(self, target, context=None):
        res = self.runner(target, context)
        goal = target.get("goal") if isinstance(target, dict) else None
        symbol = target.get("target_symbol") if isinstance(target, dict) else None
        status = res.get("status", "unknown")
        strength = _STATUS_STRENGTH.get(status)
        payload = {
            "status": status,
            "engine": res.get("engine", "imandrax"),
            "result": res.get("result", ""),
            "reasoning_fingerprint": res.get("reasoning_fingerprint"),
            "oracle": self.attribution(strength),
        }
        if res.get("engine_version"):
            payload["engine_version"] = res["engine_version"]
        if strength:
            payload["evidence_strength"] = strength
        if res.get("counterexample"):
            payload["counterexample"] = res["counterexample"]
        if symbol:
            payload["target_symbol"] = symbol
        # The evidence fingerprint (§4): subject = the reasoning task (the whole model text the runner
        # hashed, until a closure checksum is available), in both the generic and the reasoner names.
        if res.get("reasoning_fingerprint"):
            fp = make_fingerprint(res["reasoning_fingerprint"], subject_ref=symbol, oracle=self)
            fp["task_checksum"] = res["reasoning_fingerprint"]
            fp["engine"] = payload["engine"]
            if symbol:
                fp["target_symbol"] = symbol
            payload["fingerprint"] = fp
        return [{
            "artifact_type": "VerificationResult",
            "artifact_role": "CounterexampleRole" if status == "refuted" else "ProofRole",
            "name": f"verify:{goal or symbol or 'target'}",
            "format": "json",
            "payload": payload,
        }]


# --- reference oracles across the spectrum (§8) -----------------------------

class ReferenceDataOracle(Oracle):
    """A **database / reference-data store** as an oracle (`monitor`, `attested`) - the instance that
    proves the abstraction is generic.

    `invoke({"query": q, "statement"?: s, "valid_until"?: t})` runs the lookup and returns an
    `Observation`: *the source stated this value at this time in answer to this query*. The
    fingerprint's subject is (source, query, value, as-of), so the evidence goes STALE when the source
    republishes (`probe` re-runs the lookup and the checksum moves), and DETACHED when the subject is
    gone (the lookup raises `LookupError`) - never when code changes. Strength is `attested`, never
    higher, however authoritative the store.

    Back it with anything: `lookup(query) -> value` (a callable), a mapping (`from_mapping`), or a
    SQLite database (`from_sqlite`, where `query` is SQL).
    """

    oracle_type = "monitor"
    evidence_strength = "attested"
    produces = ("Observation",)

    def __init__(self, id, source, lookup, name=None, version=None, description=None,
                 default_valid_until=None, clock=None):
        self.id = id
        self.name = name or id
        self.source = source
        self._lookup = lookup
        self.version = version
        self.description = description or f"reference data from {source}"
        self.default_valid_until = default_valid_until
        self._clock = clock or now_iso
        self._queries = {}   # subject_ref -> query, remembered at invoke for probe()

    @classmethod
    def from_mapping(cls, id, source, mapping, **kw):
        def lookup(q):
            if q not in mapping:
                raise LookupError(q)
            return mapping[q]
        return cls(id, source, lookup, **kw)

    @classmethod
    def from_sqlite(cls, id, path, source=None, **kw):
        import sqlite3

        def lookup(q):
            con = sqlite3.connect(path)
            try:
                cur = con.execute(q)
                cols = [c[0] for c in cur.description] if cur.description else []
                return [dict(zip(cols, row)) for row in cur.fetchall()]
            except sqlite3.OperationalError as ex:  # a missing table / column: the subject is gone
                raise LookupError(str(ex)) from ex
            finally:
                con.close()
        return cls(id, source or os.path.basename(str(path)), lookup, **kw)

    def subject_ref(self, query) -> str:
        return f"{self.source}:{subject_checksum(query)[7:23]}"

    def _fingerprint(self, query, value, observed_at, valid_until):
        return make_fingerprint(subject_checksum(self.source, query, value), subject_ref=self.subject_ref(query),
                                oracle=self, observed_at=observed_at, valid_until=valid_until)

    def invoke(self, target, context=None):
        query = target.get("query") if isinstance(target, dict) else target
        self._queries[self.subject_ref(query)] = query   # so a later probe(subject_ref) finds the query
        observed_at = self._clock()
        valid_until = (target.get("valid_until") if isinstance(target, dict) else None) or self.default_valid_until
        try:
            value = self._lookup(query)
        except LookupError as ex:
            # The subject cannot be read: an unranked, unestablished observation (honesty rule).
            payload = {"statement": f"{self.source} could not answer {query!r}: {ex}",
                       "source": self.source, "query": query, "observed_at": observed_at,
                       "status": "unknown", "oracle": self.attribution(None)}
            return [{"artifact_type": "Observation", "artifact_role": "AuditEvidenceRole",
                     "name": f"observe:{self.source}", "format": "json", "payload": payload}]
        statement = (target.get("statement") if isinstance(target, dict) else None) \
            or f"{self.source} answered {query!r} with {json.dumps(value, default=str)[:200]}"
        payload = {
            "statement": statement,
            "source": self.source,
            "query": query,
            "value": value,
            "observed_at": observed_at,
            "status": "observed",
            "oracle": self.attribution("attested"),
            "fingerprint": self._fingerprint(query, value, observed_at, valid_until),
        }
        if valid_until:
            payload["valid_until"] = valid_until
        # The code component the observation is ABOUT (e.g. the function whose premise it checks), so a
        # goal criterion `has(settle, Observation)` roots in it precisely (Trace Spec §18 lineage rooting).
        if isinstance(target, dict) and target.get("target_symbol"):
            payload["target_symbol"] = target["target_symbol"]
        return [{"artifact_type": "Observation", "artifact_role": "AuditEvidenceRole",
                 "name": f"observe:{self.source}", "format": "json", "payload": payload}]

    def probe(self, subject_ref, context=None):
        """Re-run the lookup for a subject (a `subject_ref` minted by this oracle, or a raw query) and
        return its CURRENT fingerprint; `{"detached": True}` when the subject no longer resolves."""
        query = (context or {}).get("query") if isinstance(context, dict) else None
        if query is None:
            query = self._queries.get(subject_ref, subject_ref)
        try:
            value = self._lookup(query)
        except LookupError:
            return {"detached": True}
        return self._fingerprint(query, value, self._clock(), None)


class SubprocessTesterOracle(Oracle):
    """A **test runner** as an oracle (`tester`, `tests`): run a command, and the process exit status is
    the verdict - the one signal every runner on every platform agrees on. Produces a `CommandResult`
    with `status` passed | failed (strength `tests` either way: a failing run is empirical evidence
    too) or `error` when the command could not run (unranked)."""

    id = "subprocess-tester"
    name = "Subprocess test runner"
    oracle_type = "tester"
    evidence_strength = "tests"
    produces = ("CommandResult",)
    description = "Runs a test command; the exit status is the verdict."

    def __init__(self, runner=None, version=None):
        self._runner = runner or self._run
        if version:
            self.version = version

    @staticmethod
    def _run(command, cwd=None, timeout=None):
        proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout or 600)
        return {"exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}

    def invoke(self, target, context=None):
        command = target.get("command") if isinstance(target, dict) else target
        if isinstance(command, str):
            command = command.split()
        cwd = target.get("cwd") if isinstance(target, dict) else None
        subject = target.get("subject") if isinstance(target, dict) else None
        subject_ref = (target.get("subject_ref") if isinstance(target, dict) else None) or " ".join(command)
        try:
            res = self._runner(command, cwd=cwd, timeout=(target.get("timeout") if isinstance(target, dict) else None))
        except (subprocess.SubprocessError, OSError) as ex:
            payload = {"command": command, "status": "error", "result": str(ex), "oracle": self.attribution(None)}
            return [{"artifact_type": "CommandResult", "artifact_role": "AuditEvidenceRole",
                     "name": f"test:{subject_ref}", "format": "json", "payload": payload}]
        status = "passed" if res.get("exit_code") == 0 else "failed"
        payload = {
            "command": command,
            "exit_code": res.get("exit_code"),
            "status": status,
            "result": (res.get("stdout") or "")[-2000:],
            "stderr": (res.get("stderr") or "")[-2000:],
            "oracle": self.attribution("tests"),
            "fingerprint": make_fingerprint(subject_checksum(command, subject), subject_ref=subject_ref,
                                            oracle=self, observed_at=now_iso()),
        }
        return [{"artifact_type": "CommandResult", "artifact_role": "AuditEvidenceRole",
                 "name": f"test:{subject_ref}", "format": "json", "payload": payload}]


class CallableJudgeOracle(Oracle):
    """A **judge** oracle (`attested`): a heuristic assessor - an LLM-as-judge, a rubric grader - wrapped
    as `judge(target) -> {"verdict": str, "score"?: number, "note"?: str}`. Produces an `AnalysisNote`
    whose subject is the judged content plus the rubric. Its evidence is an opinion, graded `attested`
    and never higher."""

    oracle_type = "judge"
    evidence_strength = "attested"
    produces = ("AnalysisNote",)

    def __init__(self, id, judge, name=None, version=None, description=None):
        self.id = id
        self.name = name or id
        self._judge = judge
        self.version = version
        self.description = description or "heuristic assessment"

    def invoke(self, target, context=None):
        t = target if isinstance(target, dict) else {"content": target}
        try:
            res = self._judge(t) or {}
        except Exception as ex:  # noqa: BLE001 - a judge that fails yields an unranked note
            payload = {"statement": f"judge failed: {ex}", "status": "unknown", "oracle": self.attribution(None)}
            return [{"artifact_type": "AnalysisNote", "name": f"judge:{self.id}", "format": "json", "payload": payload}]
        verdict = res.get("verdict", "unknown")
        payload = {
            "statement": res.get("note") or f"{self.name}: {verdict}",
            "verdict": verdict,
            "status": "judged",
            "rubric": t.get("rubric"),
            "oracle": self.attribution("attested"),
            "fingerprint": make_fingerprint(
                subject_checksum(t.get("content_ref") or t.get("content"), t.get("rubric")),
                subject_ref=t.get("artifact_id") or t.get("content_ref"), oracle=self, observed_at=now_iso()),
        }
        if "score" in res:
            payload["score"] = res["score"]
        return [{"artifact_type": "AnalysisNote", "name": f"judge:{self.id}", "format": "json", "payload": payload}]


class AttestorOracle(Oracle):
    """An **attestor** oracle (`attested`): a human or external sign-off recorded as a `UserApproval`.
    `invoke({"claim_ref"|"artifact_id": ..., "disposition": "approved"|"rejected", "role"?, "note"?,
    "signer"?})`. The subject is the attested artifact (by id / content_ref), so the sign-off is
    STALE if that artifact is superseded by different content."""

    id = "attestor"
    name = "Human attestor"
    oracle_type = "attestor"
    evidence_strength = "attested"
    produces = ("UserApproval",)
    description = "Records a human / external sign-off on a claim."

    def __init__(self, signer=None, version=None):
        self.signer = signer
        if version:
            self.version = version

    def invoke(self, target, context=None):
        t = target if isinstance(target, dict) else {"claim_ref": target}
        claim = t.get("claim_ref") or t.get("artifact_id") or t.get("content_ref")
        disposition = t.get("disposition", "approved")
        signer = t.get("signer") or self.signer or "unknown"
        payload = {
            "statement": t.get("note") or f"{signer} {disposition} {claim}",
            "signer": signer,
            "disposition": disposition,
            "status": disposition,
            "oracle": self.attribution("attested"),
            "fingerprint": make_fingerprint(subject_checksum(claim, t.get("content_ref")), subject_ref=claim,
                                            oracle=self, observed_at=now_iso()),
        }
        if t.get("role"):
            payload["role"] = t["role"]
        return [{"artifact_type": "UserApproval", "artifact_role": "AuditEvidenceRole",
                 "name": f"attest:{claim}", "format": "json", "payload": payload}]


# --- in-process registry (the invocable oracles) ----------------------------

_REGISTRY: dict[str, Oracle] = {}


def register_oracle(oracle: Oracle) -> None:
    _REGISTRY[oracle.id] = oracle


def unregister_oracle(oracle_id: str) -> None:
    _REGISTRY.pop(oracle_id, None)


def get_oracle(oracle_id: str) -> Oracle | None:
    return _REGISTRY.get(oracle_id)


def list_oracles(oracle_type=None) -> list[Oracle]:
    out = list(_REGISTRY.values())
    if oracle_type:
        out = [o for o in out if o.oracle_type == oracle_type or o.specializes == oracle_type]
    return out


def producer_names(payload) -> set:
    """Every name a result's producer answers to: the attribution id, the engine it drives (from the
    block, the payload's legacy `engine`, or the registered oracle's declared `engine`), and any
    registered oracle that drives that engine. This is what `produced_by(X)` matches against, so
    `codelogician` and `imandrax` both name a CodeLogician-over-ImandraX result - including on a
    pre-1.12 payload that carries only `engine`."""
    att = attribution_of(payload) or {}
    names = set()
    for n in (att.get("id"), att.get("engine"), (payload or {}).get("engine")):
        if n:
            names.add(n)
    for n in list(names):
        o = get_oracle(n)
        if o is not None and o.engine:
            names.add(o.engine)
    for o in list_oracles():
        if o.engine and o.engine in names:
            names.add(o.id)
    return names


def produced_by(payload, x) -> bool:
    return bool(x) and x in producer_names(payload)


def probe_evidence(payload, context=None, extra=None):
    """The CURRENT fingerprint of an evidence payload's subject via the oracle that produced it (the
    registry, or `extra`: a session-local id -> oracle map), or None when it is unknown / cannot probe."""
    fp = fingerprint_of(payload)
    if not fp:
        return None
    oid = fp.get("oracle_id") or ""
    o = (extra or {}).get(oid) or get_oracle(oid)
    if o is None or not o.can_probe:
        return None
    return o.probe(fp.get("subject_ref"), context)


# Built-in oracles available out of the box.
register_oracle(CodeLogicianOracle())
register_oracle(SubprocessTesterOracle())
register_oracle(AttestorOracle())
# A reference-data store, when the environment names one (a SQLite file): the database-as-oracle.
if os.environ.get("PONENS_REFERENCE_DB"):
    register_oracle(ReferenceDataOracle.from_sqlite(
        os.environ.get("PONENS_REFERENCE_DB_ID", "reference-data"), os.environ["PONENS_REFERENCE_DB"]))


# --- CLI: `ponens oracle list|show|probe` -----------------------------------

def register(subparsers):
    from .formatting import heading, table, gray, cyan, blue, magenta

    op = subparsers.add_parser(
        "oracle", help="Inspect invocable oracles (reasoner, tester, analyzer, monitor, judge, attestor)")
    sub = op.add_subparsers(dest="oracle_command", required=True)

    def cmd_list(args):
        rows = [o.as_dict() for o in list_oracles(getattr(args, "type", None))]
        if getattr(args, "json", False):
            print(json.dumps(rows, indent=2, ensure_ascii=False))
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
            {"label": "Probe", "get": lambda e: "yes" if e.get("can_probe") else ""},
        ])
        print(gray("\n  an oracle is any evidence producer; a reasoner is the formal, proof-producing subtype"))
        return 0

    p = sub.add_parser("list", aliases=["ls"], help="List invocable oracles")
    p.add_argument("--json", action="store_true")
    p.add_argument("--type", help="Filter by oracle_type (standard or registered name)")
    p.set_defaults(func=cmd_list)

    def cmd_show(args):
        o = get_oracle(args.oracle_id)
        if not o:
            print(gray(f"  no such oracle: '{args.oracle_id}'"))
            return 1
        print(json.dumps(o.as_dict(), indent=2, ensure_ascii=False))
        return 0

    p = sub.add_parser("show", help="Show an oracle's definition")
    p.add_argument("oracle_id")
    p.set_defaults(func=cmd_show)

    def cmd_probe(args):
        o = get_oracle(args.oracle_id)
        if not o:
            print(gray(f"  no such oracle: '{args.oracle_id}'"))
            return 1
        if not o.can_probe:
            print(gray(f"  oracle '{args.oracle_id}' cannot probe"))
            return 1
        print(json.dumps(o.probe(args.subject_ref, {"query": args.query} if args.query else None),
                         indent=2, ensure_ascii=False, default=str))
        return 0

    p = sub.add_parser("probe", help="Re-read a subject's current fingerprint via an oracle (no new evidence)")
    p.add_argument("oracle_id")
    p.add_argument("subject_ref")
    p.add_argument("--query", help="The query, when the subject_ref was minted elsewhere")
    p.set_defaults(func=cmd_probe)

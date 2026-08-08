"""Cryptographic signing of a reasoning trace — non-repudiation for audit sign-off.

A signer signs the trace's `content_hash` (sync.content_hash) with their **private** key; anyone
verifies with the **public** key. The signature does two things at once: detects **tampering** (it is
over the content digest, so any later edit breaks it) and identifies **who** signed. Signatures live
in `trace["signatures"]`, which is EXCLUDED from `content_hash` (see sync.HASH_EXCLUDE), so multiple
parties can co-sign the *same* content.

Backend: OpenSSH signatures (`ssh-keygen -Y sign|verify`) — no new dependencies, reuses the keys
people already have, and verification is fully **offline**. A signature is only *trusted* when its key
appears in an **allowed-signers** roster (git's model); otherwise it is crypto-valid but *untrusted*.
"""

import base64
import datetime
import hashlib
import os
import shutil
import subprocess
import tempfile
import urllib.request

from . import sync

NAMESPACE = "ponens-trace"  # domain separator, so a ponens signature can't be replayed elsewhere


def available():
    return shutil.which("ssh-keygen") is not None


def _openssl():
    return shutil.which("openssl") is not None


def _run(argv, inp=None):
    return subprocess.run(argv, input=inp, capture_output=True, text=True)


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _require():
    if not available():
        raise RuntimeError("ssh-keygen not found — install OpenSSH to sign/verify traces")


def timestamp_signature(signature, tsa_url, timeout=30):
    """Obtain an RFC-3161 **trusted timestamp** over `signature` from the TSA at `tsa_url`. Returns a
    timestamp record (the TSA-signed token + its asserted time) that `verify_timestamp` checks offline
    against the TSA's certificate — proving the signature existed by that time, independent of any
    machine clock."""
    if not _openssl():
        raise RuntimeError("openssl not found — needed for RFC-3161 trusted timestamps")
    digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()
    q = subprocess.run(["openssl", "ts", "-query", "-digest", digest, "-sha256", "-cert"],
                       capture_output=True)
    if q.returncode != 0:
        raise RuntimeError(f"openssl ts -query failed: {q.stderr.decode('utf-8', 'replace').strip()}")
    req = urllib.request.Request(tsa_url, data=q.stdout,
                                 headers={"Content-Type": "application/timestamp-query"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            reply = resp.read()
    except Exception as e:
        raise RuntimeError(f"TSA request to {tsa_url} failed: {e}")
    return {"standard": "rfc3161", "tsa": tsa_url, "hash_alg": "sha256",
            "message_imprint": digest, "token": base64.b64encode(reply).decode(),
            "time": _tst_time(reply)}


def _tst_time(reply_der):
    """The genTime the TSA asserted, parsed from an RFC-3161 reply (for display)."""
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "reply.tsr")
        with open(f, "wb") as fh:
            fh.write(reply_der)
        t = subprocess.run(["openssl", "ts", "-reply", "-in", f, "-text"], capture_output=True)
        for line in t.stdout.decode("utf-8", "replace").splitlines():
            if "Time stamp:" in line:
                return line.split("Time stamp:", 1)[1].strip()
    return None


def verify_timestamp(sig_rec, tsa_ca_path=None):
    """Verify a signature's RFC-3161 timestamp. Returns None if absent, else a verdict:
      - "invalid"   : the token doesn't cover the current signature, or fails against the TSA cert;
      - "untrusted" : token present + covers the signature, but no TSA CA was given to trust it;
      - "valid"     : verified against the TSA CA — a trusted "existed by <time>"."""
    ts = sig_rec.get("timestamp")
    if not ts:
        return None
    # Pure data check first (no engine): does the token still cover the current signature?
    digest = hashlib.sha256((sig_rec.get("signature") or "").encode("utf-8")).hexdigest()
    if digest != ts.get("message_imprint"):
        return {"status": "invalid", "time": ts.get("time"), "tsa": ts.get("tsa"),
                "detail": "timestamp does not cover the current signature"}
    if not _openssl():
        return {"status": "unknown", "time": ts.get("time"), "detail": "openssl not found"}
    ca = os.path.expanduser(tsa_ca_path) if tsa_ca_path else None
    with tempfile.TemporaryDirectory() as d:
        tsr = os.path.join(d, "reply.tsr")
        try:
            with open(tsr, "wb") as fh:
                fh.write(base64.b64decode(ts.get("token") or ""))
        except Exception:
            return {"status": "invalid", "time": ts.get("time"), "detail": "malformed timestamp token"}
        if ca and os.path.exists(ca):
            v = subprocess.run(["openssl", "ts", "-verify", "-digest", digest, "-in", tsr, "-CAfile", ca],
                               capture_output=True)
            if v.returncode == 0:
                return {"status": "valid", "time": ts.get("time"), "tsa": ts.get("tsa"),
                        "detail": "trusted timestamp"}
            return {"status": "invalid", "time": ts.get("time"), "tsa": ts.get("tsa"),
                    "detail": v.stderr.decode("utf-8", "replace").strip() or "timestamp verification failed"}
        return {"status": "untrusted", "time": ts.get("time"), "tsa": ts.get("tsa"),
                "detail": "timestamp present; pass --tsa-ca to verify it against the TSA certificate"}


def sign_trace(trace, key_path, signer=None, role=None, disposition=None, when=None, tsa=None):
    """Sign `trace`'s content_hash with the SSH private key at `key_path`; append a signature record
    to `trace["signatures"]` and return it. With `tsa` (a TSA URL), also attach an RFC-3161 trusted
    timestamp over the signature."""
    _require()
    key_path = os.path.expanduser(key_path)
    if not os.path.exists(key_path):
        raise RuntimeError(f"private key not found: {key_path}")
    ch = sync.content_hash(trace)

    r = _run(["ssh-keygen", "-Y", "sign", "-f", key_path, "-n", NAMESPACE], inp=ch)
    if r.returncode != 0:
        raise RuntimeError(f"ssh-keygen sign failed: {r.stderr.strip()}")
    signature = r.stdout

    pub = _run(["ssh-keygen", "-y", "-f", key_path]).stdout.strip()   # "ssh-ed25519 AAAA… comment"
    parts = pub.split()
    key_type = parts[0] if parts else None
    comment = " ".join(parts[2:]) if len(parts) > 2 else None
    fp = _run(["ssh-keygen", "-lf", "-"], inp=pub).stdout.strip()      # "256 SHA256:… comment (ED25519)"
    key_id = next((t for t in fp.split() if t.startswith("SHA256:")), None)

    rec = {
        "signer": signer or comment or "unknown",
        "content_hash": ch,
        "algo": "ssh",
        "key_type": key_type,
        "key_id": key_id,
        "public_key": pub,
        "namespace": NAMESPACE,
        "signed_at": when or _now(),
        "signature": signature,
    }
    if role:
        rec["role"] = role
    if disposition:
        rec["disposition"] = disposition
    if tsa:
        rec["timestamp"] = timestamp_signature(signature, tsa)  # RFC-3161 trusted "existed by <time>"
    trace.setdefault("signatures", []).append(rec)
    return rec


def verify_trace(trace, allowed_signers_path=None, tsa_ca_path=None):
    """Verify every signature on `trace`. Returns a list of per-signature verdicts:
      - "tampered"  : content_hash no longer matches — the trace changed since signing;
      - "invalid"   : the signature does not verify against its key;
      - "untrusted" : crypto-valid, but the key is not in the allowed-signers roster (or none given);
      - "valid"     : crypto-valid AND the key is a recognised signer in the roster.
    Each entry also carries `timestamp` (the RFC-3161 verdict from `verify_timestamp`) when the
    signature was timestamped."""
    _require()
    ch = sync.content_hash(trace)
    roster = os.path.expanduser(allowed_signers_path) if allowed_signers_path else None
    have_roster = bool(roster and os.path.exists(roster))
    out = []
    for rec in trace.get("signatures", []) or []:
        signer = rec.get("signer") or "unknown"
        ts_verdict = verify_timestamp(rec, tsa_ca_path)
        base = {"signer": signer, "key_id": rec.get("key_id"),
                "role": rec.get("role"), "disposition": rec.get("disposition")}
        if ts_verdict:
            base["timestamp"] = ts_verdict
        if rec.get("content_hash") != ch:
            out.append({**base, "status": "tampered",
                        "detail": "content_hash no longer matches — the trace changed since signing"})
            continue
        with tempfile.TemporaryDirectory() as d:
            sigf = os.path.join(d, "sig")
            with open(sigf, "w") as f:
                f.write(rec.get("signature", ""))
            if have_roster:
                af = roster
            else:
                af = os.path.join(d, "allowed_signers")
                with open(af, "w") as f:
                    f.write(f"{signer} {rec.get('public_key', '')}\n")
            v = _run(["ssh-keygen", "-Y", "verify", "-f", af, "-I", signer, "-n", NAMESPACE, "-s", sigf],
                     inp=ch)
            if v.returncode == 0:
                out.append({**base, "status": "valid" if have_roster else "untrusted",
                            "detail": "verified" if have_roster
                                      else "crypto-valid; key not checked against an allowed-signers roster"})
            else:
                out.append({**base, "status": "invalid", "detail": v.stderr.strip()})
    return out

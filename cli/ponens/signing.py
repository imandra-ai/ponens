"""Cryptographic signing of a reasoning trace — non-repudiation for audit sign-off.

A signer signs the trace's `content_hash` (sync.content_hash) with their **private** key/identity; anyone
verifies with the **public** key/identity. The signature does two things at once: detects **tampering**
(it is over the content digest, so any later edit breaks it) and identifies **who** signed. Signatures
live in `trace["signatures"]`, which is EXCLUDED from `content_hash` (see sync.HASH_EXCLUDE), so multiple
parties can co-sign the *same* content, each with whatever backend they trust.

Pluggable backends (each signature records its `algo`, and `verify_trace` dispatches on it):
  - **ssh**      OpenSSH signatures (`ssh-keygen -Y sign|verify`) — no new deps, reuses existing keys,
                 verifies fully **offline**. Trust: the key is in an **allowed-signers** roster (git's model).
  - **gpg**      GnuPG detached signatures (`gpg --detach-sign|--verify`). The signer's public key is
                 inlined on the record so verification is **offline** against an ephemeral keyring; trust:
                 the key fingerprint is in a **gpg roster** (an allowed-fingerprints file).
  - **sigstore** Keyless, identity-bound signing (`sigstore sign|verify`, PyPI): a short-lived Fulcio
                 certificate binds the signature to an **OIDC identity** (email + issuer) and the proof is
                 recorded in the **Rekor** public transparency log. Trust: the cert identity matches an
                 expected `--identity`/`--oidc-issuer`. No long-lived key to manage or leak.

Across all backends the verdicts are uniform: **tampered** (content_hash changed), **invalid** (crypto
fails), **untrusted** (crypto-valid but the signer isn't established by a roster/identity), **valid**
(crypto-valid AND the signer is a recognised/expected party).
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


# ── SSH backend (OpenSSH signatures) ────────────────────────────────────────────

def _sign_ssh(content_hash, key_path=None, signer=None):
    if not available():
        raise RuntimeError("ssh-keygen not found — install OpenSSH to sign with the ssh backend")
    key_path = os.path.expanduser(key_path or "~/.ssh/id_ed25519")
    if not os.path.exists(key_path):
        raise RuntimeError(f"private key not found: {key_path}")
    r = _run(["ssh-keygen", "-Y", "sign", "-f", key_path, "-n", NAMESPACE], inp=content_hash)
    if r.returncode != 0:
        raise RuntimeError(f"ssh-keygen sign failed: {r.stderr.strip()}")
    signature = r.stdout
    pub = _run(["ssh-keygen", "-y", "-f", key_path]).stdout.strip()   # "ssh-ed25519 AAAA… comment"
    parts = pub.split()
    comment = " ".join(parts[2:]) if len(parts) > 2 else None
    fp = _run(["ssh-keygen", "-lf", "-"], inp=pub).stdout.strip()      # "256 SHA256:… comment (ED25519)"
    key_id = next((t for t in fp.split() if t.startswith("SHA256:")), None)
    return {"signer": signer or comment or "unknown", "key_type": parts[0] if parts else None,
            "key_id": key_id, "public_key": pub, "namespace": NAMESPACE, "signature": signature}


def _verify_ssh(content_hash, rec, allowed_signers_path=None):
    if not available():
        return "unknown", "ssh-keygen not installed — cannot verify the ssh signature"
    roster = os.path.expanduser(allowed_signers_path) if allowed_signers_path else None
    have_roster = bool(roster and os.path.exists(roster))
    signer = rec.get("signer") or "unknown"
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
                 inp=content_hash)
    if v.returncode == 0:
        return ("valid", "verified") if have_roster else \
               ("untrusted", "crypto-valid; key not checked against an allowed-signers roster")
    return "invalid", v.stderr.strip()


# ── GPG backend (GnuPG detached signatures) ──────────────────────────────────────

def _gpg():
    return shutil.which("gpg") or shutil.which("gpg2")


def _sign_gpg(content_hash, signer=None):
    gpg = _gpg()
    if not gpg:
        raise RuntimeError("gpg not found — install GnuPG to sign with the gpg backend")
    with tempfile.TemporaryDirectory() as d:
        data = os.path.join(d, "data")
        with open(data, "w") as f:
            f.write(content_hash)
        argv = [gpg, "--batch", "--yes", "--armor", "--status-fd", "2", "--detach-sign"]
        if signer:
            argv += ["--local-user", signer]
        argv += ["--output", "-", data]
        r = subprocess.run(argv, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"gpg sign failed: {r.stderr.strip() or 'no secret key?'}")
        signature = r.stdout
        # [GNUPG:] SIG_CREATED <type> <pk_algo> <hash_algo> <class> <ts> <fingerprint>
        fpr = next((ln.split()[-1] for ln in r.stderr.splitlines() if "SIG_CREATED" in ln), None)
        # Inline the ascii-armored public key so verification is offline (independent of the verifier's
        # keyring), and read the primary uid for a human signer label.
        export_sel = [fpr] if fpr else ([signer] if signer else [])
        pub = subprocess.run([gpg, "--armor", "--export", *export_sel], capture_output=True, text=True).stdout.strip()
        uid = None
        if fpr:
            lk = subprocess.run([gpg, "--with-colons", "--list-keys", fpr], capture_output=True, text=True).stdout
            uid = next((ln.split(":")[9] for ln in lk.splitlines()
                        if ln.startswith("uid:") and len(ln.split(":")) > 9 and ln.split(":")[9]), None)
    return {"signer": signer or uid or (f"gpg:{fpr}" if fpr else "unknown"), "key_type": "gpg",
            "key_id": fpr, "public_key": pub or None, "signature": signature}


def _load_fpr_roster(path):
    """A gpg roster: one allowed key fingerprint per line (`#` comments, spaces ignored)."""
    allowed = set()
    for line in open(path, encoding="utf-8"):
        f = line.split("#", 1)[0].strip().replace(" ", "").upper()
        if f:
            allowed.add(f)
    return allowed


def _verify_gpg(content_hash, rec, roster_path=None):
    gpg = _gpg()
    if not gpg:
        return "unknown", "gpg not installed — cannot verify the gpg signature"
    pub, sig = rec.get("public_key"), rec.get("signature")
    if not pub or not sig:
        return "invalid", "missing public key or signature"
    with tempfile.TemporaryDirectory() as home:
        os.chmod(home, 0o700)
        env = {**os.environ, "GNUPGHOME": home}
        subprocess.run([gpg, "--batch", "--import"], input=pub, capture_output=True, text=True, env=env)
        data, sigf = os.path.join(home, "data"), os.path.join(home, "sig.asc")
        with open(data, "w") as f:
            f.write(content_hash)
        with open(sigf, "w") as f:
            f.write(sig)
        v = subprocess.run([gpg, "--batch", "--status-fd", "2", "--verify", sigf, data],
                           capture_output=True, text=True, env=env)
    if "GOODSIG" not in v.stderr and "VALIDSIG" not in v.stderr:
        return "invalid", (v.stderr.strip().splitlines() or ["signature does not verify"])[-1]
    vfpr = next((ln.split()[2] for ln in v.stderr.splitlines()
                 if "VALIDSIG" in ln and len(ln.split()) >= 3), None)
    roster = os.path.expanduser(roster_path) if roster_path else None
    if roster and os.path.exists(roster):
        match = (vfpr or rec.get("key_id") or "").replace(" ", "").upper()
        if match and match in _load_fpr_roster(roster):
            return "valid", "verified; fingerprint in the gpg roster"
        return "untrusted", "crypto-valid; fingerprint not in the gpg roster"
    return "untrusted", "crypto-valid; no --gpg-roster given to establish trust"


# ── sigstore backend (keyless, identity-bound; Rekor transparency log) ────────────

def _sign_sigstore(content_hash, signer=None, oidc_issuer=None, identity_token=None):
    if not shutil.which("sigstore"):
        raise RuntimeError("sigstore not found — `pip install sigstore` for keyless, identity-bound signing")
    with tempfile.TemporaryDirectory() as d:
        data = os.path.join(d, "data")
        bundle = os.path.join(d, "trace.sigstore.json")
        with open(data, "w") as f:
            f.write(content_hash)
        argv = ["sigstore", "sign", "--bundle", bundle]
        if identity_token:
            argv += ["--identity-token", identity_token]
        if oidc_issuer:
            argv += ["--oidc-issuer", oidc_issuer]
        argv += [data]
        r = subprocess.run(argv, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"sigstore sign failed: {r.stderr.strip()}")
        with open(bundle, encoding="utf-8") as f:
            bundle_json = f.read()
    # The Fulcio cert in the bundle binds the signature to the OIDC identity; `signer` should be that
    # identity (email). The proof is recorded in Rekor (public transparency log) by `sigstore sign`.
    return {"signer": signer or "unknown", "key_type": "sigstore", "key_id": None,
            "bundle": bundle_json, "signature": bundle_json, "oidc_issuer": oidc_issuer,
            "transparency_log": "rekor"}


def _verify_sigstore(content_hash, rec, expect_identity=None, oidc_issuer=None):
    if not shutil.which("sigstore"):
        return "unknown", "sigstore not installed — cannot verify (pip install sigstore)"
    bundle = rec.get("bundle") or rec.get("signature")
    if not bundle:
        return "invalid", "missing sigstore bundle"
    identity = expect_identity or rec.get("signer")
    issuer = oidc_issuer or rec.get("oidc_issuer")
    if not identity or identity == "unknown" or not issuer:
        return "untrusted", ("crypto material present, but no expected identity/issuer to bind it to "
                             "(pass --identity and --oidc-issuer)")
    with tempfile.TemporaryDirectory() as d:
        data = os.path.join(d, "data")
        bf = os.path.join(d, "trace.sigstore.json")
        with open(data, "w") as f:
            f.write(content_hash)
        with open(bf, "w") as f:
            f.write(bundle)
        v = subprocess.run(["sigstore", "verify", "identity", "--bundle", bf,
                            "--cert-identity", identity, "--cert-oidc-issuer", issuer, data],
                           capture_output=True, text=True)
    if v.returncode == 0:
        return "valid", f"verified against identity {identity} (Rekor-logged)"
    return "invalid", (v.stderr.strip().splitlines() or ["identity verification failed"])[-1]


# ── Dispatch ─────────────────────────────────────────────────────────────────────

_SIGN = {"ssh": _sign_ssh, "gpg": _sign_gpg, "sigstore": _sign_sigstore}


def sign_trace(trace, key_path=None, signer=None, role=None, disposition=None, when=None, tsa=None,
               algo="ssh", oidc_issuer=None, identity_token=None):
    """Sign `trace`'s content_hash with backend `algo` (ssh | gpg | sigstore); append a signature record
    to `trace["signatures"]` and return it. `key_path` is the ssh/gpg key (ssh path or gpg key id via
    `signer`); sigstore is keyless (OIDC). With `tsa` (a TSA URL), also attach an RFC-3161 trusted
    timestamp over the signature (redundant for sigstore, which is already Rekor-logged)."""
    ch = sync.content_hash(trace)
    if algo == "ssh":
        fields = _sign_ssh(ch, key_path, signer)
    elif algo == "gpg":
        fields = _sign_gpg(ch, signer)
    elif algo == "sigstore":
        fields = _sign_sigstore(ch, signer, oidc_issuer, identity_token)
    else:
        raise RuntimeError(f"unknown signing backend: {algo!r} (choose ssh | gpg | sigstore)")
    rec = {"signer": fields.get("signer") or "unknown", "content_hash": ch, "algo": algo,
           "signed_at": when or _now(), **{k: v for k, v in fields.items() if k != "signer"}}
    if role:
        rec["role"] = role
    if disposition:
        rec["disposition"] = disposition
    if tsa:
        rec["timestamp"] = timestamp_signature(fields["signature"], tsa)  # RFC-3161 trusted "existed by <time>"
    trace.setdefault("signatures", []).append(rec)
    return rec


def verify_trace(trace, allowed_signers_path=None, tsa_ca_path=None, gpg_roster_path=None,
                 expect_identity=None, oidc_issuer=None):
    """Verify every signature on `trace`, dispatching on each record's `algo` (default "ssh" for legacy
    records). Returns a list of per-signature verdicts:
      - "tampered"  : content_hash no longer matches — the trace changed since signing;
      - "invalid"   : the signature does not verify against its key/identity;
      - "untrusted" : crypto-valid, but the signer isn't established (no roster / no expected identity);
      - "valid"     : crypto-valid AND the signer is a recognised/expected party;
      - "unknown"   : the backend's tool isn't installed here, so it couldn't be checked.
    Each entry also carries `timestamp` (the RFC-3161 verdict) when the signature was timestamped."""
    ch = sync.content_hash(trace)
    out = []
    for rec in trace.get("signatures", []) or []:
        signer = rec.get("signer") or "unknown"
        algo = rec.get("algo", "ssh")
        ts_verdict = verify_timestamp(rec, tsa_ca_path)
        base = {"signer": signer, "key_id": rec.get("key_id"), "algo": algo,
                "role": rec.get("role"), "disposition": rec.get("disposition")}
        if ts_verdict:
            base["timestamp"] = ts_verdict
        if rec.get("content_hash") != ch:
            out.append({**base, "status": "tampered",
                        "detail": "content_hash no longer matches — the trace changed since signing"})
            continue
        if algo == "ssh":
            status, detail = _verify_ssh(ch, rec, allowed_signers_path)
        elif algo == "gpg":
            status, detail = _verify_gpg(ch, rec, gpg_roster_path)
        elif algo == "sigstore":
            status, detail = _verify_sigstore(ch, rec, expect_identity, oidc_issuer)
        else:
            status, detail = "invalid", f"unknown signing backend: {algo!r}"
        out.append({**base, "status": status, "detail": detail})
    return out

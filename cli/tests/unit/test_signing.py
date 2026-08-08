"""Unit tests for cryptographic trace signing (ponens.signing) — sign with a private key,
verify with the public key, detect tampering, trust via an allowed-signers roster."""

import base64
import hashlib
import os
import shutil
import subprocess

import pytest

from ponens import signing, sync

pytestmark = pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="ssh-keygen not available")
_HAS_OPENSSL = shutil.which("openssl") is not None


def _keypair(tmp_path, comment="tester@acme", name="id_ed25519"):
    key = tmp_path / name
    subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", comment, "-f", str(key)],
                   check=True, capture_output=True)
    return str(key)


def _trace():
    return {"trace_id": "t", "artifacts": [{"artifact_id": "a1", "artifact_type": "SourceCode"}]}


def test_sign_appends_record_over_content_hash(tmp_path):
    key = _keypair(tmp_path)
    t = _trace()
    rec = signing.sign_trace(t, key, signer="tester@acme", role="auditor", disposition="approved")
    assert rec["content_hash"] == sync.content_hash(t)
    assert rec["content_hash"].startswith("sha256:")
    assert rec["role"] == "auditor" and rec["disposition"] == "approved"
    assert rec["signature"].startswith("-----BEGIN SSH SIGNATURE-----")
    assert t["signatures"][0] is rec


def test_signature_is_excluded_from_content_hash(tmp_path):
    # Signing must not change the very content it signs (so parties can co-sign the same hash).
    key = _keypair(tmp_path)
    t = _trace()
    h0 = sync.content_hash(t)
    signing.sign_trace(t, key, signer="tester@acme")
    assert sync.content_hash(t) == h0


def test_verify_untrusted_without_roster(tmp_path):
    key = _keypair(tmp_path)
    t = _trace()
    signing.sign_trace(t, key, signer="tester@acme")
    res = signing.verify_trace(t)                       # no roster -> crypto-valid but untrusted
    assert len(res) == 1 and res[0]["status"] == "untrusted"


def test_verify_valid_with_roster(tmp_path):
    key = _keypair(tmp_path)
    t = _trace()
    rec = signing.sign_trace(t, key, signer="tester@acme")
    roster = tmp_path / "allowed_signers"
    roster.write_text(f"tester@acme {rec['public_key']}\n")
    res = signing.verify_trace(t, allowed_signers_path=str(roster))
    assert res[0]["status"] == "valid"


def test_tamper_is_detected(tmp_path):
    key = _keypair(tmp_path)
    t = _trace()
    signing.sign_trace(t, key, signer="tester@acme")
    t["artifacts"].append({"artifact_id": "a2", "artifact_type": "Diff"})   # mutate signed content
    res = signing.verify_trace(t)
    assert res[0]["status"] == "tampered"


def test_wrong_key_in_roster_is_invalid(tmp_path):
    key = _keypair(tmp_path)
    t = _trace()
    signing.sign_trace(t, key, signer="tester@acme")
    # roster maps the identity to a DIFFERENT key -> signature won't verify against it
    other = _keypair(tmp_path, comment="x", name="other_ed25519")
    otherpub = subprocess.run(["ssh-keygen", "-y", "-f", other], capture_output=True, text=True).stdout.strip()
    roster = tmp_path / "allowed_signers"
    roster.write_text(f"tester@acme {otherpub}\n")
    res = signing.verify_trace(t, allowed_signers_path=str(roster))
    assert res[0]["status"] == "invalid"


# ── RFC-3161 trusted timestamp ──────────────────────────────────────────────────

def _ts_rec(signed_over, token=b"dummy"):
    return {"signature": signed_over,
            "timestamp": {"standard": "rfc3161", "tsa": "http://tsa.example",
                          "message_imprint": hashlib.sha256(signed_over.encode()).hexdigest(),
                          "token": base64.b64encode(token).decode(), "time": "Aug  8 12:00:00 2026 GMT"}}


def test_timestamp_absent_returns_none():
    assert signing.verify_timestamp({"signature": "x"}) is None


def test_timestamp_invalid_when_signature_changed():
    rec = _ts_rec("ORIGINAL")
    rec["signature"] = "CHANGED"                 # signature swapped -> imprint no longer matches
    assert signing.verify_timestamp(rec)["status"] == "invalid"


@pytest.mark.skipif(not _HAS_OPENSSL, reason="openssl not available")
def test_timestamp_untrusted_without_ca():
    v = signing.verify_timestamp(_ts_rec("SIGDATA"))   # present + covers sig, but no TSA CA to trust it
    assert v["status"] == "untrusted"


@pytest.mark.skipif(not (_HAS_OPENSSL and os.environ.get("PONENS_TEST_TSA")),
                    reason="set PONENS_TEST_TSA=<tsa url> for a live RFC-3161 round-trip")
def test_live_rfc3161_roundtrip(tmp_path):
    key = _keypair(tmp_path)
    t = _trace()
    signing.sign_trace(t, key, signer="tester@acme", tsa=os.environ["PONENS_TEST_TSA"])
    assert t["signatures"][0]["timestamp"]["standard"] == "rfc3161"
    res = signing.verify_trace(t)                 # no CA -> present-but-untrusted, but must parse
    assert res[0]["timestamp"]["status"] in ("untrusted", "valid")


# ── GPG backend ─────────────────────────────────────────────────────────────────
_HAS_GPG = bool(shutil.which("gpg") or shutil.which("gpg2"))


def _gen_gpg_key(email="gpgtester@acme"):
    """Generate an unattended, passphrase-less ed25519 signing key in the ambient GNUPGHOME; return
    (email, fingerprint)."""
    gpg = shutil.which("gpg") or shutil.which("gpg2")
    subprocess.run([gpg, "--batch", "--pinentry-mode", "loopback", "--passphrase", "",
                    "--quick-generate-key", email, "ed25519", "sign", "0"],
                   check=True, capture_output=True)
    out = subprocess.run([gpg, "--with-colons", "--list-keys", email],
                         capture_output=True, text=True).stdout
    fpr = next(ln.split(":")[9] for ln in out.splitlines() if ln.startswith("fpr:"))
    return email, fpr


@pytest.fixture
def gpg_home(monkeypatch):
    # A SHORT GNUPGHOME: the gpg-agent unix socket lives at $GNUPGHOME/S.gpg-agent and must stay under
    # the ~104-char sun_path limit — pytest's tmp_path is far too long (agent fails to start on macOS).
    import tempfile
    home = tempfile.mkdtemp(prefix="pgpg-", dir="/tmp")
    os.chmod(home, 0o700)
    monkeypatch.setenv("GNUPGHOME", home)
    yield home
    subprocess.run(["gpgconf", "--kill", "all"], env={**os.environ, "GNUPGHOME": home}, capture_output=True)
    shutil.rmtree(home, ignore_errors=True)


@pytest.mark.skipif(not _HAS_GPG, reason="gpg not available")
def test_gpg_sign_inlines_pubkey_and_verifies_untrusted_without_roster(gpg_home):
    email, fpr = _gen_gpg_key()
    t = _trace()
    rec = signing.sign_trace(t, signer=email, algo="gpg")
    assert rec["algo"] == "gpg" and rec["key_id"] == fpr and rec["signer"] == email
    assert rec["signature"].startswith("-----BEGIN PGP SIGNATURE-----")
    assert rec["public_key"].startswith("-----BEGIN PGP PUBLIC KEY BLOCK-----")
    # verify uses the INLINED pubkey in an ephemeral keyring -> crypto-valid but untrusted (no roster).
    res = signing.verify_trace(t)
    assert res[0]["status"] == "untrusted" and res[0]["algo"] == "gpg"


@pytest.mark.skipif(not _HAS_GPG, reason="gpg not available")
def test_gpg_valid_when_fingerprint_in_roster(gpg_home, tmp_path):
    email, fpr = _gen_gpg_key()
    t = _trace()
    signing.sign_trace(t, signer=email, algo="gpg")
    roster = tmp_path / "gpg_roster"
    roster.write_text(f"# auditors\n{fpr}\n")
    res = signing.verify_trace(t, gpg_roster_path=str(roster))
    assert res[0]["status"] == "valid"


@pytest.mark.skipif(not _HAS_GPG, reason="gpg not available")
def test_gpg_untrusted_when_fingerprint_not_in_roster(gpg_home, tmp_path):
    email, _fpr = _gen_gpg_key()
    t = _trace()
    signing.sign_trace(t, signer=email, algo="gpg")
    roster = tmp_path / "gpg_roster"
    roster.write_text("DEADBEEF" * 5 + "\n")               # a different fingerprint
    res = signing.verify_trace(t, gpg_roster_path=str(roster))
    assert res[0]["status"] == "untrusted"


@pytest.mark.skipif(not _HAS_GPG, reason="gpg not available")
def test_gpg_tamper_is_detected(gpg_home):
    email, _fpr = _gen_gpg_key()
    t = _trace()
    signing.sign_trace(t, signer=email, algo="gpg")
    t["artifacts"].append({"artifact_id": "a2", "artifact_type": "Diff"})   # mutate signed content
    res = signing.verify_trace(t)
    assert res[0]["status"] == "tampered"


# ── sigstore backend + dispatch ──────────────────────────────────────────────────

@pytest.mark.skipif(bool(shutil.which("sigstore")), reason="sigstore present — this tests the absent path")
def test_sigstore_sign_requires_the_tool():
    with pytest.raises(RuntimeError, match="sigstore not found"):
        signing.sign_trace(_trace(), algo="sigstore", signer="a@b.com",
                           oidc_issuer="https://accounts.example")


@pytest.mark.skipif(bool(shutil.which("sigstore")), reason="sigstore present — this tests the absent path")
def test_sigstore_verify_is_unknown_without_the_tool():
    t = _trace()
    t["signatures"] = [{"signer": "a@b.com", "algo": "sigstore", "content_hash": sync.content_hash(t),
                        "bundle": "{}", "signature": "{}", "oidc_issuer": "https://accounts.example"}]
    res = signing.verify_trace(t, expect_identity="a@b.com", oidc_issuer="https://accounts.example")
    assert res[0]["status"] == "unknown" and res[0]["algo"] == "sigstore"


def test_unknown_backend_verifies_as_invalid():
    t = _trace()
    t["signatures"] = [{"signer": "x", "algo": "weird", "content_hash": sync.content_hash(t)}]
    assert signing.verify_trace(t)[0]["status"] == "invalid"

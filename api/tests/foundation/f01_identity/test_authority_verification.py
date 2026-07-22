"""AI-CONTEXT: F1 operating-authority verification (Decision 190). The FMCSA
lookup is a key-gated seam mirroring F9: FakeAuthorityVerifier runs in tests,
FmcsaVerifier only when a webKey is set. Verification STRENGTHENS credibility —
it never changes can_invoice (kept self-declared for <60 s onboarding).
"""

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f01_identity.domain import verifier as vmod


def test_fake_verifier_resolves_active_carrier():
    result = identity.FakeAuthorityVerifier().verify("MC-123456", "1000001")
    assert result.found is True
    assert result.allowed_to_operate is True
    assert result.mc_number == "123456"  # non-digits stripped
    assert result.dot_number == "1000001"
    assert result.legal_name


def test_fake_verifier_without_identifier_is_not_found():
    result = identity.FakeAuthorityVerifier().verify(None, None)
    assert result.found is False
    assert result.allowed_to_operate is False


def test_verify_authority_records_verified_state(db):
    account = identity.register_account(db, "owner@example.com", "pw-123456")
    identity.upsert_driver_profile(db, account, authority_type=identity.AuthorityType.own_mc)
    profile = identity.verify_authority(db, account, "123456", "1000001")
    assert profile.authority_verify_status == identity.VerifyStatus.verified
    assert profile.authority_verified_at is not None
    assert profile.legal_name
    assert profile.mc_number == "123456"


def test_verify_authority_not_authorized_is_failed(db):
    account = identity.register_account(db, "denied@example.com", "pw-123456")
    profile = identity.verify_authority(
        db, account, "999999", None, verifier=identity.FakeAuthorityVerifier(deny=True)
    )
    assert profile.authority_verify_status == identity.VerifyStatus.failed
    assert profile.authority_verified_at is None
    assert profile.legal_name is None  # no unverified name is ever surfaced


def test_verification_does_not_change_can_invoice(db):
    # company driver stays evidence-only even after a verified lookup — verification
    # strengthens credibility but never grants the right to invoice.
    account = identity.register_account(db, "company@example.com", "pw-123456")
    identity.upsert_driver_profile(db, account, authority_type=identity.AuthorityType.company)
    profile = identity.verify_authority(db, account, "123456", None)
    assert profile.authority_verify_status == identity.VerifyStatus.verified
    assert identity.can_invoice(profile) is False


def test_resolve_verifier_is_fake_without_key():
    # conftest clears FMCSA_WEBKEY, so the default resolver stays deterministic.
    assert isinstance(identity.resolve_verifier(), identity.FakeAuthorityVerifier)


def test_fmcsa_verifier_maps_carrier_record(monkeypatch):
    # the real adapter shape: a QCMobile carrier dict -> VerificationResult, with
    # the network call monkeypatched (no HTTP in tests).
    monkeypatch.setattr(
        vmod,
        "_fmcsa_lookup",
        lambda key, mc, dot: {
            "legalName": "REAL CARRIER INC",
            "dotNumber": 1000001,
            "allowedToOperate": "Y",
        },
    )
    result = vmod.FmcsaVerifier("test-key").verify("123456", "1000001")
    assert result.found is True
    assert result.allowed_to_operate is True
    assert result.legal_name == "REAL CARRIER INC"


def test_fmcsa_verifier_network_error_is_not_found(monkeypatch):
    def boom(key, mc, dot):
        raise RuntimeError("network down")

    monkeypatch.setattr(vmod, "_fmcsa_lookup", boom)
    result = vmod.FmcsaVerifier("test-key").verify("123456", None)
    assert result.found is False


def test_stub_verifier_fails_loud():
    with pytest.raises(NotImplementedError):
        vmod.StubAuthorityVerifier().verify("123456", None)

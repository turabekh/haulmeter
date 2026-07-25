"""AI-CONTEXT: E2 — self-reported equipment registration (plate, unit, VIN).

The honesty line these tests defend: the VIN is FORMAT-checked so a typo is caught
at entry, and nothing more. No decode service is called, no vehicle fact is
inferred, and no field anywhere claims the equipment was verified (§11.7).
"""

import pytest

from app.foundation.f01_identity import public as identity

# real-shape VINs with correct ISO-3779 check digits
VALID_VIN = "1FUJGLDR9CSBF4183"  # Freightliner Cascadia
VALID_VIN_X_CHECK = "1M1AN07YXEM011508"  # check digit 10 renders as "X"


def _account(db, email="equip@example.com"):
    return identity.register_account(db, email, "pw-123456")


def test_profile_stores_plate_unit_and_vin(db):
    account = _account(db)
    profile = identity.upsert_driver_profile(
        db,
        account,
        plate_state="TX",
        plate_number="4XN2291",
        unit_number="118",
        vin=VALID_VIN,
    )
    assert (profile.plate_state, profile.plate_number) == ("TX", "4XN2291")
    assert profile.unit_number == "118"
    assert profile.vin == VALID_VIN


def test_equipment_is_additive_and_does_not_disturb_authority(db):
    # E2 fields sit alongside the existing authority/dimension fields, no rework
    account = _account(db, "additive@example.com")
    identity.upsert_driver_profile(db, account, authority_type=identity.AuthorityType.own_mc)
    profile = identity.upsert_driver_profile(db, account, unit_number="42")
    assert profile.authority_type == identity.AuthorityType.own_mc
    assert profile.authority_verify_status == identity.VerifyStatus.unverified
    assert profile.unit_number == "42"


@pytest.mark.parametrize("vin", [VALID_VIN, VALID_VIN_X_CHECK])
def test_validate_vin_accepts_real_vins(vin):
    assert identity.validate_vin(vin) == vin


def test_validate_vin_normalizes_case_and_separators():
    assert identity.validate_vin(f" {VALID_VIN.lower()} ") == VALID_VIN


def test_validate_vin_allows_unset():
    assert identity.validate_vin(None) is None
    assert identity.validate_vin("   ") is None


def test_validate_vin_rejects_wrong_length():
    with pytest.raises(identity.InvalidVin, match="17"):
        identity.validate_vin("1FUJGLDR9CSBF41")


def test_validate_vin_rejects_i_o_q():
    # I/O/Q are excluded from the VIN alphabet so they can't be read as 1/0
    bad = "1FUJGLDR9CSBF418O"
    with pytest.raises(identity.InvalidVin, match="I, O and Q"):
        identity.validate_vin(bad)


def test_validate_vin_rejects_bad_check_digit():
    # flip the check digit (position 9) — this is what catches a transposed typo
    bad = VALID_VIN[:8] + "8" + VALID_VIN[9:]
    with pytest.raises(identity.InvalidVin, match="check digit"):
        identity.validate_vin(bad)


def test_no_verification_is_implied_by_a_valid_vin(db):
    # a well-formed VIN must NOT move any verification state (§11.7): the only
    # verified thing on this profile is FMCSA authority, which E2 never touches
    account = _account(db, "novc@example.com")
    profile = identity.upsert_driver_profile(db, account, vin=identity.validate_vin(VALID_VIN))
    assert profile.authority_verify_status == identity.VerifyStatus.unverified
    assert profile.authority_verified_at is None
    assert profile.legal_name is None

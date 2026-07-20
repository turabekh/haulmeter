from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f07_ledger import public as ledger
from app.foundation.f09_ai_gateway import public as ai
from app.foundation.f14_admin import public as admin
from app.modules.m02_facility_intel import public as m2

DALLAS = (32.7767, -96.7970)
FAR = (32.9000, -96.8000)
T0 = datetime(2026, 7, 20, 6, 0, tzinfo=UTC)


def _account(db, email="driver@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _receiver(db, name="Dallas Receiver"):
    return facility.create_facility(db, facility.FacilityType.shipper_receiver, name, *DALLAS)


def _dwell(db, account, fac, enter, exit_at):
    # arm + ENTER at the facility, then EXIT elsewhere -> one dwell sample
    location.arm_geofence(db, account.id, fac.id)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=enter)
    location.evaluate_ping(db, account.id, *FAR, occurred_at=exit_at)
    location.disarm_geofence(db, account.id, fac.id, occurred_at=exit_at)


def test_register_module(db):
    from app.foundation.f13_flags import public as flags

    m2.register_module(db)
    assert flags.is_enabled(db, "m02_facility_intel") is False
    assert admin.list_admin_views(db, module="m02")[0].title == "Facility Scorecard"


def test_profile_factual_claim_rejects_non_factual(db):
    fac = _receiver(db)
    m2.update_factual_attributes(db, fac.id, {"overnight_parking": True, "restrooms": True})
    prof = m2.get_or_create_profile(db, fac.id)
    assert prof.overnight_parking is True
    with pytest.raises(m2.NotFactualField):
        m2.update_factual_attributes(db, fac.id, {"ratings": {"safety": 5}})


def test_review_moderation_awards_points_on_approval(db):
    fac = _receiver(db)
    author = _account(db, "author@example.com")
    review = m2.submit_review(
        db, fac.id, author.id, {"safety": 5, "check_in_speed": 4}, text="Quick and safe"
    )
    assert review.status == m2.ReviewStatus.pending
    assert m2.list_reviews(db, fac.id) == []  # pending not visible

    m2.moderate_review(db, review, approve=True, provider=ai.FakeModelProvider())
    assert review.status == m2.ReviewStatus.approved
    assert len(m2.list_reviews(db, fac.id)) == 1

    points = ledger.get_or_create_account(
        db,
        ledger.LedgerAccountKind.points_balance,
        f"points:{author.id}",
        currency=ledger.Currency.points,
        owner_ref=author.id,
    )
    assert ledger.balance(db, points) == m2.REVIEW_POINTS


def test_invalid_ratings_rejected(db):
    fac = _receiver(db)
    author = _account(db)
    with pytest.raises(m2.InvalidRatings):
        m2.submit_review(db, fac.id, author.id, {"unknown_aspect": 5})
    with pytest.raises(m2.InvalidRatings):
        m2.submit_review(db, fac.id, author.id, {"safety": 9})


def test_aggregate_ratings_over_approved(db):
    fac = _receiver(db)
    for i, email in enumerate(["a@x.com", "b@x.com"]):
        acct = _account(db, email)
        r = m2.submit_review(db, fac.id, acct.id, {"safety": 4 + i})
        m2.moderate_review(db, r, approve=True)
    agg = m2.aggregate_ratings(db, fac.id)
    assert agg["per_aspect"]["safety"] == 4.5
    assert agg["review_count"] == 2


def test_dwell_stats_with_sample_sizes(db):
    fac = _receiver(db)
    a = _account(db, "a@x.com")
    b = _account(db, "b@x.com")
    # a: 1h dwell arriving 06:00; b: 3h dwell arriving 06:00
    _dwell(db, a, fac, T0, T0 + timedelta(hours=1))
    _dwell(db, b, fac, T0, T0 + timedelta(hours=3))
    stats = m2.dwell_stats(db, fac.id)
    assert stats.overall["sample_size"] == 2
    assert stats.overall["median_seconds"] == 2 * 3600  # median of 1h and 3h
    assert stats.by_hour[6]["sample_size"] == 2


def test_detention_risk_is_m3_seam(db):
    fac = _receiver(db)
    assert m2.detention_risk(db, fac.id)["basis"] == "m3_pending"


def test_semantic_review_search(db):
    fac = _receiver(db)
    author = _account(db)
    r = m2.submit_review(
        db,
        fac.id,
        author.id,
        {"overnight_parking": 5},
        text="great overnight parking, quiet lot, easy backing",
    )
    m2.moderate_review(db, r, approve=True, provider=ai.FakeModelProvider())
    hits = m2.search_reviews(
        db, ai.FakeModelProvider(), "great overnight parking, quiet lot, easy backing"
    )
    assert hits[0]["facility_id"] == str(fac.id)

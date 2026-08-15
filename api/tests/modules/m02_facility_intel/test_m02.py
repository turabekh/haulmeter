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
    # ships on (audit F-02, §23 entry 133) — and nobody has decided otherwise
    assert flags.is_enabled(db, "m02_facility_intel") is True
    assert db.get(flags.FeatureFlag, "m02_facility_intel").enabled is None
    assert admin.list_admin_views(db, module="m02")[0].title == "Facility Scorecard"


def test_profile_factual_claim_rejects_non_factual(db):
    fac = _receiver(db)
    m2.update_factual_attributes(db, fac.id, {"overnight_parking": True, "restrooms": True})
    prof = m2.get_or_create_profile(db, fac.id)
    assert prof.overnight_parking is True
    with pytest.raises(m2.NotFactualField):
        m2.update_factual_attributes(db, fac.id, {"ratings": {"safety": 5}})


def _points_balance(db, account):
    points = ledger.get_or_create_account(
        db,
        ledger.LedgerAccountKind.points_balance,
        f"points:{account.id}",
        currency=ledger.Currency.points,
        owner_ref=account.id,
    )
    return ledger.balance(db, points)


def test_review_is_published_on_submission_and_pays_its_points(db):
    """AI-CONTEXT: §23 entry 153 — a review is live when it is written.

    This test asserted the OPPOSITE until the owner's decision, and it was right about
    the code and wrong about the product: measured on the dev box, 8 reviews sat pending
    and the only 2 approvals were the seed, so no review a driver wrote had ever been
    seen by anyone. Moderation is take-down now, and the default while nobody is looking
    falls towards the driver's words existing.
    """
    fac = _receiver(db)
    author = _account(db, "author@example.com")
    review = m2.submit_review(
        db, fac.id, author.id, {"safety": 5, "check_in_speed": 4}, text="Quick and safe"
    )
    assert review.status == m2.ReviewStatus.approved
    assert review.decided_at is not None
    # visible to everyone immediately — the half a driver could not previously see
    assert len(m2.list_reviews(db, fac.id)) == 1
    # and it counts towards the figure on the card, which is the half OTHER drivers read
    assert m2.aggregate_ratings(db, fac.id)["review_count"] == 1
    assert _points_balance(db, author) == m2.REVIEW_POINTS

    # the moderation item still exists, because take-down has to have something to act on
    assert review.moderation_ref is not None


def test_confirming_an_already_published_review_does_not_pay_twice(db):
    # the common path now: a moderator looks at a live review and leaves it live. Paying
    # on approval as well as on submission would mint a second helping every time.
    fac = _receiver(db)
    author = _account(db, "author@example.com")
    review = m2.submit_review(db, fac.id, author.id, {"safety": 5}, text="Quick and safe")
    assert _points_balance(db, author) == m2.REVIEW_POINTS

    m2.moderate_review(db, review, approve=True, provider=ai.FakeModelProvider())
    assert _points_balance(db, author) == m2.REVIEW_POINTS


def test_moderation_can_still_take_a_review_down(db):
    # the control that makes publish-first honest: a rejection removes the review from
    # every read and from the aggregate other drivers are shown
    fac = _receiver(db)
    author = _account(db, "author@example.com")
    review = m2.submit_review(db, fac.id, author.id, {"safety": 1}, text="abusive text")
    assert len(m2.list_reviews(db, fac.id)) == 1

    m2.moderate_review(db, review, approve=False)
    assert review.status == m2.ReviewStatus.rejected
    assert m2.list_reviews(db, fac.id) == []
    assert m2.aggregate_ratings(db, fac.id)["review_count"] == 0


def test_approval_survives_an_embedding_failure(db):
    # embedding is best-effort — a Voyage failure (e.g. a free-tier 429) must not
    # block review approval or its points award (Decision 197).
    class FailingEmbedProvider(ai.FakeModelProvider):
        def embed(self, text):
            raise RuntimeError("voyage 429")

    fac = _receiver(db)
    author = _account(db, "resilient@example.com")
    review = m2.submit_review(db, fac.id, author.id, {"safety": 5}, text="Great dock")
    m2.moderate_review(db, review, approve=True, provider=FailingEmbedProvider())
    assert review.status == m2.ReviewStatus.approved  # approval still went through
    assert len(m2.list_reviews(db, fac.id)) == 1


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


def test_m2_does_not_pretend_to_compute_detention_risk(db):
    """§23 entry 87. M2-FR3's indicator is "derived from M3 claim events", and
    import-linter orders M2 BEFORE M3 — so this module can never read a claim. It
    carried a stub returning `basis: "m3_pending"` for sessions after M3 existed, and
    the old version of this test asserted that stub as correct.

    The indicator lives in `m03.facility_detention_stats` and is composed at the
    router. This holds the boundary: a stub reappearing here would be unimplementable
    all over again."""
    assert not hasattr(m2, "detention_risk")


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

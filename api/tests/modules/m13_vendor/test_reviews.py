"""AI-CONTEXT: M13-FR5 — vendor reviews.

The discipline under test is distinct-REVIEWER counting (§11.7): "12 drivers" must
always mean twelve people, never twelve opinions from six people. Plus the 7-day
cadence, and the two deliberate departures from the M2 pattern — publish
immediately, and award no points (Phase A keeps M13 away from the ledger).
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f13_flags import public as flags
from app.modules.m13_vendor import public as m13

T0 = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


def _account(db, email):
    return identity.register_account(db, email, "pw-123456")


def _vendor(db, email="cook@example.com", name="Osh Express", **kwargs):
    account = _account(db, email)
    defaults = {"languages": ["uz"], "halal_answered": True, "metro": "dallas-tx"}
    return m13.register_vendor(
        db, account.id, name, m13.VendorType.food_mobile, **{**defaults, **kwargs}
    )


def test_a_review_publishes_immediately(db):
    # unlike an M2 facility review, a note about a meal is not held behind a
    # moderator — the section would read as dead if every review waited
    vendor = _vendor(db)
    driver = _account(db, "d1@x.com")
    review = m13.submit_review(db, vendor, driver.id, 5, "Best osh on I-35", now=T0)

    assert review.status == m13.ReviewStatus.visible
    assert m13.list_reviews(db, vendor.id)[0].id == review.id


def test_a_second_review_inside_seven_days_is_refused_with_a_date(db):
    vendor = _vendor(db)
    driver = _account(db, "d2@x.com")
    m13.submit_review(db, vendor, driver.id, 5, now=T0)

    with pytest.raises(m13.ReviewTooSoon) as exc:
        m13.submit_review(db, vendor, driver.id, 1, now=T0 + timedelta(days=3))
    # §12.4: the refusal carries WHEN they may return, not just "no"
    assert exc.value.next_allowed_at == T0 + timedelta(days=7)


def test_after_the_window_a_driver_updates_rather_than_duplicates(db):
    # THE distinct-reviewer rule: one person's changed mind is one voice, not two
    vendor = _vendor(db)
    driver = _account(db, "d3@x.com")
    m13.submit_review(db, vendor, driver.id, 5, "Great", now=T0)
    m13.submit_review(db, vendor, driver.id, 2, "Off night", now=T0 + timedelta(days=8))

    summary = m13.review_summary(db, vendor.id)
    assert summary.reviewers == 1
    assert summary.average == 2.0  # the newer verdict replaces, never averages in
    assert len(m13.list_reviews(db, vendor.id)) == 1


def test_distinct_drivers_are_counted_once_each(db):
    vendor = _vendor(db)
    for i, rating in enumerate([5, 4, 3]):
        m13.submit_review(db, vendor, _account(db, f"m{i}@x.com").id, rating, now=T0)

    summary = m13.review_summary(db, vendor.id)
    assert summary.reviewers == 3
    assert summary.average == 4.0


def test_a_vendor_with_no_reviews_reports_nothing_rather_than_zero(db):
    # a 0.0 average would read as "rated badly"; no reviews means no number
    vendor = _vendor(db)
    summary = m13.review_summary(db, vendor.id)
    assert summary.average is None
    assert summary.reviewers == 0
    assert summary.has_reviews is False


def test_the_cadence_window_is_f13_tunable(db):
    vendor = _vendor(db)
    driver = _account(db, "tune@x.com")
    flags.set_config(db, m13.CONFIG_REVIEW_COOLDOWN_DAYS, 1)
    m13.submit_review(db, vendor, driver.id, 4, now=T0)

    m13.submit_review(db, vendor, driver.id, 5, now=T0 + timedelta(days=2))
    assert m13.review_summary(db, vendor.id).average == 5.0


@pytest.mark.parametrize("rating", [0, 6, -1, 2.5, "five"])
def test_ratings_outside_one_to_five_are_refused(db, rating):
    vendor = _vendor(db)
    driver = _account(db, "bad@x.com")
    with pytest.raises(m13.InvalidRating):
        m13.submit_review(db, vendor, driver.id, rating, now=T0)


def test_overlong_text_is_refused(db):
    vendor = _vendor(db)
    driver = _account(db, "long@x.com")
    with pytest.raises(m13.InvalidRating):
        m13.submit_review(db, vendor, driver.id, 5, "x" * 501, now=T0)


def test_can_review_reports_the_cadence_state(db):
    vendor = _vendor(db)
    driver = _account(db, "state@x.com")
    assert m13.can_review(db, vendor.id, driver.id, now=T0) is True

    m13.submit_review(db, vendor, driver.id, 5, now=T0)
    assert m13.can_review(db, vendor.id, driver.id, now=T0 + timedelta(days=2)) is False
    assert m13.can_review(db, vendor.id, driver.id, now=T0 + timedelta(days=8)) is True


def test_reviews_award_no_points(db):
    # deliberate departure from M2, which pays REVIEW_POINTS on approval. Points are
    # the M10 closed-loop economy funded against the M6 take; routing a reward
    # through the ledger from M13 is exactly the money-adjacent path Phase A forbids.
    from app.foundation.f07_ledger import public as ledger

    vendor = _vendor(db)
    driver = _account(db, "nopoints@x.com")
    m13.submit_review(db, vendor, driver.id, 5, "Great", now=T0)

    balance = ledger.get_or_create_account(
        db,
        ledger.LedgerAccountKind.points_balance,
        f"points:{driver.id}",
        currency=ledger.Currency.points,
        owner_ref=driver.id,
    )
    assert ledger.balance(db, balance) == 0


def test_a_hidden_review_leaves_the_average_and_the_count(db):
    # a reported review must not keep steering the score while it is under review
    vendor = _vendor(db)
    good = _account(db, "good@x.com")
    bad = _account(db, "bad2@x.com")
    m13.submit_review(db, vendor, good.id, 5, now=T0)
    hostile = m13.submit_review(db, vendor, bad.id, 1, "slander", now=T0)

    m13.report_content(
        db,
        m13.CONTENT_REVIEW,
        hostile.id,
        vendor.id,
        good.id,
        m13.ModerationReason.offensive,
        now=T0,
    )

    summary = m13.review_summary(db, vendor.id)
    assert summary.reviewers == 1
    assert summary.average == 5.0

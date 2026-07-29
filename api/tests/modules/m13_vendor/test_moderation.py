"""AI-CONTEXT: M13 Q-8 — moderation SLA. "Trust is the product."

The two asymmetries these tests exist to defend:

· A reported REVIEW hides on the first report. A reported VENDOR does not — it
  needs reports from N DISTINCT drivers, because a single anonymous report must
  never become a competitor's kill switch on someone's livelihood.
· Repeat offending is counted in reports a moderator UPHELD, never in reports
  received, so a vendor cannot be suspended by volume of complaint alone.

Plus the 72h SLA being visible (an SLA nobody can see is not an SLA), and the
Q11 false-attestation reason existing at all — the ranking boost that
`property_approved` grants is only defensible because lying about it is actionable.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f13_flags import public as flags
from app.foundation.f14_admin import public as admin
from app.modules.m13_vendor import public as m13

DALLAS = (32.7767, -96.7970)
T0 = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)
MENU = [m13.OfferingIn("Osh", 1200)]


def _account(db, email):
    return identity.register_account(db, email, "pw-123456")


def _vendor(db, email="cook@example.com", name="Osh Express", **kwargs):
    account = _account(db, email)
    defaults = {"languages": ["uz"], "halal_answered": True, "metro": "dallas-tx"}
    return m13.register_vendor(
        db, account.id, name, m13.VendorType.food_mobile, **{**defaults, **kwargs}
    )


def _facility(db, name="Loves 212"):
    return facility.create_facility(db, facility.FacilityType.truck_stop, name, *DALLAS)


def _report(db, kind, ref, vendor, reporter_email, reason=None, now=T0):
    return m13.report_content(
        db,
        kind,
        ref,
        vendor.id,
        _account(db, reporter_email).id,
        reason or m13.ModerationReason.spam,
        now=now,
    )


# --- reviews: hide on first report ---
def test_a_reported_review_hides_immediately(db):
    vendor = _vendor(db)
    author = _account(db, "author@x.com")
    review = m13.submit_review(db, vendor, author.id, 1, "nonsense", now=T0)

    outcome = _report(db, m13.CONTENT_REVIEW, review.id, vendor, "reporter@x.com")

    assert outcome.hidden is True
    assert review.status == m13.ReviewStatus.hidden_pending
    assert m13.list_reviews(db, vendor.id) == []


def test_a_reported_review_reaches_the_f14_queue(db):
    vendor = _vendor(db)
    review = m13.submit_review(db, vendor, _account(db, "a2@x.com").id, 1, now=T0)
    _report(db, m13.CONTENT_REVIEW, review.id, vendor, "r2@x.com")

    pending = admin.list_pending_moderation(db, content_kind=m13.CONTENT_REVIEW)
    assert [i.content_ref for i in pending] == [review.id]


def test_dismissing_a_report_restores_the_review(db):
    vendor = _vendor(db)
    review = m13.submit_review(db, vendor, _account(db, "a3@x.com").id, 4, "fine", now=T0)
    _report(db, m13.CONTENT_REVIEW, review.id, vendor, "r3@x.com")

    result = m13.resolve_report(db, m13.CONTENT_REVIEW, review.id, uphold=False, now=T0)

    assert review.status == m13.ReviewStatus.visible
    assert result["reports_closed"] == 1
    assert admin.list_pending_moderation(db, content_kind=m13.CONTENT_REVIEW) == []


def test_upholding_a_report_removes_the_review_for_good(db):
    vendor = _vendor(db)
    review = m13.submit_review(db, vendor, _account(db, "a4@x.com").id, 1, "abuse", now=T0)
    _report(db, m13.CONTENT_REVIEW, review.id, vendor, "r4@x.com")

    m13.resolve_report(db, m13.CONTENT_REVIEW, review.id, uphold=True, now=T0)
    assert review.status == m13.ReviewStatus.removed
    assert m13.list_reviews(db, vendor.id) == []


# --- vendor listings: N distinct drivers, never one ---
def test_one_report_does_not_take_down_a_vendor(db):
    # the whole point: a competitor with one account cannot silence a business
    vendor = _vendor(db)
    outcome = _report(db, m13.CONTENT_VENDOR, vendor.id, vendor, "rival@x.com")

    assert outcome.hidden is False
    assert vendor.publish_suspended is False
    assert outcome.distinct_reports == 1


def test_three_distinct_drivers_do_take_a_vendor_down(db):
    vendor = _vendor(db)
    for i in range(m13.DEFAULT_VENDOR_HIDE_REPORTS):
        outcome = _report(db, m13.CONTENT_VENDOR, vendor.id, vendor, f"crowd{i}@x.com")

    assert outcome.distinct_reports == 3
    assert outcome.hidden is True
    assert vendor.publish_suspended is True


def test_one_driver_cannot_manufacture_the_threshold(db):
    # the unique constraint is what makes "distinct" mean anything
    vendor = _vendor(db)
    reporter = _account(db, "spammer@x.com")
    m13.report_content(
        db, m13.CONTENT_VENDOR, vendor.id, vendor.id, reporter.id, m13.ModerationReason.spam, now=T0
    )
    with pytest.raises(m13.AlreadyReported):
        m13.report_content(
            db,
            m13.CONTENT_VENDOR,
            vendor.id,
            vendor.id,
            reporter.id,
            m13.ModerationReason.spam,
            now=T0,
        )
    assert m13.distinct_reporters(db, m13.CONTENT_VENDOR, vendor.id) == 1


def test_the_hide_threshold_is_f13_tunable(db):
    vendor = _vendor(db)
    flags.set_config(db, m13.CONFIG_VENDOR_HIDE_REPORTS, 1)
    outcome = _report(db, m13.CONTENT_VENDOR, vendor.id, vendor, "single@x.com")
    assert outcome.hidden is True


def test_a_suspended_vendor_cannot_publish(db):
    # the suspension has to actually bite, or it is theatre
    vendor, fac = _vendor(db), _facility(db)
    for i in range(m13.DEFAULT_VENDOR_HIDE_REPORTS):
        _report(db, m13.CONTENT_VENDOR, vendor.id, vendor, f"stop{i}@x.com")

    with pytest.raises(m13.PublishSuspended):
        m13.publish_appearance(db, vendor, fac.id, T0, T0 + timedelta(hours=4), MENU, now=T0)


def test_dismissing_a_vendor_report_lifts_the_suspension(db):
    vendor = _vendor(db)
    for i in range(m13.DEFAULT_VENDOR_HIDE_REPORTS):
        _report(db, m13.CONTENT_VENDOR, vendor.id, vendor, f"wrong{i}@x.com")

    m13.resolve_report(db, m13.CONTENT_VENDOR, vendor.id, uphold=False, now=T0)
    assert vendor.publish_suspended is False


def test_one_queue_item_per_reported_item_not_per_report(db):
    # a moderator should see "this listing, reported by 3 people", not three tasks
    vendor = _vendor(db)
    for i in range(3):
        _report(db, m13.CONTENT_VENDOR, vendor.id, vendor, f"dup{i}@x.com")

    pending = admin.list_pending_moderation(db, content_kind=m13.CONTENT_VENDOR)
    assert len(pending) == 1


# --- Q11: false property attestation ---
def test_a_false_property_attestation_is_a_recordable_reason(db):
    # PRD §17 Q11 let a self-attestation earn a ranking boost. That is only
    # defensible because lying about it is actionable — this is that consequence.
    vendor = _vendor(db)
    outcome = _report(
        db,
        m13.CONTENT_VENDOR,
        vendor.id,
        vendor,
        "property@x.com",
        reason=m13.ModerationReason.false_property_attestation,
    )
    assert outcome.report.reason == m13.ModerationReason.false_property_attestation


# --- repeat offenders ---
def test_three_upheld_reports_suspend_a_repeat_offender(db):
    vendor = _vendor(db)
    for i in range(m13.DEFAULT_REPEAT_OFFENDER_STRIKES):
        review = m13.submit_review(db, vendor, _account(db, f"auth{i}@x.com").id, 1, now=T0)
        _report(db, m13.CONTENT_REVIEW, review.id, vendor, f"rep{i}@x.com")
        result = m13.resolve_report(db, m13.CONTENT_REVIEW, review.id, uphold=True, now=T0)

    assert m13.upheld_report_count(db, vendor.id) == 3
    assert result["vendor_suspended"] is True
    assert vendor.status == m13.VendorStatus.suspended


def test_dismissed_reports_never_count_toward_suspension(db):
    # volume of complaint is not evidence; only a moderator agreeing is
    vendor = _vendor(db)
    for i in range(5):
        review = m13.submit_review(db, vendor, _account(db, f"ok{i}@x.com").id, 5, now=T0)
        _report(db, m13.CONTENT_REVIEW, review.id, vendor, f"noise{i}@x.com")
        m13.resolve_report(db, m13.CONTENT_REVIEW, review.id, uphold=False, now=T0)

    assert m13.upheld_report_count(db, vendor.id) == 0
    assert vendor.status == m13.VendorStatus.active


# --- the 72h SLA has to be visible ---
def test_the_queue_reports_age_and_flags_overdue(db):
    vendor = _vendor(db)
    review = m13.submit_review(db, vendor, _account(db, "old@x.com").id, 1, now=T0)
    _report(db, m13.CONTENT_REVIEW, review.id, vendor, "sla@x.com")

    fresh = m13.queue_with_sla(db, now=T0 + timedelta(hours=2))
    assert fresh[0].overdue is False

    late = m13.queue_with_sla(db, now=T0 + timedelta(hours=73))
    assert late[0].overdue is True
    assert late[0].age_hours >= 72


def test_the_sla_is_a_platform_promise_not_an_m13_one(db):
    # every module's queue makes the same promise to the same people; a per-module
    # SLA would quietly become several different promises
    assert admin.MODERATION_SLA_HOURS == 72


def test_overdue_moderation_finds_late_items(db):
    """AI-CONTEXT: anchored to `now`, not to T0, and that is the whole point.

    This test seeded a report at the fixed T0 (26 July, 12:00 UTC) and then asked
    whether it was overdue relative to `datetime.now()`. With MODERATION_SLA_HOURS = 72
    that was true until **29 July 13:00 UTC** and false after — an expiry nobody wrote
    down, in a test that reads as timeless. It is the second instance of exactly the
    defect §23 recorded for the admin console, so the fix is the general one: seed
    relative to the same clock the assertion reads.
    """
    vendor = _vendor(db)
    now = datetime.now(UTC)
    review = m13.submit_review(db, vendor, _account(db, "late@x.com").id, 1, now=now)
    _report(db, m13.CONTENT_REVIEW, review.id, vendor, "late2@x.com", now=now)

    assert admin.overdue_moderation(db, now - timedelta(hours=1)) == []
    late = admin.overdue_moderation(db, now + timedelta(hours=100))
    assert [i.content_ref for i in late] == [review.id]


def test_an_unknown_content_kind_is_refused(db):
    vendor = _vendor(db)
    with pytest.raises(m13.NotReportable):
        m13.report_content(
            db,
            "something_else",
            vendor.id,
            vendor.id,
            _account(db, "weird@x.com").id,
            m13.ModerationReason.other,
            now=T0,
        )

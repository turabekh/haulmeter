"""AI-CONTEXT: moderation integrity guards (Admin Console 2.0 decision 4).

Q-8 gave drivers a report button. These guards exist because a report button with
no counter-pressure is a free weapon: a vendor can report the reviews they dislike,
and a determined account can file until something sticks.

Three defences, each with a deliberate shape:

· **A vendor cannot report their own listing into a takedown** — but the attempt is
  RECORDED. Discarding it would hide the abuse from the only person able to act on it.
· **Reports are rate-limited per account.** Reporting should stay easy; filing dozens
  in an evening is a campaign, and a moderator's attention is finite.
· **Frivolous is a third verdict**, and its strike lands on the REPORTER. Without it
  a moderator can only ever penalise the reported party.

None of this is a ban (out of scope): an account past the strike limit keeps
reporting and a moderator still sees every one — only the automatic weight is gone.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f13_flags import public as flags
from app.foundation.f14_admin import public as admin
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


def _review(db, vendor, email="author@x.com", rating=1, now=T0):
    return m13.submit_review(db, vendor, _account(db, email).id, rating, "text", now=now)


def _report(db, kind, ref, vendor, account_id, reason=None, now=T0):
    return m13.report_content(
        db, kind, ref, vendor.id, account_id, reason or m13.ModerationReason.spam, now=now
    )


# --- 4a: a vendor cannot silence criticism of itself ---
def test_a_vendor_reporting_a_review_of_itself_does_not_hide_it(db):
    vendor = _vendor(db)
    review = _review(db, vendor)

    outcome = _report(db, m13.CONTENT_REVIEW, review.id, vendor, vendor.owner_account_id)

    assert outcome.hidden is False
    assert outcome.discounted is True
    assert review.status == m13.ReviewStatus.visible  # the review stays up


def test_the_self_report_is_still_recorded_and_visible_to_a_moderator(db):
    # the abuse must be legible: discarding the report would hide it from the only
    # person who can act on it
    vendor = _vendor(db)
    review = _review(db, vendor)
    outcome = _report(db, m13.CONTENT_REVIEW, review.id, vendor, vendor.owner_account_id)

    assert outcome.report.self_reported is True
    assert m13.all_reporters(db, m13.CONTENT_REVIEW, review.id) == 1
    assert m13.distinct_reporters(db, m13.CONTENT_REVIEW, review.id) == 0  # carries no weight
    assert any(i.content_ref == review.id for i in admin.list_pending_moderation(db))


def test_a_vendor_member_is_also_the_vendor_for_this_purpose(db):
    # a helper account is not an independent voice about their own vendor
    vendor = _vendor(db)
    helper = _account(db, "helper@x.com")
    m13.add_member(db, vendor, helper.id)
    review = _review(db, vendor)

    outcome = _report(db, m13.CONTENT_REVIEW, review.id, vendor, helper.id)
    assert outcome.discounted is True
    assert review.status == m13.ReviewStatus.visible


def test_a_vendor_cannot_report_its_own_listing_into_a_takedown(db):
    vendor = _vendor(db)
    outcome = _report(db, m13.CONTENT_VENDOR, vendor.id, vendor, vendor.owner_account_id)
    assert outcome.distinct_reports == 0
    assert vendor.publish_suspended is False


def test_an_unrelated_driver_still_hides_a_review_normally(db):
    # the guard must not blunt the ordinary path
    vendor = _vendor(db)
    review = _review(db, vendor)
    outcome = _report(db, m13.CONTENT_REVIEW, review.id, vendor, _account(db, "driver@x.com").id)

    assert outcome.hidden is True
    assert outcome.discounted is False
    assert review.status == m13.ReviewStatus.hidden_pending


# --- 4b: rate limit ---
def test_an_account_is_rate_limited_after_the_daily_cap(db):
    vendor = _vendor(db)
    reporter = _account(db, "busy@x.com")
    for i in range(m13.DEFAULT_REPORTS_PER_DAY):
        _report(db, m13.CONTENT_REVIEW, _review(db, vendor, f"a{i}@x.com").id, vendor, reporter.id)

    with pytest.raises(m13.ReportRateLimited) as exc:
        _report(db, m13.CONTENT_REVIEW, _review(db, vendor, "last@x.com").id, vendor, reporter.id)
    assert exc.value.limit == m13.DEFAULT_REPORTS_PER_DAY


def test_the_limit_is_a_rolling_window_not_a_permanent_ceiling(db):
    vendor = _vendor(db)
    reporter = _account(db, "patient@x.com")
    for i in range(m13.DEFAULT_REPORTS_PER_DAY):
        _report(db, m13.CONTENT_REVIEW, _review(db, vendor, f"b{i}@x.com").id, vendor, reporter.id)

    tomorrow = T0 + timedelta(hours=25)
    outcome = _report(
        db,
        m13.CONTENT_REVIEW,
        _review(db, vendor, "later@x.com", now=tomorrow).id,
        vendor,
        reporter.id,
        now=tomorrow,
    )
    assert outcome.report is not None


def test_the_daily_cap_is_f13_tunable(db):
    vendor = _vendor(db)
    reporter = _account(db, "tuned@x.com")
    flags.set_config(db, m13.CONFIG_REPORTS_PER_DAY, 1)
    _report(db, m13.CONTENT_REVIEW, _review(db, vendor, "one@x.com").id, vendor, reporter.id)

    with pytest.raises(m13.ReportRateLimited):
        _report(db, m13.CONTENT_REVIEW, _review(db, vendor, "two@x.com").id, vendor, reporter.id)


def test_the_cap_is_per_account_not_global(db):
    # one noisy account must not exhaust everyone else's ability to report
    vendor = _vendor(db)
    noisy = _account(db, "noisy@x.com")
    for i in range(m13.DEFAULT_REPORTS_PER_DAY):
        _report(db, m13.CONTENT_REVIEW, _review(db, vendor, f"c{i}@x.com").id, vendor, noisy.id)

    quiet = _account(db, "quiet@x.com")
    outcome = _report(
        db, m13.CONTENT_REVIEW, _review(db, vendor, "fresh@x.com").id, vendor, quiet.id
    )
    assert outcome.hidden is True


# --- 4c: frivolous strikes back at the reporter ---
def test_a_frivolous_verdict_restores_the_content_and_marks_the_report(db):
    vendor = _vendor(db)
    review = _review(db, vendor, rating=5)
    reporter = _account(db, "vexatious@x.com")
    _report(db, m13.CONTENT_REVIEW, review.id, vendor, reporter.id)

    result = m13.resolve_report(
        db, m13.CONTENT_REVIEW, review.id, uphold=False, frivolous=True, now=T0
    )

    assert review.status == m13.ReviewStatus.visible  # it comes back
    assert result["frivolous"] is True
    assert m13.frivolous_strikes(db, reporter.id) == 1


def test_a_report_cannot_be_both_upheld_and_frivolous(db):
    vendor = _vendor(db)
    review = _review(db, vendor)
    _report(db, m13.CONTENT_REVIEW, review.id, vendor, _account(db, "d@x.com").id)

    with pytest.raises(ValueError):
        m13.resolve_report(db, m13.CONTENT_REVIEW, review.id, uphold=True, frivolous=True, now=T0)


def test_strikes_cost_an_account_its_automatic_weight_but_not_its_voice(db):
    vendor = _vendor(db)
    reporter = _account(db, "burned@x.com")
    for i in range(m13.DEFAULT_FRIVOLOUS_STRIKES):
        review = _review(db, vendor, f"e{i}@x.com", rating=5)
        _report(db, m13.CONTENT_REVIEW, review.id, vendor, reporter.id)
        m13.resolve_report(db, m13.CONTENT_REVIEW, review.id, uphold=False, frivolous=True, now=T0)

    assert m13.reporter_credible(db, reporter.id) is False

    # they can still file, and a moderator still sees it — only the auto-hide is gone
    fresh = _review(db, vendor, "target@x.com", rating=5)
    outcome = _report(db, m13.CONTENT_REVIEW, fresh.id, vendor, reporter.id)
    assert outcome.discounted is True
    assert outcome.hidden is False
    assert fresh.status == m13.ReviewStatus.visible
    assert any(i.content_ref == fresh.id for i in admin.list_pending_moderation(db))


def test_a_discredited_account_is_not_banned(db):
    # decision 5: account-level banning is out of scope. The account still exists,
    # still reviews, still confirms — only its report weight was withdrawn.
    vendor = _vendor(db)
    reporter = _account(db, "notbanned@x.com")
    for i in range(m13.DEFAULT_FRIVOLOUS_STRIKES):
        review = _review(db, vendor, f"f{i}@x.com", rating=5)
        _report(db, m13.CONTENT_REVIEW, review.id, vendor, reporter.id)
        m13.resolve_report(db, m13.CONTENT_REVIEW, review.id, uphold=False, frivolous=True, now=T0)

    other = _vendor(db, "other@x.com", "Other Cook", metro="austin-tx")
    review = m13.submit_review(db, other, reporter.id, 4, "fine", now=T0)
    assert review.status == m13.ReviewStatus.visible


def test_the_strike_limit_is_f13_tunable(db):
    vendor = _vendor(db)
    reporter = _account(db, "onestrike@x.com")
    flags.set_config(db, m13.CONFIG_FRIVOLOUS_STRIKES, 1)
    review = _review(db, vendor, rating=5)
    _report(db, m13.CONTENT_REVIEW, review.id, vendor, reporter.id)
    m13.resolve_report(db, m13.CONTENT_REVIEW, review.id, uphold=False, frivolous=True, now=T0)

    assert m13.reporter_credible(db, reporter.id) is False


def test_the_resolution_reports_who_lost_credibility(db):
    # the console tells a moderator the consequence of the verdict they just gave
    vendor = _vendor(db)
    reporter = _account(db, "consequence@x.com")
    review = _review(db, vendor, rating=5)
    _report(db, m13.CONTENT_REVIEW, review.id, vendor, reporter.id)

    result = m13.resolve_report(
        db, m13.CONTENT_REVIEW, review.id, uphold=False, frivolous=True, now=T0
    )
    assert result["discredited"][0]["account_id"] == reporter.id
    assert result["discredited"][0]["strikes"] == 1


def test_an_ordinary_dismissal_costs_the_reporter_nothing(db):
    # reporting in good faith and being wrong is not an offence
    vendor = _vendor(db)
    reporter = _account(db, "goodfaith@x.com")
    review = _review(db, vendor, rating=5)
    _report(db, m13.CONTENT_REVIEW, review.id, vendor, reporter.id)

    m13.resolve_report(db, m13.CONTENT_REVIEW, review.id, uphold=False, now=T0)

    assert m13.frivolous_strikes(db, reporter.id) == 0
    assert m13.reporter_credible(db, reporter.id) is True

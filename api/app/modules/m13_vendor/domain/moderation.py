"""AI-CONTEXT: M13 Q-8 — moderation SLA. "Trust is the product."

Reported content reaches the F14 queue, gets resolved inside 72h, and repeat
offenders are suspended. Two asymmetries in here are deliberate and owner-approved:

**A reported REVIEW hides on the first report; a reported VENDOR does not.**
Hiding one review is low blast radius and trivially restored. Hiding an entire
vendor is taking away someone's livelihood for the evening, and a single anonymous
report would hand a competitor a kill switch. A vendor listing therefore needs
reports from N DISTINCT drivers (default 3, F13-tunable) before it hides — and the
report table's unique constraint is what makes "distinct" mean anything, since one
person cannot manufacture N reports.

**Reports are counted per driver, upheld reports per vendor.** Repeat offending is
measured in reports a moderator AGREED with, never in reports received, so a vendor
cannot be suspended by volume of complaint alone.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.foundation.f13_flags import public as flags
from app.foundation.f14_admin import public as admin

from .enums import ModerationReason, PromotionStatus, ReviewStatus
from .models import ContentReport, Promotion, Vendor, VendorReview

CONTENT_REVIEW = "vendor_review"
CONTENT_VENDOR = "vendor_listing"
CONTENT_PROMOTION = "vendor_promotion"

# how many DISTINCT drivers must report a vendor listing before it hides
CONFIG_VENDOR_HIDE_REPORTS = "m13_vendor_hide_reports"
DEFAULT_VENDOR_HIDE_REPORTS = 3
# upheld reports before a vendor is suspended as a repeat offender
CONFIG_REPEAT_OFFENDER_STRIKES = "m13_repeat_offender_strikes"
DEFAULT_REPEAT_OFFENDER_STRIKES = 3
# how many reports one account may file per rolling 24h. Reporting is a civic act
# and should stay easy; filing dozens in an evening is not reporting, it is a
# campaign, and the queue a moderator has to read is a finite resource.
CONFIG_REPORTS_PER_DAY = "m13_reports_per_day"
DEFAULT_REPORTS_PER_DAY = 5
# upheld-frivolous reports before an account's reports stop carrying hide weight.
# The account keeps reporting and a moderator still sees every one — this is not a
# ban (that stays out of scope), it is the same class of measure as vendor
# publish-suspension: the automatic consequence is withdrawn, the human one is not.
CONFIG_FRIVOLOUS_STRIKES = "m13_frivolous_strikes"
DEFAULT_FRIVOLOUS_STRIKES = 3


class AlreadyReported(Exception):
    """One report per driver per item — the honest basis for a distinct count."""


class NotReportable(Exception):
    pass


class ReportRateLimited(Exception):
    """Decision 4b. Carries the cap so the UI can say what the limit actually is."""

    def __init__(self, limit: int):
        super().__init__(str(limit))
        self.limit = limit


@dataclass
class ReportOutcome:
    report: ContentReport
    hidden: bool
    distinct_reports: int
    moderation_ref: object
    # true when the reporter is the vendor's own owner/member, or has spent their
    # credibility on frivolous reports. The report is still filed; it just carries
    # no automatic weight, and the moderator is told why.
    discounted: bool = False


def _config_int(db: Session, key: str, default: int) -> int:
    return int(flags.get_config(db, key, default))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def distinct_reporters(db: Session, content_kind: str, content_ref) -> int:
    """Reports that CARRY WEIGHT, counted per distinct account. A vendor reporting
    their own listing, and an account that has spent its credibility on frivolous
    reports, are both excluded here — they are still on file, they just cannot move
    the automatic threshold on their own say-so."""
    return int(
        db.scalar(
            select(func.count(func.distinct(ContentReport.account_id))).where(
                ContentReport.content_kind == content_kind,
                ContentReport.content_ref == content_ref,
                ContentReport.self_reported.is_(False),
                ContentReport.frivolous.is_(False),
            )
        )
        or 0
    )


def all_reporters(db: Session, content_kind: str, content_ref) -> int:
    """Every report on file including discounted ones — what a MODERATOR sees, so
    an attempted self-takedown is visible rather than invisible."""
    return int(
        db.scalar(
            select(func.count(func.distinct(ContentReport.account_id))).where(
                ContentReport.content_kind == content_kind,
                ContentReport.content_ref == content_ref,
            )
        )
        or 0
    )


def is_own_vendor(db: Session, vendor_id, account_id) -> bool:
    from .service import is_member

    vendor = db.get(Vendor, vendor_id)
    if vendor is None:
        return False
    return vendor.owner_account_id == account_id or is_member(db, vendor_id, account_id)


def frivolous_strikes(db: Session, account_id) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(ContentReport)
            .where(
                ContentReport.account_id == account_id,
                ContentReport.frivolous.is_(True),
            )
        )
        or 0
    )


def reports_today(db: Session, account_id, now: datetime) -> int:
    since = now - timedelta(hours=24)
    return int(
        db.scalar(
            select(func.count())
            .select_from(ContentReport)
            .where(
                ContentReport.account_id == account_id,
                ContentReport.created_at >= since,
            )
        )
        or 0
    )


def reporter_credible(db: Session, account_id) -> bool:
    """False once an account has accumulated frivolous strikes. Their reports keep
    reaching a moderator; they simply stop carrying automatic weight. This is not a
    ban — the human path is untouched, only the automatic one is withdrawn."""
    strikes = _config_int(db, CONFIG_FRIVOLOUS_STRIKES, DEFAULT_FRIVOLOUS_STRIKES)
    return frivolous_strikes(db, account_id) < strikes


def report_content(
    db: Session,
    content_kind: str,
    content_ref,
    vendor_id,
    account_id,
    reason: ModerationReason,
    note: str | None = None,
    now: datetime | None = None,
) -> ReportOutcome:
    now = now or datetime.now(UTC)
    if content_kind not in (CONTENT_REVIEW, CONTENT_VENDOR, CONTENT_PROMOTION):
        raise NotReportable(content_kind)

    already = db.scalar(
        select(ContentReport).where(
            ContentReport.content_kind == content_kind,
            ContentReport.content_ref == content_ref,
            ContentReport.account_id == account_id,
        )
    )
    if already is not None:
        raise AlreadyReported(str(content_ref))

    limit = _config_int(db, CONFIG_REPORTS_PER_DAY, DEFAULT_REPORTS_PER_DAY)
    if reports_today(db, account_id, now) >= limit:
        raise ReportRateLimited(limit)

    # decision 4a/4c: a vendor reporting themselves, or an account that has spent its
    # credibility, files a report that a moderator will see and that carries no
    # automatic weight. Recorded, not discarded — discarding would hide the abuse
    # from the only person able to act on it.
    self_reported = is_own_vendor(db, vendor_id, account_id)
    discounted = self_reported or not reporter_credible(db, account_id)

    report = ContentReport(
        content_kind=content_kind,
        content_ref=content_ref,
        vendor_id=vendor_id,
        account_id=account_id,
        reason=reason,
        note=note,
        self_reported=self_reported,
        created_at=now,
    )
    db.add(report)
    db.flush()

    count = distinct_reporters(db, content_kind, content_ref)
    hidden = False if discounted else _apply_hide_policy(db, content_kind, content_ref, count)

    # one F14 queue item per reported ITEM, not per report — a moderator should see
    # "this review, reported by 3 people", not three identical tasks
    existing_ref = _existing_moderation_ref(db, content_kind, content_ref)
    if existing_ref is None:
        item = admin.enqueue_moderation(db, content_kind, content_ref, submitted_by=account_id)
        _attach_moderation_ref(db, content_kind, content_ref, item.id)
        existing_ref = item.id

    return ReportOutcome(
        report=report,
        hidden=hidden,
        distinct_reports=count,
        moderation_ref=existing_ref,
        discounted=discounted,
    )


def _apply_hide_policy(db: Session, content_kind: str, content_ref, distinct_count: int) -> bool:
    """A review or a promotion hides on the first report. A vendor listing needs N
    distinct drivers, so one report cannot silence a business."""
    if content_kind == CONTENT_REVIEW:
        review = db.get(VendorReview, content_ref)
        if review is not None and review.status == ReviewStatus.visible:
            review.status = ReviewStatus.hidden_pending
            db.flush()
            return True
        return False

    if content_kind == CONTENT_PROMOTION:
        promo = db.get(Promotion, content_ref)
        if promo is not None and promo.status == PromotionStatus.active:
            promo.status = PromotionStatus.hidden_pending
            db.flush()
            return True
        return False

    threshold = _config_int(db, CONFIG_VENDOR_HIDE_REPORTS, DEFAULT_VENDOR_HIDE_REPORTS)
    if distinct_count >= threshold:
        vendor = db.get(Vendor, content_ref)
        if vendor is not None and not vendor.publish_suspended:
            # publishing stops; the profile is not deleted and an admin can restore it
            vendor.publish_suspended = True
            db.flush()
            return True
    return False


def _existing_moderation_ref(db: Session, content_kind: str, content_ref):
    if content_kind == CONTENT_REVIEW:
        review = db.get(VendorReview, content_ref)
        return review.moderation_ref if review is not None else None
    if content_kind == CONTENT_PROMOTION:
        promo = db.get(Promotion, content_ref)
        return promo.moderation_ref if promo is not None else None
    open_item = db.scalar(
        select(admin.ModerationItem).where(
            admin.ModerationItem.content_kind == content_kind,
            admin.ModerationItem.content_ref == content_ref,
            admin.ModerationItem.status == admin.ModerationStatus.pending,
        )
    )
    return open_item.id if open_item is not None else None


def _attach_moderation_ref(db: Session, content_kind: str, content_ref, item_id) -> None:
    if content_kind == CONTENT_REVIEW:
        review = db.get(VendorReview, content_ref)
        if review is not None:
            review.moderation_ref = item_id
    elif content_kind == CONTENT_PROMOTION:
        promo = db.get(Promotion, content_ref)
        if promo is not None:
            promo.moderation_ref = item_id
    db.flush()


def resolve_report(
    db: Session,
    content_kind: str,
    content_ref,
    uphold: bool,
    moderator_account_id=None,
    reason: str | None = None,
    now: datetime | None = None,
    frivolous: bool = False,
) -> dict:
    """Three outcomes, not two. Uphold = the content stays down. Dismiss = it comes
    back. **Frivolous** = it comes back AND the report itself was the abuse, so the
    strike lands on the REPORTER. Without that third verdict a moderator can only
    ever penalise the reported party, which makes the report button a free weapon.

    Either way the queue item closes, which is what the 72h SLA measures."""
    now = now or datetime.now(UTC)
    if frivolous and uphold:
        raise ValueError("a report cannot be both upheld and frivolous")
    reports = list(
        db.scalars(
            select(ContentReport).where(
                ContentReport.content_kind == content_kind,
                ContentReport.content_ref == content_ref,
                ContentReport.upheld.is_(None),
            )
        )
    )
    for report in reports:
        report.upheld = uphold
        report.frivolous = frivolous

    if content_kind == CONTENT_REVIEW:
        review = db.get(VendorReview, content_ref)
        if review is not None:
            review.status = ReviewStatus.removed if uphold else ReviewStatus.visible
            _close_item(db, review.moderation_ref, uphold, moderator_account_id, reason)
    elif content_kind == CONTENT_PROMOTION:
        promo = db.get(Promotion, content_ref)
        if promo is not None:
            promo.status = PromotionStatus.removed if uphold else PromotionStatus.active
            _close_item(db, promo.moderation_ref, uphold, moderator_account_id, reason)
    else:
        vendor = db.get(Vendor, content_ref)
        if vendor is not None and not uphold:
            vendor.publish_suspended = False
        item = db.scalar(
            select(admin.ModerationItem).where(
                admin.ModerationItem.content_kind == content_kind,
                admin.ModerationItem.content_ref == content_ref,
                admin.ModerationItem.status == admin.ModerationStatus.pending,
            )
        )
        if item is not None:
            _close_item(db, item.id, uphold, moderator_account_id, reason)

    db.flush()
    suspended = _apply_repeat_offender(db, reports, moderator_account_id) if uphold else False
    # who lost credibility, and are they now past the strike limit? Surfaced so the
    # console can tell a moderator the consequence of the verdict they just gave.
    discredited = []
    if frivolous:
        for account_id in {r.account_id for r in reports}:
            discredited.append(
                {
                    "account_id": account_id,
                    "strikes": frivolous_strikes(db, account_id),
                    "credible": reporter_credible(db, account_id),
                }
            )
    return {
        "upheld": uphold,
        "frivolous": frivolous,
        "reports_closed": len(reports),
        "vendor_suspended": suspended,
        "discredited": discredited,
    }


def _close_item(db: Session, item_id, uphold: bool, moderator_account_id, reason) -> None:
    if item_id is None:
        return
    item = db.get(admin.ModerationItem, item_id)
    if item is None or item.status != admin.ModerationStatus.pending:
        return
    # "approved" on a REPORT means the report was upheld — the content goes down
    admin.decide_moderation(
        db,
        item,
        admin.ModerationStatus.approved if uphold else admin.ModerationStatus.rejected,
        moderator_account_id=moderator_account_id,
        reason=reason,
    )


def upheld_report_count(db: Session, vendor_id) -> int:
    # counted per reported ITEM, not per report row: three drivers agreeing about
    # one bad listing is one offence, not three
    return int(
        db.scalar(
            select(func.count(func.distinct(ContentReport.content_ref))).where(
                ContentReport.vendor_id == vendor_id,
                ContentReport.upheld.is_(True),
            )
        )
        or 0
    )


def _apply_repeat_offender(db: Session, reports: list[ContentReport], moderator_account_id) -> bool:
    if not reports:
        return False
    vendor = db.get(Vendor, reports[0].vendor_id)
    if vendor is None:
        return False
    strikes = _config_int(db, CONFIG_REPEAT_OFFENDER_STRIKES, DEFAULT_REPEAT_OFFENDER_STRIKES)
    if upheld_report_count(db, vendor.id) < strikes:
        return False
    from .service import suspend_vendor

    suspend_vendor(db, vendor, True, moderator_account_id=moderator_account_id)
    return True


@dataclass
class QueueItem:
    item: object
    age_hours: float
    overdue: bool


def queue_with_sla(db: Session, now: datetime | None = None) -> list[QueueItem]:
    """Q-8's SLA is only real if a moderator can SEE what is late. Age and the
    overdue flag ride on every pending item; the 72h constant lives in F14 because
    the promise is platform-wide, not M13's alone."""
    now = now or datetime.now(UTC)
    out = []
    for item in admin.list_pending_moderation(db):
        age = (now - _aware(item.created_at)).total_seconds() / 3600
        out.append(
            QueueItem(item=item, age_hours=round(age, 1), overdue=age > admin.MODERATION_SLA_HOURS)
        )
    return out

"""AI-CONTEXT: M13-FR5 — vendor reviews.

Follows the M2 review pattern (replicated, never imported laterally) with two
deliberate departures, both recorded in HANDOFF-072:

1. **Publish immediately; queue on report.** M2 queues every facility review BEFORE
   publication because a facility scorecard carries defamation exposure (PRD §13).
   A driver's note about a meal does not, and holding every review behind a
   moderator would make the section feel dead. Reported reviews hide instantly
   (Q-8) — low blast radius, trivially restored.
2. **No points.** M2 awards REVIEW_POINTS through the F7 ledger on approval. Points
   are the M10 closed-loop economy funded against the M6 take; routing a reward
   through the ledger from M13 is exactly the money-adjacent path Phase A forbids.

The §11.7 discipline here is distinct-REVIEWER counting: a driver who reviews the
same vendor again REPLACES their earlier verdict rather than adding a second voice,
so "12 drivers" always means twelve people.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.foundation.f13_flags import public as flags

from .enums import ReviewStatus
from .models import Vendor, VendorReview

# one review per driver per vendor per 7 days (FR5), F13-tunable
CONFIG_REVIEW_COOLDOWN_DAYS = "m13_review_cooldown_days"
DEFAULT_REVIEW_COOLDOWN_DAYS = 7
MIN_RATING = 1
MAX_RATING = 5
MAX_REVIEW_CHARS = 500


class InvalidRating(Exception):
    pass


class ReviewTooSoon(Exception):
    """FR5 cadence limit. Carries when the driver may review again so the UI can say
    so plainly rather than just refusing (§12.4 — what happened + what to do)."""

    def __init__(self, next_allowed_at: datetime):
        super().__init__(next_allowed_at.isoformat())
        self.next_allowed_at = next_allowed_at


class VendorNotReviewable(Exception):
    pass


@dataclass
class ReviewSummary:
    """Deliberately carries the raw pair, not just an average: `reviewers` is the
    honest denominator (§11.7), and an average without it invites overreading a
    handful of opinions."""

    average: float | None
    reviewers: int

    @property
    def has_reviews(self) -> bool:
        return self.reviewers > 0


def _cooldown(db: Session) -> timedelta:
    days = int(flags.get_config(db, CONFIG_REVIEW_COOLDOWN_DAYS, DEFAULT_REVIEW_COOLDOWN_DAYS))
    return timedelta(days=days)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def latest_review(db: Session, vendor_id, account_id) -> VendorReview | None:
    return db.scalar(
        select(VendorReview)
        .where(VendorReview.vendor_id == vendor_id, VendorReview.account_id == account_id)
        .order_by(VendorReview.created_at.desc())
        .limit(1)
    )


def submit_review(
    db: Session,
    vendor: Vendor,
    account_id,
    rating: int,
    text: str | None = None,
    now: datetime | None = None,
) -> VendorReview:
    now = now or datetime.now(UTC)
    if not isinstance(rating, int) or not (MIN_RATING <= rating <= MAX_RATING):
        raise InvalidRating(f"rating must be an int {MIN_RATING}-{MAX_RATING}")
    if text is not None and len(text) > MAX_REVIEW_CHARS:
        raise InvalidRating(f"review text is at most {MAX_REVIEW_CHARS} characters")

    existing = latest_review(db, vendor.id, account_id)
    if existing is not None:
        window = _cooldown(db)
        elapsed = now - _aware(existing.created_at)
        if elapsed < window:
            raise ReviewTooSoon(_aware(existing.created_at) + window)
        # past the window: the driver's verdict is UPDATED, not duplicated, so the
        # reviewer count stays a count of people rather than of opinions
        existing.rating = rating
        existing.text = text
        existing.created_at = now
        if existing.status == ReviewStatus.hidden_pending:
            pass  # a hidden review stays hidden until a moderator rules on it
        db.flush()
        return existing

    # created_at is set explicitly, not left to the DB clock: the 7-day cadence is
    # measured against it, and every other M13 timestamp is caller-supplied so the
    # whole module can be reasoned about (and tested) on one clock.
    review = VendorReview(
        vendor_id=vendor.id,
        account_id=account_id,
        rating=rating,
        text=text,
        created_at=now,
    )
    db.add(review)
    db.flush()
    return review


def list_reviews(db: Session, vendor_id, include_hidden: bool = False) -> list[VendorReview]:
    stmt = select(VendorReview).where(VendorReview.vendor_id == vendor_id)
    if not include_hidden:
        stmt = stmt.where(VendorReview.status == ReviewStatus.visible)
    return list(db.scalars(stmt.order_by(VendorReview.created_at.desc())))


def review_summary(db: Session, vendor_id) -> ReviewSummary:
    # hidden and removed reviews are excluded from BOTH the average and the count:
    # a reported review must not keep influencing the score while it is under review
    row = db.execute(
        select(
            func.avg(VendorReview.rating), func.count(func.distinct(VendorReview.account_id))
        ).where(VendorReview.vendor_id == vendor_id, VendorReview.status == ReviewStatus.visible)
    ).one()
    average, reviewers = row
    return ReviewSummary(
        average=round(float(average), 2) if average is not None else None,
        reviewers=int(reviewers or 0),
    )


def can_review(db: Session, vendor_id, account_id, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    existing = latest_review(db, vendor_id, account_id)
    if existing is None:
        return True
    return now - _aware(existing.created_at) >= _cooldown(db)

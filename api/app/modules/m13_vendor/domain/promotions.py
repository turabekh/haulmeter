"""AI-CONTEXT: M13-FR6 — promotions (PRD §17 Q10, resolved 2026-07-25).

Free in Phase A, any verification tier, **labelled slots only**. There is no price,
bid, budget, or billing column anywhere in this file or its table; paid placement
remains an open owner question and building toward it now would be speculative.

**Q-3 is protected structurally, not by vigilance.** Promotions are read by
`promotions_for_facility` — a function the ranking path never calls. `rank_entries`
takes no promotion argument and this module is not imported by `service.py`, so a
promotion has no route into organic order even if someone tried. The Session-A test
that greps `rank_entries` for a promotion term keeps passing UNMODIFIED, which is
the point: the guarantee is a property of the shape, not of a reviewer noticing.

Push delivery rides the Session-A `vendor_alert` class and every one of its caps
(opt-in, <=1 per driver per day, quiet hours, per-vendor mute). Nothing here
loosens them; a promotion is simply another event handed to the same gate.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.foundation.f02_facility import public as facility_registry
from app.foundation.f08_notifications import public as notify
from app.foundation.f10_crowd import public as crowd

from .enums import AppearanceStatus, PromotionScope, PromotionStatus
from .models import Appearance, Promotion, Vendor
from .service import is_presentable

MAX_PROMOTION_CHARS = 140
VENDOR_ALERT = notify.VENDOR_ALERT_CLASS


class InvalidPromotion(Exception):
    pass


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def create_promotion(
    db: Session,
    vendor: Vendor,
    text: str,
    starts_at: datetime,
    ends_at: datetime,
    scope: PromotionScope = PromotionScope.own_appearances,
    now: datetime | None = None,
) -> Promotion:
    now = now or datetime.now(UTC)
    body = (text or "").strip()
    if not body:
        raise InvalidPromotion("a promotion needs text")
    if len(body) > MAX_PROMOTION_CHARS:
        raise InvalidPromotion(f"at most {MAX_PROMOTION_CHARS} characters")
    if ends_at <= starts_at:
        raise InvalidPromotion("the window must end after it starts")
    if _aware(ends_at) <= now:
        # Q-1 spirit: nothing may be published already dead
        raise InvalidPromotion("that window has already passed")

    promotion = Promotion(
        vendor_id=vendor.id, text=body, starts_at=starts_at, ends_at=ends_at, scope=scope
    )
    db.add(promotion)
    db.flush()
    return promotion


def cancel_promotion(db: Session, promotion: Promotion) -> Promotion:
    promotion.status = PromotionStatus.cancelled
    db.flush()
    return promotion


def sweep_promotions(db: Session, now: datetime | None = None) -> int:
    """Q-1 spirit: a promotion past its window vanishes rather than lingering as
    stale content a driver might act on."""
    now = now or datetime.now(UTC)
    expired = 0
    for promotion in db.scalars(
        select(Promotion).where(Promotion.status == PromotionStatus.active)
    ):
        if _aware(promotion.ends_at) <= now:
            promotion.status = PromotionStatus.expired
            expired += 1
    db.flush()
    return expired


def _live(now: datetime):
    return (
        Promotion.status == PromotionStatus.active,
        Promotion.starts_at <= now,
        Promotion.ends_at > now,
    )


def active_promotions(db: Session, vendor_id, now: datetime | None = None) -> list[Promotion]:
    now = now or datetime.now(UTC)
    return list(
        db.scalars(
            select(Promotion)
            .where(Promotion.vendor_id == vendor_id, *_live(now))
            .order_by(Promotion.created_at.desc())
        )
    )


def promotions_for_facility(db: Session, facility_id, now: datetime | None = None) -> list[dict]:
    """The labelled slot's contents for one facility. Separate from discovery on
    purpose — a caller cannot accidentally fold this into the ranked list, because
    the ranked list is produced by a different function that never sees it."""
    now = now or datetime.now(UTC)
    vendor_ids: set = set()

    # scope 1: vendors scheduled at this facility (their promotion travels with them)
    for appearance in db.scalars(
        select(Appearance).where(
            Appearance.facility_id == facility_id,
            Appearance.status.in_((AppearanceStatus.scheduled, AppearanceStatus.live)),
            Appearance.ends_at > now,
        )
    ):
        vendor_ids.add(appearance.vendor_id)

    # scope 2: the service centre that claimed this facility (FR7)
    from .claims import approved_claim

    claim = approved_claim(db, facility_id)
    if claim is not None:
        vendor_ids.add(claim.vendor_id)

    if not vendor_ids:
        return []

    rows = db.scalars(
        select(Promotion)
        .where(Promotion.vendor_id.in_(vendor_ids), *_live(now))
        .order_by(Promotion.created_at.desc())
    )
    out = []
    for promotion in rows:
        vendor = db.get(Vendor, promotion.vendor_id)
        if vendor is None or not is_presentable(vendor):
            continue  # a suspended vendor promotes nothing, by either route
        if promotion.scope == PromotionScope.claimed_facility and (
            claim is None or claim.vendor_id != vendor.id
        ):
            continue
        out.append(
            {
                "promotion_id": promotion.id,
                "vendor_id": vendor.id,
                "vendor_name": vendor.name,
                "text": promotion.text,
                "ends_at": promotion.ends_at,
                # the client renders this in a labelled container; it is never
                # merged into the organic list (Q-3)
                "promoted": True,
            }
        )
    return out


def notify_promotion(
    db: Session, promotion: Promotion, gateway, now: datetime | None = None
) -> list:
    """Hand the promotion to the `vendor_alert` gate. Every cap the class declares
    still applies — this function decides only WHO is plausibly relevant, never
    whether the message may be sent.

    Relevance is approximated by "drivers who have confirmed this vendor before".
    The class declares `route_relevant_only`, but no live route context exists yet
    (M8 has no per-driver route feed), so a demonstrated prior connection is the
    honest stand-in rather than a claim of route targeting we cannot make.
    """
    now = now or datetime.now(UTC)
    vendor = db.get(Vendor, promotion.vendor_id)
    if vendor is None or not is_presentable(vendor):
        return []
    if promotion.status != PromotionStatus.active or _aware(promotion.ends_at) <= now:
        return []

    audience = db.scalars(
        select(crowd.Submission.account_id)
        .where(
            crowd.Submission.subject_ref == str(vendor.id),
            crowd.Submission.signal_type == crowd.SignalType.vendor_present,
            crowd.Submission.account_id.is_not(None),
        )
        .distinct()
    )
    sent = []
    for account_id in audience:
        sent.append(
            notify.dispatch(
                db,
                account_id,
                notify.NotificationTier.P1,
                VENDOR_ALERT,
                vendor.name,
                promotion.text,
                f"/vendor/{vendor.id}",
                gateway,
                now=now,
                subject_ref=str(vendor.id),
            )
        )
    promotion.pushed_at = now
    db.flush()
    return sent


def facility_name(db: Session, facility_id) -> str | None:
    facility = facility_registry.get_facility(db, facility_id)
    return facility.name if facility is not None else None


__all__ = [
    "MAX_PROMOTION_CHARS",
    "InvalidPromotion",
    "active_promotions",
    "cancel_promotion",
    "create_promotion",
    "facility_name",
    "notify_promotion",
    "promotions_for_facility",
    "sweep_promotions",
]

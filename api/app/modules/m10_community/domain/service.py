"""AI-CONTEXT: M10 Community & Points Economy (PRD §8.10) — pay drivers for the
data everyone else extracts for free, and create peer-to-peer liquidity
incumbents can't copy. Owns schema m10.

- Points economy (M10-FR1): earn rules per contribution type on top of F10's
  trust-weighted, geofence-gated points; redemption solely against M6 bookings
  at a fixed rate (F7 points currency), with rate-limit anti-gaming. book_with_
  points funds the discount from the M6 take (platform_revenue) — the
  "partially circular" monetization (PRD §8.10).
- Spot handoff relay (M10-FR2): "leaving in X" from a geofence-present driver at
  a FREE public lot (never M6 inventory); a nearby driver claims; both earn on
  the claimer's confirmed ENTER. The highest-novelty bet — conservative proof.
- Contributor reputation (M10-FR3): levels + counts from the contribution log.
- Moderated facility Q&A (M10-FR4): answers from geofence-present drivers,
  pinned to the M2 facility page.

Composes f02 + f03 + f07 + f10 + m06. Runs behind the F13 flag m10_community.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.foundation.f02_facility import public as facility_registry
from app.foundation.f03_location import public as location
from app.foundation.f07_ledger import public as ledger
from app.foundation.f10_crowd import public as crowd
from app.modules.m06_parking import public as m6

from .enums import HandoffState
from .models import ContributionLog, FacilityAnswer, FacilityQuestion, Handoff

FLAG_KEY = "m10_community"
MODULE = "m10"

# economy parameters — F13-config tunable at activation (PRD §8.10 DoD)
REDEEM_CENTS_PER_POINT = 1  # 1 point = 1¢ against an M6 booking
EARN_RULES = {"review": 15, "handoff": 10, "answer": 5}
CONFIG_EARN_PREFIX = "m10_earn_"  # F13 rewards scope; per-kind key, editable in F14 admin
RATE_LIMIT_PER_DAY = 50  # anti-gaming: max contributions/24h/account
# free public lots a handoff may relay — NEVER a bookable M6 property
FREE_LOT_TYPES = (
    facility_registry.FacilityType.truck_stop,
    facility_registry.FacilityType.rest_area,
)
_REP_LEVELS = [(2000, "elite"), (500, "pro"), (100, "regular"), (0, "rookie")]


class RateLimited(Exception):
    pass


class InsufficientPoints(Exception):
    pass


class NotPresent(Exception):
    pass


class NotFreeLot(Exception):
    pass


class HandoffNotClaimable(Exception):
    pass


@dataclass
class Reputation:
    points_earned: int
    contribution_count: int
    trust_score: float
    level: str


def register_module(db: Session) -> None:
    from app.foundation.f13_flags import public as flags
    from app.foundation.f14_admin import public as admin

    flags.register_flag(db, FLAG_KEY, description="M10 Community & Points Economy")
    admin.register_admin_view(db, "m10.points", MODULE, "Community & Points", "/admin/m10/points")


# --- Points economy (M10-FR1) ---
def points_balance(db: Session, account_id) -> int:
    account = ledger.get_or_create_account(
        db,
        ledger.LedgerAccountKind.points_balance,
        f"points:{account_id}",
        currency=ledger.Currency.points,
        owner_ref=account_id,
    )
    return int(ledger.balance(db, account))  # plain int (points are whole)


def _rate_limited(db: Session, account_id, now: datetime) -> bool:
    since = now - timedelta(days=1)
    count = db.scalar(
        select(func.count())
        .select_from(ContributionLog)
        .where(ContributionLog.account_id == account_id, ContributionLog.created_at >= since)
    )
    return count >= RATE_LIMIT_PER_DAY


def _earn_points(db: Session, kind: str) -> int:
    # the live per-kind earn rate: F13 config (edited in the F14 admin console)
    # falling back to the compiled EARN_RULES default (the HANDOFF-041 pattern)
    from app.foundation.f13_flags import public as flags

    return int(flags.get_config(db, f"{CONFIG_EARN_PREFIX}{kind}", EARN_RULES.get(kind, 0)))


def award_contribution(db: Session, account_id, kind: str, now: datetime) -> int:
    if _rate_limited(db, account_id, now):
        raise RateLimited(str(account_id))
    points = _earn_points(db, kind)
    if points > 0:
        crowd.issue_points(db, account_id, points)  # F7 points_earn via F10
        db.add(ContributionLog(account_id=account_id, kind=kind, points=points))
        db.flush()
    return points


def redeem_points(db: Session, account_id, points: int, now: datetime | None = None) -> int:
    if points <= 0:
        return 0
    if points_balance(db, account_id) < points:
        raise InsufficientPoints(str(account_id))
    balance = ledger.get_or_create_account(
        db,
        ledger.LedgerAccountKind.points_balance,
        f"points:{account_id}",
        currency=ledger.Currency.points,
        owner_ref=account_id,
    )
    pool = ledger.get_or_create_account(
        db, ledger.LedgerAccountKind.points_pool, "points:pool", currency=ledger.Currency.points
    )
    ledger.post_entry(
        db,
        ledger.EntryType.points_redeem,
        [
            ledger.Posting(pool.id, ledger.Direction.debit, points),
            ledger.Posting(balance.id, ledger.Direction.credit, points),
        ],
        currency=ledger.Currency.points,
    )
    return points * REDEEM_CENTS_PER_POINT


def book_with_points(db: Session, spot, driver_account_id, start_at, end_at, points, now=None):
    # AI-CONTEXT: redemption is ONLY against M6 bookings (PRD §8.10). The discount
    # is funded from the M6 take (platform_revenue) — partially circular economy.
    discount_cents = redeem_points(db, driver_account_id, points, now)
    booking = m6.book(db, spot, driver_account_id, start_at, end_at)
    if discount_cents > 0:
        cash = ledger.get_or_create_account(
            db, ledger.LedgerAccountKind.cash_clearing, "cash:parking", currency=ledger.Currency.usd
        )
        platform = ledger.get_or_create_account(
            db,
            ledger.LedgerAccountKind.platform_revenue,
            "revenue:parking",
            currency=ledger.Currency.usd,
        )
        ledger.post_entry(
            db,
            ledger.EntryType.adjustment,
            [
                ledger.Posting(platform.id, ledger.Direction.debit, discount_cents),
                ledger.Posting(cash.id, ledger.Direction.credit, discount_cents),
            ],
            description=f"points redemption on booking {booking.id}",
        )
    return booking, discount_cents


# --- Spot handoff relay (M10-FR2) ---
def broadcast_handoff(
    db: Session, account_id, facility_ref, leaving_at: datetime, now: datetime
) -> Handoff:
    fac = facility_registry.get_facility(db, facility_ref)
    if fac is None or fac.facility_type not in FREE_LOT_TYPES:
        raise NotFreeLot(str(facility_ref))  # never cannibalize M6 inventory
    if not location.is_present(db, account_id, facility_ref):
        raise NotPresent(str(account_id))
    handoff = Handoff(
        facility_ref=facility_ref,
        broadcaster_id=account_id,
        leaving_at=leaving_at,
        state=HandoffState.open,
    )
    db.add(handoff)
    db.flush()
    return handoff


def claim_handoff(db: Session, handoff: Handoff, claimer_id, now: datetime) -> Handoff:
    if handoff.state != HandoffState.open:
        raise HandoffNotClaimable(str(handoff.id))
    handoff.claimer_id = claimer_id
    handoff.state = HandoffState.claimed
    db.flush()
    return handoff


def confirm_handoff(db: Session, handoff: Handoff, now: datetime) -> Handoff:
    if handoff.state != HandoffState.claimed or handoff.claimer_id is None:
        raise HandoffNotClaimable(str(handoff.id))
    # the claimer must actually arrive — conservative geofence proof (PRD note)
    if not location.is_present(db, handoff.claimer_id, handoff.facility_ref):
        raise NotPresent(str(handoff.claimer_id))
    award_contribution(db, handoff.broadcaster_id, "handoff", now)
    award_contribution(db, handoff.claimer_id, "handoff", now)
    handoff.state = HandoffState.confirmed
    handoff.confirmed_at = now
    db.flush()
    return handoff


def nearby_handoffs(db: Session, lat: float, lon: float, radius_m: float) -> list[Handoff]:
    # open "leaving soon" broadcasts at free lots within reach — the claimable feed
    facilities = facility_registry.nearest(db, lat, lon, radius_m)
    fac_ids = [f.id for f in facilities]
    if not fac_ids:
        return []
    return list(
        db.scalars(
            select(Handoff).where(
                Handoff.facility_ref.in_(fac_ids), Handoff.state == HandoffState.open
            )
        )
    )


# --- Contributor reputation (M10-FR3) ---
def reputation(db: Session, account_id) -> Reputation:
    rows = list(db.scalars(select(ContributionLog).where(ContributionLog.account_id == account_id)))
    earned = sum(r.points for r in rows)
    trust = crowd.get_or_create_trust(db, account_id)
    level = next(name for threshold, name in _REP_LEVELS if earned >= threshold)
    return Reputation(
        points_earned=earned,
        contribution_count=len(rows),
        trust_score=trust.score,
        level=level,
    )


def leaderboard(db: Session, limit: int = 10) -> list[dict]:
    rows = db.execute(
        select(ContributionLog.account_id, func.sum(ContributionLog.points).label("points"))
        .group_by(ContributionLog.account_id)
        .order_by(func.sum(ContributionLog.points).desc())
        .limit(limit)
    )
    return [{"account_id": r.account_id, "points": int(r.points)} for r in rows]


# --- Moderated facility Q&A (M10-FR4) ---
def ask_question(
    db: Session, account_id, facility_ref, text: str, now: datetime
) -> FacilityQuestion:
    question = FacilityQuestion(facility_ref=facility_ref, asker_id=account_id, text=text)
    db.add(question)
    db.flush()
    return question


def answer_question(
    db: Session, account_id, question: FacilityQuestion, text: str, now: datetime
) -> FacilityAnswer:
    present = location.is_present(db, account_id, question.facility_ref)
    answer = FacilityAnswer(
        question_id=question.id, answerer_id=account_id, text=text, presence_proven=present
    )
    db.add(answer)
    db.flush()
    if present:  # on-site answers earn (and rank higher)
        award_contribution(db, account_id, "answer", now)
    return answer


def list_questions(db: Session, facility_ref) -> list[FacilityQuestion]:
    return list(
        db.scalars(
            select(FacilityQuestion)
            .where(FacilityQuestion.facility_ref == facility_ref)
            .order_by(FacilityQuestion.created_at.desc())
        )
    )

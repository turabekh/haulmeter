import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.foundation.f02_facility import public as facility_registry
from app.foundation.f03_location import public as location
from app.foundation.f07_ledger import public as ledger

from .enums import SignalType
from .models import Belief, ContributorTrust, Submission

BASE_TRUST = 1.0
MAX_TRUST = 3.0
MIN_TRUST = 0.1
UNPROVEN_WEIGHT_FACTOR = 0.3
AGGREGATION_WINDOW_HALFLIVES = 10

HALF_LIFE_SECONDS: dict[SignalType, float] = {
    SignalType.parking_fullness: 3600,  # 1 hour
    SignalType.weigh_station_status: 7200,  # 2 hours
    SignalType.fuel_price: 86400,  # 24 hours
    SignalType.facility_attribute: 2592000,  # 30 days
}

POINTS_PER_SIGNAL: dict[SignalType, int] = {
    SignalType.parking_fullness: 5,
    SignalType.weigh_station_status: 5,
    SignalType.fuel_price: 3,
    SignalType.facility_attribute: 10,
}

# a reading younger than this counts as "fresh" for authoritative-vs-crowd precedence
FRESH_THRESHOLD_SECONDS: dict[SignalType, float] = {
    SignalType.parking_fullness: 1800,  # 30 min (TPIMS updates every 1-5 min)
    SignalType.weigh_station_status: 3600,
    SignalType.fuel_price: 43200,
    SignalType.facility_attribute: 604800,
}
AUTHORITATIVE_TRUST = 5.0  # above any crowd trust_weight


class FacilityNotFound(Exception):
    pass


@dataclass
class BeliefResult:
    value: dict
    confidence: float
    sample_size: int
    freshest_at: datetime | None


# --- Contributor trust ---
def get_or_create_trust(db: Session, account_id) -> ContributorTrust:
    trust = db.get(ContributorTrust, account_id)
    if trust is None:
        trust = ContributorTrust(account_id=account_id, score=BASE_TRUST)
        db.add(trust)
        db.flush()
    return trust


def adjust_trust(db: Session, account_id, confirmed: bool) -> ContributorTrust:
    trust = get_or_create_trust(db, account_id)
    if confirmed:
        trust.score = min(MAX_TRUST, trust.score + 0.1)
        trust.confirmed_count += 1
    else:
        trust.score = max(MIN_TRUST, trust.score - 0.2)
        trust.rejected_count += 1
    db.flush()
    return trust


# --- Points issuance (F7 closed-loop) ---
def issue_points(db: Session, account_id, amount: int):
    if amount <= 0:
        return None
    balance = ledger.get_or_create_account(
        db,
        ledger.LedgerAccountKind.points_balance,
        f"points:{account_id}",
        currency=ledger.Currency.points,
        owner_ref=account_id,
    )
    pool = ledger.get_or_create_account(
        db,
        ledger.LedgerAccountKind.points_pool,
        "points:pool",
        currency=ledger.Currency.points,
    )
    return ledger.post_entry(
        db,
        ledger.EntryType.points_earn,
        [
            ledger.Posting(balance.id, ledger.Direction.debit, amount),
            ledger.Posting(pool.id, ledger.Direction.credit, amount),
        ],
        currency=ledger.Currency.points,
    )


# --- Submission (geofence-presence gated) ---
def submit(
    db: Session,
    account_id,
    facility_id,
    signal_type: SignalType,
    value: dict,
    submitted_at: datetime,
    award: bool = True,
) -> Submission:
    if facility_registry.get_facility(db, facility_id) is None:
        raise FacilityNotFound(str(facility_id))
    presence_proven = location.is_present(db, account_id, facility_id)
    trust = get_or_create_trust(db, account_id)

    submission = Submission(
        account_id=account_id,
        facility_id=facility_id,
        signal_type=signal_type,
        value=value,
        presence_proven=presence_proven,
        trust_weight=trust.score,
        submitted_at=submitted_at,
    )
    db.add(submission)
    db.flush()

    if presence_proven and award:
        issue_points(db, account_id, POINTS_PER_SIGNAL.get(signal_type, 0))
    return submission


def submit_authoritative(
    db: Session,
    facility_id,
    signal_type: SignalType,
    value: dict,
    submitted_at: datetime,
    source: str,
    trust_data: bool = True,
) -> Submission | None:
    # an authoritative feed (e.g. TPIMS). No driver, no points, no geofence proof —
    # but a real source + real timestamp. Honors the feed's trust flag (condition A):
    # if trust_data is false the reading is NOT recorded, so it never presents as
    # fresh truth. Returns None when skipped.
    if not trust_data:
        return None
    if facility_registry.get_facility(db, facility_id) is None:
        raise FacilityNotFound(str(facility_id))
    submission = Submission(
        account_id=None,
        facility_id=facility_id,
        signal_type=signal_type,
        value=value,
        presence_proven=True,
        authoritative=True,
        source=source,
        trust_weight=AUTHORITATIVE_TRUST,
        submitted_at=submitted_at,
    )
    db.add(submission)
    db.flush()
    return submission


# --- Aggregation: current best belief ---
def _contributor_key(s: Submission):
    # one belief contribution per contributor: a driver (account), a feed (source),
    # else the row itself. So the SAME driver re-reporting a spot can't stack weight
    # or inflate the "N drivers" count — only their freshest reading counts.
    if s.authoritative:
        return ("feed", s.source)
    if s.account_id is not None:
        return ("acct", s.account_id)
    return ("row", s.id)


def _latest_per_contributor(submissions: list[Submission]) -> list[Submission]:
    latest: dict = {}
    for s in submissions:
        key = _contributor_key(s)
        cur = latest.get(key)
        if cur is None or s.submitted_at > cur.submitted_at:
            latest[key] = s
    return list(latest.values())


def _decay_weight(age_seconds: float, signal_type: SignalType) -> float:
    half_life = HALF_LIFE_SECONDS[signal_type]
    return 0.5 ** (max(0.0, age_seconds) / half_life)


def aggregate_belief(
    db: Session, facility_id, signal_type: SignalType, as_of: datetime
) -> BeliefResult | None:
    window = HALF_LIFE_SECONDS[signal_type] * AGGREGATION_WINDOW_HALFLIVES
    submissions = list(
        db.scalars(
            select(Submission).where(
                Submission.facility_id == facility_id,
                Submission.signal_type == signal_type,
            )
        )
    )
    submissions = _latest_per_contributor(submissions)
    scored: list[tuple[Submission, float]] = []
    for submission in submissions:
        age = (as_of - submission.submitted_at).total_seconds()
        if age > window:
            continue
        weight = (
            submission.trust_weight
            * _decay_weight(age, signal_type)
            * (1.0 if submission.presence_proven else UNPROVEN_WEIGHT_FACTOR)
        )
        if weight > 0:
            scored.append((submission, weight))

    if not scored:
        return None

    # Belief precedence when an authoritative feed (TPIMS) contributes (condition A):
    # fresh authoritative > fresh crowd > stale authoritative > stale crowd. Pure
    # crowd data is untouched (the branch below only runs if any authoritative row
    # is in scope), so existing crowd behavior — decay-weighted over all — is intact.
    if any(s.authoritative for s, _ in scored):
        fresh_cutoff = FRESH_THRESHOLD_SECONDS[signal_type]

        def _is_fresh(sub) -> bool:
            return (as_of - sub.submitted_at).total_seconds() <= fresh_cutoff

        for want_fresh, want_auth in ((True, True), (True, False), (False, True), (False, False)):
            group = [
                (s, w)
                for s, w in scored
                if _is_fresh(s) == want_fresh and s.authoritative == want_auth
            ]
            if group:
                scored = group
                break

    total_weight = sum(w for _, w in scored)
    freshest = max(s.submitted_at for s, _ in scored)
    sample_size = len(scored)

    if signal_type == SignalType.fuel_price:
        avg = sum(s.value["price_cents"] * w for s, w in scored) / total_weight
        confidence = min(1.0, total_weight / (total_weight + 1.0))
        return BeliefResult({"price_cents": round(avg)}, confidence, sample_size, freshest)

    tally: dict[str, float] = {}
    representative: dict[str, dict] = {}
    for submission, weight in scored:
        key = json.dumps(submission.value, sort_keys=True)
        tally[key] = tally.get(key, 0.0) + weight
        representative[key] = submission.value
    winner_key = max(tally, key=tally.get)
    confidence = tally[winner_key] / total_weight
    return BeliefResult(representative[winner_key], confidence, sample_size, freshest)


def update_belief(
    db: Session, facility_id, signal_type: SignalType, as_of: datetime
) -> Belief | None:
    result = aggregate_belief(db, facility_id, signal_type, as_of)
    if result is None:
        return None
    belief = db.scalar(
        select(Belief).where(Belief.facility_id == facility_id, Belief.signal_type == signal_type)
    )
    if belief is None:
        belief = Belief(facility_id=facility_id, signal_type=signal_type)
        db.add(belief)
    belief.value = result.value
    belief.confidence = result.confidence
    belief.sample_size = result.sample_size
    belief.computed_at = as_of
    belief.freshest_at = result.freshest_at
    db.flush()
    return belief


def get_belief(db: Session, facility_id, signal_type: SignalType) -> Belief | None:
    return db.scalar(
        select(Belief).where(Belief.facility_id == facility_id, Belief.signal_type == signal_type)
    )

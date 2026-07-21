from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.foundation.f02_facility import public as facility_registry
from app.foundation.f03_location import public as location
from app.foundation.f04_evidence import public as evidence

from .enums import CounterpartyKind, LoadSource, LoadStatus, StopStatus, StopType
from .models import Counterparty, Load, Stop


class FacilityNotFound(Exception):
    pass


# --- Counterparty registry ---
def create_counterparty(
    db: Session,
    name: str,
    kind: CounterpartyKind,
    mc_number: str | None = None,
    contact_email: str | None = None,
    contact_phone: str | None = None,
) -> Counterparty:
    counterparty = Counterparty(
        name=name,
        kind=kind,
        mc_number=mc_number,
        contact_email=contact_email,
        contact_phone=contact_phone,
        payment_behavior={},
    )
    db.add(counterparty)
    db.flush()
    return counterparty


def record_payment_observation(
    db: Session, counterparty: Counterparty, days_to_pay: int
) -> Counterparty:
    behavior = dict(counterparty.payment_behavior or {})
    observations = list(behavior.get("days_to_pay", []))
    observations.append(days_to_pay)
    behavior["days_to_pay"] = observations
    behavior["avg_days_to_pay"] = sum(observations) / len(observations)
    counterparty.payment_behavior = behavior
    db.flush()
    return counterparty


def record_claim(db: Session, counterparty: Counterparty) -> Counterparty:
    counterparty.claim_count += 1
    db.flush()
    return counterparty


# --- Loads ---
def create_load(
    db: Session,
    account_id,
    counterparty_id=None,
    reference_number: str | None = None,
    rate_cents: int | None = None,
    detention_rate_cents_per_hour: int | None = None,
    free_time_minutes: int | None = None,
    accessorial_terms: dict | None = None,
    source: LoadSource = LoadSource.manual,
) -> Load:
    load = Load(
        account_id=account_id,
        counterparty_id=counterparty_id,
        reference_number=reference_number,
        rate_cents=rate_cents,
        detention_rate_cents_per_hour=detention_rate_cents_per_hour,
        free_time_minutes=free_time_minutes,
        accessorial_terms=accessorial_terms or {},
        source=source,
    )
    db.add(load)
    db.flush()
    return load


def create_load_from_parsed_terms(db: Session, account_id, parsed: dict) -> Load:
    return create_load(
        db,
        account_id,
        counterparty_id=parsed.get("counterparty_id"),
        reference_number=parsed.get("reference_number"),
        rate_cents=parsed.get("rate_cents"),
        detention_rate_cents_per_hour=parsed.get("detention_rate_cents_per_hour"),
        free_time_minutes=parsed.get("free_time_minutes"),
        accessorial_terms=parsed.get("accessorial_terms", {}),
        source=LoadSource.rate_con_parse,
    )


def set_load_status(db: Session, load: Load, status: LoadStatus) -> Load:
    load.status = status
    db.flush()
    return load


def get_load(db: Session, load_id) -> Load | None:
    return db.get(Load, load_id)


def get_stop(db: Session, stop_id) -> Stop | None:
    return db.get(Stop, stop_id)


def get_counterparty(db: Session, counterparty_id) -> Counterparty | None:
    return db.get(Counterparty, counterparty_id)


# --- Stops ---
def add_stop(
    db: Session,
    load: Load,
    facility_id,
    stop_type: StopType,
    sequence: int | None = None,
    appointment_start: datetime | None = None,
    appointment_end: datetime | None = None,
    free_time_minutes: int | None = None,
    detention_rate_cents_per_hour: int | None = None,
) -> Stop:
    if facility_registry.get_facility(db, facility_id) is None:
        raise FacilityNotFound(str(facility_id))
    if sequence is None:
        current_max = db.scalar(select(func.max(Stop.sequence)).where(Stop.load_id == load.id))
        sequence = 0 if current_max is None else current_max + 1
    stop = Stop(
        load_id=load.id,
        facility_id=facility_id,
        sequence=sequence,
        stop_type=stop_type,
        appointment_start=appointment_start,
        appointment_end=appointment_end,
        free_time_minutes=free_time_minutes,
        detention_rate_cents_per_hour=detention_rate_cents_per_hour,
    )
    db.add(stop)
    db.flush()
    return stop


def effective_detention_terms(db: Session, stop: Stop) -> tuple[int | None, int | None]:
    load = db.get(Load, stop.load_id)
    free_time = (
        stop.free_time_minutes if stop.free_time_minutes is not None else load.free_time_minutes
    )
    rate = (
        stop.detention_rate_cents_per_hour
        if stop.detention_rate_cents_per_hour is not None
        else load.detention_rate_cents_per_hour
    )
    return free_time, rate


def arm_stop(db: Session, stop: Stop) -> Stop:
    load = db.get(Load, stop.load_id)
    if stop.evidence_log_id is None:
        log = evidence.create_log(
            db, load.account_id, stop_ref=stop.id, label=f"stop-{stop.sequence}"
        )
        stop.evidence_log_id = log.id
    location.arm_geofence(db, load.account_id, stop.facility_id)
    stop.geofence_armed = True
    stop.status = StopStatus.armed
    db.flush()
    return stop


def disarm_stop(db: Session, stop: Stop, occurred_at: datetime | None = None) -> Stop:
    load = db.get(Load, stop.load_id)
    location.disarm_geofence(db, load.account_id, stop.facility_id, occurred_at)
    stop.geofence_armed = False
    db.flush()
    return stop


def list_stops(db: Session, load: Load) -> list[Stop]:
    return list(db.scalars(select(Stop).where(Stop.load_id == load.id).order_by(Stop.sequence)))


def active_stop_for_account(db: Session, account_id) -> Stop | None:
    # the driver's current stop: the most recent ARMED stop across their loads
    # (arm is the active marker; arrival is derived from geofence presence, not a
    # status change). Lets a fresh device resume The Meter without local state.
    stmt = (
        select(Stop)
        .join(Load, Stop.load_id == Load.id)
        .where(Load.account_id == account_id, Stop.status == StopStatus.armed)
        .order_by(Stop.created_at.desc())
    )
    return db.scalars(stmt).first()

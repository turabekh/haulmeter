from datetime import UTC, datetime

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
    appointment_source: str | None = None,
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
        # a window with no value has no provenance to state; claiming one would be the
        # same defect this field exists to fix, one layer down
        appointment_source=appointment_source if appointment_start is not None else None,
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


# AI-CONTEXT: the moments a dispute turns on (§23 entry 70).
#
# F4's whole purpose is "artifacts that survive a dispute", and a stop that had been
# armed, arrived at, notified on and departed produced ONE record — the on-time proof
# check — because nothing else ever wrote to the stop's log. Geofence ENTER/EXIT are F3
# events and nothing bridged them into F4; the notice and the departure were not
# recorded at all. So the pack a broker receives said an event occurred and not which.
#
# These are the three a detention argument is actually made of: when the driver got
# there, when the counterparty was told the clock had started, and when the truck left.
EVENT_ARRIVED = "arrived"
EVENT_NOTICE_SENT = "notice_sent"
EVENT_DEPARTED = "departed"


def record_stop_event(
    db: Session,
    stop: Stop,
    event: str,
    occurred_at: datetime | None = None,
    record_type=None,
    **extra,
) -> None:
    """Append one fact to the stop's hash-chained log. Silent when the stop has no log
    yet — an unarmed stop has nothing to append to, and losing the event is better than
    refusing the action that produced it."""
    if stop.evidence_log_id is None:
        return
    log = db.get(evidence.EvidenceLog, stop.evidence_log_id)
    if log is None:
        return
    evidence.append_record(
        db,
        log,
        record_type or evidence.RecordType.USER_ACTION,
        {"event": event, **extra},
        occurred_at=occurred_at or datetime.now(UTC),
    )


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


def set_stop_appointment(
    db: Session,
    stop: Stop,
    appointment_start: datetime | None,
    appointment_end: datetime | None = None,
    source: str = "manual",
) -> Stop:
    """Correct a stop's appointment window (§23 entry 62).

    AI-CONTEXT: F5 owns `Stop.appointment_*`, and nothing could write it after
    creation — which made M5-FR1 half a feature. FR1 exists so a driver sees a
    MIS-PARSED window while they are still approaching and can still do something
    about it; the screen showed the window and its provenance and then offered no way
    to fix it, so the only remedy was ringing the broker with nowhere to record the
    answer. Correcting it is the driver's own account of the time, so the provenance
    becomes `manual` unless a caller states otherwise.
    """
    stop.appointment_start = appointment_start
    stop.appointment_end = appointment_end
    stop.appointment_source = source if appointment_start is not None else None
    db.flush()
    return stop


def depart_stop(db: Session, stop: Stop, occurred_at: datetime | None = None) -> Stop:
    # the driver is done here: mark departed + disarm. Drops out of the active-stop
    # query, so ending a load is durable (not just a client-side clear).
    disarm_stop(db, stop, occurred_at)
    stop.status = StopStatus.departed
    stop.departed_at = occurred_at
    # the moment the truck left, in the chain — half of every detention argument
    record_stop_event(db, stop, EVENT_DEPARTED, occurred_at)
    db.flush()
    return stop


def list_loads(db: Session, account_id, limit: int = 50) -> list[Load]:
    """A driver's loads, newest first.

    AI-CONTEXT: nothing has ever asked this question. `/load/active` returns the ONE
    armed stop and there is no other read, so a load that ended left no way back to
    itself — its evidence log, condition captures and stop-scoped BOL all still in the
    database with no route reaching them. An evidence pack is worth having precisely
    because it can be produced weeks later when a broker disputes; unreachable the
    moment the driver taps "End load" is the opposite of that.
    """
    stmt = (
        select(Load)
        .where(Load.account_id == account_id)
        .order_by(Load.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def complete_load_if_finished(db: Session, load: Load) -> Load:
    """Mark a load completed once no stop is still live.

    `LoadStatus` has carried draft/active/completed/canceled since F5 was written and
    `set_load_status` was never called from anywhere — so every load ever created is
    still `draft`. Ending a load departed the STOP and left the load untouched, which
    is why "completed" could not be listed even by something that wanted to.
    """
    live = {StopStatus.pending, StopStatus.armed, StopStatus.arrived}
    if any(s.status in live for s in load.stops):
        return load
    if load.status != LoadStatus.completed:
        set_load_status(db, load, LoadStatus.completed)
    return load


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

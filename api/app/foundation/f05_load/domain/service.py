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


class InvalidContactEmail(ValueError):
    pass


# AI-CONTEXT: the address every counterparty notice is sent to, and until this session
# there was NOWHERE in the product to put one. `contact_email` has been on the model since
# F5 shipped and nothing but tests ever wrote it, so every row carried NULL and M3
# addressed an invented literal instead — the detention wedge could not deliver to anyone,
# by construction (previous session, SESSION-REPORT.md §3.1).
#
# PRAGMATIC, NOT RFC-COMPLETE, and that is a decision rather than a shortcut. A real
# address is whatever the receiving server accepts, so any client-side rule is a guess;
# the useful job here is catching the typo a driver can see and fix ("acme.com" with no
# `@`, a trailing name, a pasted sentence) before it becomes an
# `SMTPRecipientsRefused` — which `PERMANENT_FAILURES` never retries, so a malformed
# address costs the notice permanently. Anything stricter starts rejecting addresses that
# work.
MAX_CONTACT_EMAIL = 320  # the column's width


def validate_contact_email(raw: str | None) -> str | None:
    """Normalise and check. None/blank means an explicit CLEAR, not an error.

    Raises `InvalidContactEmail` with a message a driver can act on.
    """
    if raw is None:
        return None
    email = raw.strip()
    if not email:
        return None  # "remove the address on file" is a legitimate thing to ask for
    if len(email) > MAX_CONTACT_EMAIL:
        raise InvalidContactEmail(f"email must be {MAX_CONTACT_EMAIL} characters or fewer")
    if any(ch.isspace() for ch in email):
        raise InvalidContactEmail("email cannot contain spaces")
    if email.count("@") != 1:
        raise InvalidContactEmail("email needs exactly one @")
    local, _, domain = email.partition("@")
    if not local or not domain:
        raise InvalidContactEmail("email needs a name and a domain")
    if "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise InvalidContactEmail("email domain needs a dot")
    return email


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


def set_load_counterparty_email(
    db: Session, load: Load, email: str | None
) -> tuple[Counterparty, bool]:
    """Set this load's broker address. Returns (counterparty, copied).

    AI-CONTEXT: edit in place if and only if every load referencing this counterparty row
    belongs to this load's account; otherwise COPY-ON-WRITE — a new row carrying the same
    identity with the new address, and only this load repointed at it.

    WHY, given that `create_counterparty` never dedupes and so each load gets its own row
    today: nothing ENFORCES that. It is a property of one call site, not of the schema, and
    the tests share rows freely. An unconditional in-place edit would therefore be correct
    only by accident — and the failure mode if that accident ends is that one driver
    editing their broker's address silently rewrites where another driver's detention
    notices go. That is not a bug you find from a stack trace.

    One query decides it. Safe now, safe if sharing ever appears, and it needs no migration
    and no account column on the counterparty — both of which are recorded follow-ups for
    the F5 section rather than this change.
    """
    counterparty = get_counterparty(db, load.counterparty_id) if load.counterparty_id else None
    if counterparty is None:
        raise InvalidContactEmail("this load has no counterparty to address")

    others = db.scalar(
        select(func.count())
        .select_from(Load)
        .where(
            Load.counterparty_id == counterparty.id,
            Load.account_id != load.account_id,
        )
    )
    if others:
        copy = create_counterparty(
            db,
            counterparty.name,
            counterparty.kind,
            mc_number=counterparty.mc_number,
            contact_email=email,
            contact_phone=counterparty.contact_phone,
        )
        load.counterparty_id = copy.id
        db.flush()
        return copy, True

    counterparty.contact_email = email
    db.flush()
    return counterparty, False


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
    # AI-CONTEXT: sweep this account's OTHER armings too (F3-1). Departing disarms the
    # fence for THIS facility and always has; what it never did is notice the fences left
    # behind by stops the driver never departed — the tab closed, the app reinstalled, the
    # load abandoned. Those stay armed forever and keep minting arrivals at docks the
    # driver is merely driving past, which `visit_window` can hand to the NEXT load.
    #
    # Ordered after the status change deliberately: the predicate asks whether a live stop
    # still needs each fence, and this stop has just stopped being one.
    location.reconcile_armings(
        db, has_live_stop_at, account_id=stop_account_id(db, stop), now=occurred_at
    )
    return stop


def stop_account_id(db: Session, stop: Stop):
    load = db.get(Load, stop.load_id)
    return load.account_id if load is not None else None


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


# AI-CONTEXT: the live-stop set, named once so it cannot drift (F3-1).
# `complete_load_if_finished` below asks the same question of one load's stops; F3's arming
# reconcile asks it of a facility. Two literals would eventually disagree about whether an
# `arrived` stop is still live, and the answer decides whether a geofence keeps minting
# arrivals a driver's next load can inherit.
LIVE_STOP_STATUSES = (StopStatus.pending, StopStatus.armed, StopStatus.arrived)


def has_live_stop_at(db: Session, account_id, facility_id) -> bool:
    """Does this account still have a stop under way at this facility?

    Supplied to `location.reconcile_armings` as its predicate — F3 may not read F5's
    internals (import-linter's f05-internals-are-private contract), and a location
    component that knew what a stop was would be this module leaking downwards.
    """
    return (
        db.scalar(
            select(Stop.id)
            .join(Load, Load.id == Stop.load_id)
            .where(
                Load.account_id == account_id,
                Stop.facility_id == facility_id,
                Stop.status.in_(LIVE_STOP_STATUSES),
                Load.status != LoadStatus.canceled,
            )
            .limit(1)
        )
        is not None
    )


def complete_load_if_finished(db: Session, load: Load) -> Load:
    """Mark a load completed once no stop is still live.

    `LoadStatus` has carried draft/active/completed/canceled since F5 was written and
    `set_load_status` was never called from anywhere — so every load ever created is
    still `draft`. Ending a load departed the STOP and left the load untouched, which
    is why "completed" could not be listed even by something that wanted to.
    """
    if any(s.status in LIVE_STOP_STATUSES for s in load.stops):
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

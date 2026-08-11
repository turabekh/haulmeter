from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import cos, hypot, radians

from geoalchemy2 import Geography
from geoalchemy2.elements import WKTElement
from sqlalchemy import cast, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.foundation.f02_facility import public as facility_registry

from .enums import GeofenceEventType, LocationMode
from .models import (
    EvaluationCursor,
    FacilityGeofence,
    GeofenceArming,
    GeofenceEvent,
    GeofencePresence,
    LocationPing,
)

DEFAULT_RADIUS_M = 150.0
DWELL_TICK_INTERVAL = timedelta(minutes=15)
GPS_DIVERGENCE_THRESHOLD = timedelta(seconds=30)


class FacilityNotFound(Exception):
    pass


def _point(lat: float, lon: float) -> WKTElement:
    return WKTElement(f"POINT({lon} {lat})", srid=4326)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def facility_radius(db: Session, facility_id) -> float:
    config = db.get(FacilityGeofence, facility_id)
    return config.radius_m if config is not None else DEFAULT_RADIUS_M


def arm_geofence(
    db: Session, account_id, facility_id, radius_m: float | None = None
) -> GeofenceArming:
    """Get-or-create. One active arming per (account, facility) (F3-1).

    AI-CONTEXT: this wrote a NEW ROW on every call and nothing ever collapsed them, so an
    account accumulated an arming per stop for the life of the account. Two costs, and the
    second is the one that touches money:

      · `evaluate_ping` loops every active arming and does a facility fetch plus a PostGIS
        containment test per arming, so per-ping work grew with a driver's career;
      · an arming that outlives its stop keeps minting real presence and event rows. A
        drive-by within 150 m of a dock the driver delivered to last month creates an
        ENTER, and `visit_window` can hand that arrival to the NEXT load as the moment its
        detention clock started.

    NO UNIQUE INDEX BACKS THIS, which is a deliberate and unusual choice — see migration
    0068's note. Duplicate armings are what every existing box already contains, so a
    constraint plus a refusing preflight would be undeployable by construction. The
    consequence is an accepted race: two concurrent `arm_geofence` calls can still both
    miss and both insert. It is harmless by construction rather than by luck — presence is
    uniquely constrained, so a duplicate arming produces at most one visit, and
    `reconcile_armings` collapses the pair on the next nightly run.
    """
    if facility_registry.get_facility(db, facility_id) is None:
        raise FacilityNotFound(str(facility_id))
    if db.get(FacilityGeofence, facility_id) is None:
        db.add(FacilityGeofence(facility_id=facility_id, radius_m=DEFAULT_RADIUS_M))
        db.flush()
    existing = db.scalar(
        select(GeofenceArming)
        .where(
            GeofenceArming.account_id == account_id,
            GeofenceArming.facility_id == facility_id,
            GeofenceArming.disarmed_at.is_(None),
        )
        .order_by(GeofenceArming.armed_at, GeofenceArming.id)
        .limit(1)
    )
    if existing is not None:
        # a caller re-arming with a radius means it: the stop's fence may have been
        # widened since. Silence (None) leaves whatever is on the row alone.
        if radius_m is not None:
            existing.radius_m = radius_m
            db.flush()
        return existing
    arming = GeofenceArming(account_id=account_id, facility_id=facility_id, radius_m=radius_m)
    db.add(arming)
    db.flush()
    return arming


# AI-CONTEXT: what keeps a fence armed is F5's question, not F3's (F3-1).
#
# The predicate is INJECTED rather than imported, and import-linter is why: F3 sits below
# F5 in the spine and may not read its internals — the first draft of this reached into
# `f05_load.domain.models` and the contract caught it, correctly. A location component that
# knew what a "stop" was would be F5 leaking downwards.
#
# So F3 owns the mechanism (which armings to disarm, and never to delete them) and the
# caller owns the meaning (`f05.has_live_stop_at`). The default — no predicate — collapses
# duplicates and disarms nothing, which is the honest behaviour for a caller that cannot
# say what "live" means.
def reconcile_armings(
    db: Session, has_live_stop=None, account_id=None, now: datetime | None = None
) -> dict:
    """Disarm what no longer has a stop, and collapse duplicates. Idempotent.

    AI-CONTEXT: the janitor for F3-1. Two jobs:

      (i)  an active arming whose account has no live stop at that facility is DISARMED —
           the stop it was created for is over, so the fence should not still be minting
           arrivals. `has_live_stop(db, account_id, facility_id) -> bool` is supplied by
           the caller (F5 owns the lifecycle); without one, nothing is orphaned;
      (ii) duplicate actives for one (account, facility) collapse to the EARLIEST, which is
           the one `arm_geofence`'s get-or-create would have returned.

    It NEVER DELETES. `disarmed_at` is set and the row stays: an arming is part of the
    record of why a presence exists, and a claim being argued next year may need it.

    `account_id=None` means the whole box, which is how the nightly runner calls it.
    """
    now = now or datetime.now(UTC)
    stmt = select(GeofenceArming).where(GeofenceArming.disarmed_at.is_(None))
    if account_id is not None:
        stmt = stmt.where(GeofenceArming.account_id == account_id)
    armings = list(db.scalars(stmt.order_by(GeofenceArming.armed_at, GeofenceArming.id)))

    orphaned = collapsed = 0
    kept: set[tuple] = set()
    for arming in armings:
        key = (arming.account_id, arming.facility_id)
        if key in kept:
            arming.disarmed_at = now  # a duplicate of one we already kept
            collapsed += 1
            continue
        if has_live_stop is not None and not has_live_stop(
            db, arming.account_id, arming.facility_id
        ):
            arming.disarmed_at = now
            orphaned += 1
            continue
        kept.add(key)
    db.flush()
    return {"scanned": len(armings), "orphaned": orphaned, "collapsed": collapsed}


def _active_armings(db: Session, account_id) -> list[GeofenceArming]:
    return list(
        db.scalars(
            select(GeofenceArming).where(
                GeofenceArming.account_id == account_id,
                GeofenceArming.disarmed_at.is_(None),
            )
        )
    )


def _active_presence(db: Session, account_id, facility_id) -> GeofencePresence | None:
    return db.scalar(
        select(GeofencePresence).where(
            GeofencePresence.account_id == account_id,
            GeofencePresence.facility_id == facility_id,
            GeofencePresence.active.is_(True),
        )
    )


def visit_window(
    db: Session, account_id, facility_id, since: datetime
) -> tuple[datetime | None, datetime | None]:
    """ONE visit to a facility: when the truck arrived and when it left (§23 entry 73).

    AI-CONTEXT: F3 has always recorded visits as `GeofencePresence` rows — one per
    arrival, closed on exit — and nothing outside F3 could read them, so M3 rebuilt
    the notion of "this visit" by replaying raw ENTER/EXIT events and took the
    EARLIEST enter and the LATEST exit ever recorded at that facility. A driver's
    second load to the same dock therefore billed from their first visit. This
    returns the visit belonging to `since`: the session still open at that moment
    (the driver was already inside) or, failing that, the next one to begin. Sessions
    that had already closed before `since` belong to an earlier load and are skipped.
    """
    # AI-CONTEXT: audit F-15 — this walked EVERY visit the driver had ever made to the
    # dock to answer a question about one of them, skipping the closed ones in Python.
    # The skip is now the WHERE clause and the loop is a LIMIT 1: same selection rule
    # (a session still open at `since`, else the next one to begin), asked of the index.
    floor = _as_utc(since)
    session = db.scalar(
        select(GeofencePresence)
        .where(
            GeofencePresence.account_id == account_id,
            GeofencePresence.facility_id == facility_id,
            or_(
                GeofencePresence.exited_at.is_(None),
                GeofencePresence.exited_at > floor,
            ),
        )
        .order_by(GeofencePresence.entered_at)
        .limit(1)
    )
    if session is None:
        return None, None
    exited = _as_utc(session.exited_at) if session.exited_at is not None else None
    return _as_utc(session.entered_at), exited


def _emit(db, account_id, facility_id, event_type, occurred_at, lat, lon) -> GeofenceEvent:
    event = GeofenceEvent(
        account_id=account_id,
        facility_id=facility_id,
        event_type=event_type,
        occurred_at=occurred_at,
        geom=_point(lat, lon),
    )
    db.add(event)
    db.flush()
    return event


def _increment_confirmed_arrivals(db: Session, facility_id) -> None:
    # AI-CONTEXT: an atomic UPDATE, not a read-modify-write. Two drivers arriving at one
    # dock in the same instant both read the old count and both wrote old+1, so the
    # facility's arrival count drifted DOWN over exactly the busy docks it is meant to
    # describe. The database can add one without being told what the value was.
    db.execute(
        update(FacilityGeofence)
        .where(FacilityGeofence.facility_id == facility_id)
        .values(confirmed_arrivals=FacilityGeofence.confirmed_arrivals + 1)
    )
    db.flush()


# AI-CONTEXT: where a driver most recently was, IF that is still worth believing.
#
# `not_older_than` is not optional politeness — it is the whole point. A ping from
# three days ago is a place the driver has long left, and a caller that targeted an
# interruption on it would be confidently wrong. Past the bound this returns None and
# the caller is expected to stay quiet rather than guess (§11.7).
#
# Driver position lives in F3, so consumers ask here instead of querying pings
# themselves — the same reason facility geometry is only reachable through F2.
def last_known_position(db: Session, account_id, not_older_than: timedelta, now=None):
    now = now or datetime.now(UTC)
    ping = db.scalar(
        select(LocationPing)
        .where(
            LocationPing.account_id == account_id,
            LocationPing.occurred_at >= now - not_older_than,
        )
        .order_by(LocationPing.occurred_at.desc())
        .limit(1)
    )
    if ping is None:
        return None
    lon, lat = db.execute(
        select(func.ST_X(LocationPing.geom), func.ST_Y(LocationPing.geom)).where(
            LocationPing.id == ping.id
        )
    ).one()
    return (lat, lon)


def record_ping(
    db: Session,
    account_id,
    lat: float,
    lon: float,
    occurred_at: datetime,
    client_skew_ms: int | None = None,
    gps_time: datetime | None = None,
    accuracy_m: float | None = None,
    speed_mps: float | None = None,
    mode: LocationMode = LocationMode.significant_change,
) -> LocationPing:
    divergent = False
    if gps_time is not None:
        if abs(_as_utc(gps_time) - _as_utc(occurred_at)) > GPS_DIVERGENCE_THRESHOLD:
            divergent = True
    ping = LocationPing(
        account_id=account_id,
        geom=_point(lat, lon),
        occurred_at=occurred_at,
        client_skew_ms=client_skew_ms,
        gps_time=gps_time,
        gps_time_divergent=divergent,
        accuracy_m=accuracy_m,
        speed_mps=speed_mps,
        mode=mode,
    )
    db.add(ping)
    db.flush()
    return ping


# AI-CONTEXT: the two knobs that make the state machine tolerant of a real phone (F3-4).
#
# BOTH SHIP INERT. `exit_confirm_pings = 1` is exactly today's single-ping exit and
# `accuracy_gate_m = 0` is off, so with defaults every existing behaviour test passes
# unmodified — which is asserted directly, not hoped for. Turning either one MOVES MONEY
# TIMING: a later EXIT is a longer detention clock. That makes the numbers an owner's
# decision, and this session deliberately does not make it. §23 entries 73, 93 and 107 are
# all the same story of something adjacent to the clock being changed and the money going
# wrong; the retention knob's "0 means off" discipline is the template followed here.
#
# WHY THEY EXIST AT ALL. `accuracy_m` has been recorded on every ping since F3 was written
# and read by nothing, and a single bad fix outside the radius closed the visit on the
# spot — the clock stopped early and the driver was undercounted, with no debounce and no
# gate. The mechanism is the hard part and it is now built and tested; choosing thresholds
# needs a real accuracy distribution from real handsets, which this fleet does not yet have.
CONFIG_EXIT_CONFIRM_PINGS = "f03.exit_confirm_pings"
DEFAULT_EXIT_CONFIRM_PINGS = 1
CONFIG_ACCURACY_GATE_M = "f03.accuracy_gate_m"
DEFAULT_ACCURACY_GATE_M = 0


def _exit_confirm_pings(db: Session) -> int:
    from app.foundation.f13_flags import public as flags

    # below 1 would mean "never exit", which is a visit that never ends and a clock that
    # never stops — the one setting that must not be reachable by typing 0
    return max(1, int(flags.get_config(db, CONFIG_EXIT_CONFIRM_PINGS, DEFAULT_EXIT_CONFIRM_PINGS)))


def _accuracy_gate_m(db: Session) -> float:
    from app.foundation.f13_flags import public as flags

    return float(flags.get_config(db, CONFIG_ACCURACY_GATE_M, DEFAULT_ACCURACY_GATE_M))


# AI-CONTEXT: how far this account's evaluated time has reached (F3-3).
#
# `FUTURE_TOLERANCE` is a constant rather than a knob on purpose: it is not a policy about
# money, it is the width of ordinary clock skew on a handset. Five minutes forgives a phone
# whose clock drifted; it does not forgive a phone that thinks it is 2031.
FUTURE_TOLERANCE = timedelta(minutes=5)

SKIP_STALE_ORDER = "stale_order"
SKIP_FUTURE = "future"
SKIP_LOW_ACCURACY = "low_accuracy"


@dataclass
class PingResult:
    """What `evaluate_ping` did — which is not always "evaluated it".

    AI-CONTEXT: this returned a bare list of events, so "no events" meant both "nothing
    happened" and "we refused to look", and no caller could tell them apart. The ingestion
    route now reports which, because a client flushing an offline queue deserves to know
    its pings were recorded and skipped rather than silently ignored.
    """

    events: list
    evaluated: bool = True
    skipped_reason: str | None = None

    # AI-CONTEXT: iterable over its own events, so this stayed a PURE ADDITION. Every
    # caller and every test that treated the return as a list still does, which is what
    # makes "the pre-existing suite passes UNMODIFIED" a real proof that the state machine
    # is unchanged rather than a claim about tests that were edited to agree with it.
    def __iter__(self):
        return iter(self.events)

    def __len__(self):
        return len(self.events)

    def __getitem__(self, index):
        return self.events[index]



def _lock_cursor(db: Session, account_id) -> EvaluationCursor:
    """The account's evaluation cursor, locked for the rest of this transaction.

    AI-CONTEXT: this is the mechanism that makes per-account evaluation SERIAL, and it is
    what actually kills F3-2's duplicate-presence race — the unique index catches the case
    the lock cannot cover (no row yet, two connections), but a caught IntegrityError is a
    recovery, not a design. Ordinary concurrency should never reach it.

    Created on first use. The insert races with itself for a brand-new account, which is
    why the `IntegrityError` path re-reads rather than assuming it won.
    """
    cursor = db.scalar(
        select(EvaluationCursor)
        .where(EvaluationCursor.account_id == account_id)
        .with_for_update()
    )
    if cursor is not None:
        return cursor
    cursor = EvaluationCursor(
        account_id=account_id, last_evaluated_at=datetime.min.replace(tzinfo=UTC)
    )
    try:
        with db.begin_nested():
            db.add(cursor)
            db.flush()
    except IntegrityError:
        if cursor in db:
            db.expunge(cursor)
        cursor = db.scalar(
            select(EvaluationCursor)
            .where(EvaluationCursor.account_id == account_id)
            .with_for_update()
        )
    return cursor


def evaluate_ping(
    db: Session,
    account_id,
    lat: float,
    lon: float,
    occurred_at: datetime,
    client_skew_ms: int | None = None,
    gps_time: datetime | None = None,
    accuracy_m: float | None = None,
    speed_mps: float | None = None,
    mode: LocationMode = LocationMode.significant_change,
    now: datetime | None = None,
) -> PingResult:
    """Record the ping, then apply it to the geofence state machine — if it may be applied.

    AI-CONTEXT: THE TRAIL IS RECORDED EITHER WAY. A ping we refuse to evaluate is still
    where the driver was, and dropping it would make the map and the retention window lie
    about the same journey the state machine declined to reason about. Only the state
    machine is skipped.

    Three refusals, in order:

      · out of ORDER (F3-3). The offline outbox exists precisely to deliver pings late, and
        the machine applied every one to CURRENT state at the ping's own timestamp — so a
        late inside-ping arriving after its visit's EXIT re-opened a presence that never
        closes, and a late outside-ping after an ENTER closed the visit at a moment before
        it began. Both put a wrong `entered_at`/`exited_at` under a detention claim.
      · from the FUTURE. Trail-recorded, not evaluated, and deliberately does NOT advance
        the cursor: a device that thinks it is next year would otherwise set the mark ahead
        and silently discard every real ping that followed.
      · too INACCURATE, when the gate is on. Off by default — see `CONFIG_ACCURACY_GATE_M`.
    """
    now = _as_utc(now or datetime.now(UTC))
    occurred = _as_utc(occurred_at)
    record_ping(
        db, account_id, lat, lon, occurred_at, client_skew_ms, gps_time, accuracy_m, speed_mps, mode
    )

    if occurred > now + FUTURE_TOLERANCE:
        return PingResult([], evaluated=False, skipped_reason=SKIP_FUTURE)

    gate = _accuracy_gate_m(db)
    if gate > 0 and accuracy_m is not None and accuracy_m > gate:
        return PingResult([], evaluated=False, skipped_reason=SKIP_LOW_ACCURACY)

    cursor = _lock_cursor(db, account_id)
    if occurred <= _as_utc(cursor.last_evaluated_at):
        return PingResult([], evaluated=False, skipped_reason=SKIP_STALE_ORDER)

    events = _apply_to_state(db, account_id, lat, lon, occurred_at)
    cursor.last_evaluated_at = occurred
    db.flush()
    return PingResult(events)


def _apply_to_state(db: Session, account_id, lat: float, lon: float, occurred_at: datetime) -> list:
    confirm = _exit_confirm_pings(db)
    events: list[GeofenceEvent] = []
    for arming in _active_armings(db, account_id):
        facility = facility_registry.get_facility(db, arming.facility_id)
        if facility is None:
            continue
        radius = arming.radius_m or facility_radius(db, arming.facility_id)
        inside = facility_registry.contains_point(db, facility, lat, lon, radius)
        presence = _active_presence(db, account_id, arming.facility_id)

        if inside and presence is None:
            presence = _open_presence(db, account_id, arming.facility_id, occurred_at)
            if presence is None:
                continue  # a concurrent ENTER won; its session is the visit
            events.append(
                _emit(
                    db,
                    account_id,
                    arming.facility_id,
                    GeofenceEventType.ENTER,
                    occurred_at,
                    lat,
                    lon,
                )
            )
            _increment_confirmed_arrivals(db, arming.facility_id)
        elif inside and presence is not None:
            presence.outside_streak = 0  # a fix inside ends any run of outside ones
            if _as_utc(occurred_at) - _as_utc(presence.last_tick_at) >= DWELL_TICK_INTERVAL:
                presence.last_tick_at = occurred_at
                db.flush()
                events.append(
                    _emit(
                        db,
                        account_id,
                        arming.facility_id,
                        GeofenceEventType.DWELL_TICK,
                        occurred_at,
                        lat,
                        lon,
                    )
                )
            else:
                db.flush()
        elif not inside and presence is not None:
            presence.outside_streak += 1
            if presence.outside_streak < confirm:
                # not yet confirmed: no event, the visit stays open, and `last_tick_at` is
                # deliberately untouched so a bad fix cannot masquerade as a dwell tick
                db.flush()
                continue
            presence.active = False
            presence.exited_at = occurred_at
            db.flush()
            events.append(
                _emit(
                    db,
                    account_id,
                    arming.facility_id,
                    GeofenceEventType.EXIT,
                    occurred_at,
                    lat,
                    lon,
                )
            )
    return events


def _open_presence(db: Session, account_id, facility_id, occurred_at) -> GeofencePresence | None:
    """Open a visit, or return None if a concurrent evaluation already opened it.

    AI-CONTEXT: the cursor lock should make this unreachable — it serialises evaluation per
    account — so this is the backstop for the one case a lock cannot cover: two connections
    for an account whose cursor row does not exist yet. `uq_geofence_presence_active` is
    what turns that into a caught error instead of a second open session whose stale
    `entered_at` a later load inherits.
    """
    presence = GeofencePresence(
        account_id=account_id,
        facility_id=facility_id,
        entered_at=occurred_at,
        last_tick_at=occurred_at,
        active=True,
    )
    try:
        with db.begin_nested():
            db.add(presence)
            db.flush()
    except IntegrityError:
        # the SAVEPOINT rollback has already detached it; expunging again raises. Guarded
        # rather than assumed, because the same shape in m03 leaves the object attached and
        # the difference is not visible from the call site.
        if presence in db:
            db.expunge(presence)
        return None
    return presence


def disarm_geofence(db: Session, account_id, facility_id, occurred_at: datetime | None = None):
    when = occurred_at or datetime.now(UTC)
    for arming in db.scalars(
        select(GeofenceArming).where(
            GeofenceArming.account_id == account_id,
            GeofenceArming.facility_id == facility_id,
            GeofenceArming.disarmed_at.is_(None),
        )
    ):
        arming.disarmed_at = when
    presence = _active_presence(db, account_id, facility_id)
    if presence is not None:
        presence.active = False
        presence.exited_at = when
    db.flush()


def is_present(db: Session, account_id, facility_id) -> bool:
    return _active_presence(db, account_id, facility_id) is not None


def is_present_anywhere(db: Session, account_id) -> bool:
    """Is this account inside ANY armed geofence right now (§5's ON_SITE input).

    AI-CONTEXT: the steady state, as opposed to the ENTER/EXIT edges `evaluate_ping`
    returns. F3 has recorded it as a row since the Foundation and never answered the
    question, so the client could only ever learn presence by catching an edge as it
    happened — which made design-prd §5's ON_SITE unreachable in normal use. A driver
    who reloaded the tab, or who arrived by tapping "I've arrived" instead of tripping
    the geofence, was ON_SITE nowhere but in the database, and every ON_SITE behaviour
    in the product stayed dark. An edge is a fact about a moment; a state has to be
    askable at any moment, including the first render after a cold start.
    """
    return (
        db.scalar(
            select(GeofencePresence).where(
                GeofencePresence.account_id == account_id,
                GeofencePresence.active.is_(True),
            )
        )
        is not None
    )


def dwell_samples(db: Session, facility_id) -> list[dict]:
    # AI-CONTEXT: pair ENTER->EXIT per account at a facility into dwell samples
    # (seconds + arrival hour). The objective, evidence-grade dwell data M2/M8
    # build stats on. Ordered per account by time; an ENTER without a following
    # EXIT is an open stop and is skipped.
    events = db.scalars(
        select(GeofenceEvent)
        .where(GeofenceEvent.facility_id == facility_id)
        .order_by(GeofenceEvent.account_id, GeofenceEvent.occurred_at)
    )
    samples: list[dict] = []
    open_enter: dict = {}
    for event in events:
        if event.event_type == GeofenceEventType.ENTER:
            open_enter[event.account_id] = event.occurred_at
        elif event.event_type == GeofenceEventType.EXIT:
            entered = open_enter.pop(event.account_id, None)
            if entered is not None:
                seconds = (_as_utc(event.occurred_at) - _as_utc(entered)).total_seconds()
                if seconds >= 0:
                    samples.append(
                        {
                            "enter_at": entered,
                            "exit_at": event.occurred_at,
                            "seconds": seconds,
                            "arrival_hour": _as_utc(entered).hour,
                        }
                    )
    return samples


def list_events(db: Session, account_id, facility_id=None) -> list[GeofenceEvent]:
    stmt = select(GeofenceEvent).where(GeofenceEvent.account_id == account_id)
    if facility_id is not None:
        stmt = stmt.where(GeofenceEvent.facility_id == facility_id)
    return list(db.scalars(stmt.order_by(GeofenceEvent.occurred_at)))


# AI-CONTEXT: `build_trace` WAS HERE, and it is gone deliberately (finding F3-6).
#
# WHAT IT WAS. `build_trace(db, account_id, since, until) -> str | None` returned a
# PostGIS `ST_MakeLine` over the account's raw `location_ping` rows in a window, as WKT,
# or None below two points. It was exported from `public.py`, covered by two tests, and
# called by NOTHING in the tree for the whole life of the project — the ping-retention
# comment below says so itself, and relied on it.
#
# WHY IT WENT rather than being wired into the evidence pack, which was the alternative
# considered. `render.py` CAN draw a polyline — `_trace` already does, from
# `_located_points` — so the obstacle was never rendering machinery. The obstacle is that
# file's governing rule, stated in its own docstring:
#
#     "The trace is drawn from EVIDENCE, not from raw location pings. Every plotted point
#      is a hash-chained record or a geotagged artifact, so the map cannot show a position
#      the verification block does not cover."
#
# A `location_ping` is neither hash-chained nor permanent — it is purged on the retention
# window declared immediately below. Wiring this in would have plotted positions the
# verification block cannot vouch for, and made a claim's pack render DIFFERENTLY before
# and after a purge, which is exactly the property the retention wiring was justified by.
#
# WHAT IT WOULD TAKE TO BRING IT BACK: make the points evidence first — append the visit's
# pings to the stop's F4 chain as located records at pack time, so `_located_points` picks
# them up through the existing path and the verification block covers them. That is
# evidence machinery, not location machinery, and it belongs to the F4 session that owns
# device-truth. Until then, an unwired path-from-raw-pings is an inert engine, and this
# codebase has removed four of those for the same reason: a deferral that cannot fail is
# indistinguishable from a finished feature.


def purge_pings_older_than(db: Session, cutoff: datetime) -> int:
    result = db.execute(delete(LocationPing).where(LocationPing.received_at < cutoff))
    db.flush()
    return result.rowcount


# AI-CONTEXT: audit F-09 — `purge_pings_older_than` existed, was exported, and its only
# caller in the entire tree was one test. PRD §7.3 specifies "PostGIS storage of traces
# … with configurable retention"; the retention was configurable in the sense that
# nothing enforced it. F3 is the sensory system under the whole evidence engine, so
# `location_ping` is also the fastest-growing table the product has.
#
# The NUMBER is a policy decision, not an engineering one, so it is a declared F13 key
# rather than a constant — visible in /admin/config before anybody needs it (session
# 112's finding).
#
# WHAT A PURGE HERE CANNOT BREAK, checked before wiring it rather than assumed: the F4
# evidence pack does NOT read this table. `render.py` states the rule and the reason —
# "the trace is drawn from EVIDENCE, not from raw location pings … the map cannot show
# a position the verification block does not cover" — so every plotted point is a
# hash-chained record. The one function that DOES read raw pings, `build_trace`, has no
# caller anywhere outside its own test. So deleting an old ping destroys no claim's
# evidence, and this is a privacy-and-growth control, not an evidence-retention one.
#
# 365 days is therefore conservative by DEFAULT-CHOOSING, not by necessity: nobody has
# decided the number, a long window is the safe direction for a first wiring, and it
# still bounds a table growing at ~700–1,300 rows per driver per DRIVING DAY. Shortening
# it is cheap and safe; the paragraph above is what makes that sentence checkable.
#
# ZERO OR LESS MEANS NEVER PURGE, and that is the safety property that matters most
# here: this is the one job in the worker that destroys data, and the plausible operator
# accident is typing 0 into a retention box meaning "off". Read as a cutoff, 0 would
# delete the entire table.
CONFIG_PING_RETENTION_DAYS = "f03.ping_retention_days"
DEFAULT_PING_RETENTION_DAYS = 365


def register_location_retention(db: Session) -> None:
    from app.foundation.f13_flags import public as flags

    flags.register_config(
        db,
        CONFIG_EXIT_CONFIRM_PINGS,
        DEFAULT_EXIT_CONFIRM_PINGS,
        description=(
            "Consecutive pings outside a geofence before EXIT fires and the detention "
            "clock stops. 1 is today's behaviour: one stray fix ends the visit. Raising it "
            "ignores a bad GPS reading but DELAYS every exit, lengthening detention "
            "claims — an owner decision. Below 1 reads as 1."
        ),
        scope="location",
    )
    flags.register_config(
        db,
        CONFIG_ACCURACY_GATE_M,
        DEFAULT_ACCURACY_GATE_M,
        description=(
            "Ignore pings whose reported accuracy is worse than this many metres when "
            "deciding presence. 0 disables the gate — today's behaviour, every ping "
            "trusted however vague. Pings reporting no accuracy are never gated. Set too "
            "low, a truck in a canyon stops being tracked: an owner decision."
        ),
        scope="location",
    )
    flags.register_config(
        db,
        CONFIG_PING_RETENTION_DAYS,
        DEFAULT_PING_RETENTION_DAYS,
        description=(
            "Days of raw GPS pings to keep before the nightly purge deletes them. "
            "0 or less disables the purge entirely. Safe to shorten: the F4 evidence "
            "pack is built from hash-chained evidence records, not from this table, "
            "so a purge here cannot remove a claim's proof."
        ),
        scope="location",
    )


def purge_expired_pings(db: Session, now: datetime | None = None) -> dict:
    from app.foundation.f13_flags import public as flags

    now = now or datetime.now(UTC)
    days = int(flags.get_config(db, CONFIG_PING_RETENTION_DAYS, DEFAULT_PING_RETENTION_DAYS))
    if days <= 0:
        return {"deleted": 0, "retention_days": days, "purged": False}
    deleted = purge_pings_older_than(db, now - timedelta(days=days))
    return {"deleted": deleted, "retention_days": days, "purged": True}


# --- Stationary detection, read-only (§23 entry 112, shape (c)) ---
#
# AI-CONTEXT: this exists because the geofence could NOT answer the question. Events
# fire only for facilities with an active ARMING, and `arm_geofence` has one caller in
# the tree — `f05_load.arm_stop` — so a driver parked at a truck stop for the night is
# invisible to `evaluate_ping`. Auto-arming would have fixed it and was rejected
# (owner decision): armings write presence and event rows that M3's money reads, and
# §23 entries 73, 93 and 107 are all the same story of something adjacent to the clock
# being changed and the money going wrong.
#
# So this reads the ping trail and writes NOTHING. No arming, no presence, no event.
# It cannot affect a detention claim even if it is completely wrong, which is the whole
# reason it is shaped this way.
STATIONARY_RADIUS_M = 150.0
STATIONARY_WINDOW = timedelta(hours=2)


def stationary_since(
    db: Session,
    account_id,
    now: datetime,
    radius_m: float = STATIONARY_RADIUS_M,
    window: timedelta = STATIONARY_WINDOW,
) -> datetime | None:
    """When the driver's current stay began, or None if they are not staying.

    Walks BACKWARDS from the newest ping while each older one is still within
    `radius_m` of it, and returns the oldest ping in that unbroken run. The first ping
    outside the radius ends the stay — a driver who left and came back gets the second
    visit, not the union of both, which is the same scoping mistake §23 entry 73 made
    with geofence events and billed a driver $187.76 for it.

    ONE query regardless of how many pings there are: the anchor is a scalar subquery,
    so PostGIS flags the whole window against it server-side. Comparing them row by row
    would be a per-ping round trip — the shape §23 entry 98 spent a session removing
    from the map — and computing the distance in Python would grow a second geometry
    implementation beside F2's, which `facility_distances` explicitly warns against.
    Bounded by `window`, and the 250 m / 5 min client throttle (§23 entry 93) keeps that
    a handful of rows.

    The anchor stays IN SQL deliberately. Fetching it first and passing the value back
    in casts a WKB element to text and PostGIS rejects it — "parse error - invalid
    geometry" — which is the kind of failure that reads like a data problem and is
    actually a round trip that should never have happened.
    """
    anchor = (
        select(LocationPing.geom)
        .where(LocationPing.account_id == account_id, LocationPing.occurred_at <= now)
        .order_by(LocationPing.occurred_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    rows = db.execute(
        select(
            LocationPing.occurred_at,
            func.ST_DWithin(
                cast(LocationPing.geom, Geography), cast(anchor, Geography), radius_m
            ),
        )
        .where(
            LocationPing.account_id == account_id,
            LocationPing.occurred_at >= now - window,
            LocationPing.occurred_at <= now,
        )
        .order_by(LocationPing.occurred_at.desc())
    ).all()
    if not rows:
        return None
    since = None
    for occurred_at, near in rows:
        if not near:
            break
        since = occurred_at
    return since


# --- Location basis, read-only (D6) ---
#
# AI-CONTEXT: what the GPS data IS, so a document can stop implying what it is not.
#
# Counterparty copy said "GPS-verified" and nothing in the product gated accuracy, flagged
# a mock provider, or surfaced `gps_time_divergent`. The chain proves a reading has not
# been altered SINCE it was recorded; it proves nothing about how the reading was produced.
# This is the honest middle: state the shape of the trail — how many fixes, how precise
# they claimed to be, how many disagreed with their own device clock, how many implied a
# speed no truck reaches — and let the reader judge.
#
# SHAPE (c), like `stationary_since`: it reads and writes NOTHING. No arming, no presence,
# no event. It cannot affect a detention claim even if every number in it is wrong, which
# is the whole reason it is allowed to run at pack time.
#
# THE CONSTANTS ARE ANNOTATE-ONLY, and that is why they are constants rather than F13 keys.
# The two knobs this module gained last session (`exit_confirm_pings`, `accuracy_gate_m`)
# GATE A CLOCK — move them and detention timing moves, so they are the owner's. These only
# LABEL A REPORT: change `IMPLAUSIBLE_SPEED_MPS` and a line in a PDF reads differently and
# not one cent moves. An owner knob implies a decision worth making; this is a threshold
# for a footnote.
#
# 60 m/s is ~134 mph — comfortably above any truck, and above the highway speeds a normal
# fix pair produces, so it flags teleports rather than lead feet. The dt floor exists
# because two fixes 200 ms apart with 30 m of GPS jitter imply 150 m/s and mean nothing:
# below it there is no speed worth computing, only noise.
IMPLAUSIBLE_SPEED_MPS = 60.0
IMPLAUSIBLE_MIN_DT_SECONDS = 5.0


def location_basis(db: Session, account_id, since: datetime, until: datetime) -> dict:
    """What the location trail for this window actually consists of.

    `pings` of 0 means the trail is absent — purged past the retention window, or never
    recorded — and every other figure is None. A caller must render that as absence and
    assert nothing, never as zero problems.
    """
    rows = db.execute(
        select(
            LocationPing.occurred_at,
            LocationPing.accuracy_m,
            LocationPing.gps_time_divergent,
            func.ST_Y(LocationPing.geom),
            func.ST_X(LocationPing.geom),
        )
        .where(
            LocationPing.account_id == account_id,
            LocationPing.occurred_at >= _as_utc(since),
            LocationPing.occurred_at <= _as_utc(until),
        )
        .order_by(LocationPing.occurred_at)
    ).all()

    if not rows:
        return {
            "pings": 0,
            "accuracy_min_m": None,
            "accuracy_median_m": None,
            "accuracy_max_m": None,
            "accuracy_reported": 0,
            "divergent_clock_pings": 0,
            "implausible_moves": 0,
        }

    accuracies = sorted(r[1] for r in rows if r[1] is not None)
    median = None
    if accuracies:
        mid = len(accuracies) // 2
        median = (
            accuracies[mid]
            if len(accuracies) % 2
            else (accuracies[mid - 1] + accuracies[mid]) / 2
        )

    implausible = 0
    for (t0, _a0, _d0, lat0, lon0), (t1, _a1, _d1, lat1, lon1) in zip(rows, rows[1:], strict=False):
        dt = (_as_utc(t1) - _as_utc(t0)).total_seconds()
        if dt < IMPLAUSIBLE_MIN_DT_SECONDS:
            continue
        # equirectangular metres — enough for "is this a teleport", and deliberately not a
        # second geometry implementation beside F2's (`facility_distances` warns about it)
        mean_lat = radians((lat0 + lat1) / 2)
        dx = radians(lon1 - lon0) * 6371000 * cos(mean_lat)
        dy = radians(lat1 - lat0) * 6371000
        if hypot(dx, dy) / dt > IMPLAUSIBLE_SPEED_MPS:
            implausible += 1

    return {
        "pings": len(rows),
        "accuracy_min_m": accuracies[0] if accuracies else None,
        "accuracy_median_m": median,
        "accuracy_max_m": accuracies[-1] if accuracies else None,
        "accuracy_reported": len(accuracies),
        "divergent_clock_pings": sum(1 for r in rows if r[2]),
        "implausible_moves": implausible,
    }

from datetime import UTC, datetime, timedelta

from geoalchemy2.elements import WKTElement
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.orm import Session

from app.foundation.f02_facility import public as facility_registry

from .enums import GeofenceEventType, LocationMode
from .models import (
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
    if facility_registry.get_facility(db, facility_id) is None:
        raise FacilityNotFound(str(facility_id))
    if db.get(FacilityGeofence, facility_id) is None:
        db.add(FacilityGeofence(facility_id=facility_id, radius_m=DEFAULT_RADIUS_M))
        db.flush()
    arming = GeofenceArming(account_id=account_id, facility_id=facility_id, radius_m=radius_m)
    db.add(arming)
    db.flush()
    return arming


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
    config = db.get(FacilityGeofence, facility_id)
    if config is not None:
        config.confirmed_arrivals += 1
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
) -> list[GeofenceEvent]:
    record_ping(
        db, account_id, lat, lon, occurred_at, client_skew_ms, gps_time, accuracy_m, speed_mps, mode
    )
    events: list[GeofenceEvent] = []
    for arming in _active_armings(db, account_id):
        facility = facility_registry.get_facility(db, arming.facility_id)
        if facility is None:
            continue
        radius = arming.radius_m or facility_radius(db, arming.facility_id)
        inside = facility_registry.contains_point(db, facility, lat, lon, radius)
        presence = _active_presence(db, account_id, arming.facility_id)

        if inside and presence is None:
            db.add(
                GeofencePresence(
                    account_id=account_id,
                    facility_id=arming.facility_id,
                    entered_at=occurred_at,
                    last_tick_at=occurred_at,
                    active=True,
                )
            )
            db.flush()
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
        elif not inside and presence is not None:
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


def build_trace(db: Session, account_id, since: datetime, until: datetime) -> str | None:
    count = db.scalar(
        select(func.count())
        .select_from(LocationPing)
        .where(
            LocationPing.account_id == account_id,
            LocationPing.occurred_at >= since,
            LocationPing.occurred_at <= until,
        )
    )
    if count is None or count < 2:
        return None
    return db.scalar(
        select(
            func.ST_AsText(
                func.ST_MakeLine(aggregate_order_by(LocationPing.geom, LocationPing.occurred_at))
            )
        ).where(
            LocationPing.account_id == account_id,
            LocationPing.occurred_at >= since,
            LocationPing.occurred_at <= until,
        )
    )


def purge_pings_older_than(db: Session, cutoff: datetime) -> int:
    result = db.execute(delete(LocationPing).where(LocationPing.received_at < cutoff))
    db.flush()
    return result.rowcount

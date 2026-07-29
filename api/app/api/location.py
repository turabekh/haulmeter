"""AI-CONTEXT: F3's inbound seam — the route that was missing.

F3 has been complete since the Foundation: `evaluate_ping` records a trace point and
emits ENTER / EXIT / DWELL_TICK against F2 geometries, and `record_ping` measures
client clock skew and flags GPS-time divergence. **Nothing ever called them from the
app.** In application code `evaluate_ping` had exactly one caller — `POST
/load/{stop}/arrive`, passing the FACILITY'S OWN coordinates, which by construction
can only ever produce an ENTER. Every other caller in the repo was a test or
`scripts/seed_demo.py`.

So geofence **EXIT could not fire in production**, and everything downstream of it was
dead without saying so: F3's dwell pairing walks ENTER→EXIT and skips an unclosed
ENTER, so M2's `dwell_stats` and `detention_risk` computed over an empty sample; M3's
`_arrival_departure` always returned `departure = None`. Measured before building —
across the whole dev database, every facility a driver had ever touched carried ENTER
and zero EXIT, and the only EXIT rows anywhere came from the demo seeder faking one.

Time integrity is PRD §7.3's: **server time is authoritative**, and the client's own
clock is recorded as skew rather than trusted. A ping that arrives claiming 10 minutes
ago is still evaluated as now — which is also why the client must never queue these
(see ui/src/core/location.js).
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_account, get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f05_load import public as loads
from app.foundation.f08_notifications import public as notify
from app.modules.m01_map import public as m1
from app.modules.m05_protection import public as m5

router = APIRouter(prefix="/location", tags=["location"])

_GATEWAY = notify.RecordingNotificationGateway()  # F8 seam (dev)


def _warn_of_unrecoverable_gaps(db, account, facility_id, now) -> None:
    """M5-FR5 at the moment the gap stops being fixable.

    Scoped to the stop the driver is actually working: an EXIT from a truck stop they
    happened to be armed at is not a delivery, and M5 only has something to say about
    the facility this stop belongs to.
    """
    stop = loads.active_stop_for_account(db, account.id)
    if stop is None or stop.facility_id != facility_id:
        return
    fac = facility.get_facility(db, facility_id)
    m5.notify_protection_gap(
        db,
        stop,
        account.id,
        gateway=_GATEWAY,
        now=now,
        facility_name=fac.name if fac else None,
    )


class GeocodeIn(BaseModel):
    address: str


def _ask_about_the_lot(db, account, lat, lon, now) -> None:
    """§23 entry 112 — the product's first question to a driver.

    Composed HERE for the same reason M5's EXIT carve-out is: a foundation must not
    reach up into a module to tell it something happened, and this router is already
    where a position ping meets the modules that care.

    §13.4's ban on interactive prompts at speed is satisfied by the TRIGGER rather than
    by a check somebody can forget: a driver who has not been within 150 m of one spot
    for fifteen minutes is not asked, and a driver who has is parked by definition.

    The gateway is resolved per account so a configured deployment pushes to the
    driver's own browsers (§23 entry 111); an unconfigured one records to the inbox.
    """
    m1.lot_status_prompt_due(db, account.id, lat, lon, notify.gateway_for(db, account.id), now)


@router.post("/geocode")
def geocode(
    body: GeocodeIn,
    _account: identity.Account = Depends(current_account),
) -> dict:
    """Turn an address into candidate coordinates, so the driver can confirm where a
    dock actually is (§23 entry 67).

    The import screen proposes a location from the parsed address; a driver who edits
    that address needs to re-ask, which is what this is for. An address we cannot place
    returns an empty list rather than an error — "we could not find this" is a fact to
    show, and losing a confirmed rate con to a 4xx would cost the driver the photograph.
    """
    places = facility.geocode(body.address)
    return {
        "places": [{"lat": p.lat, "lon": p.lon, "label": p.label} for p in places],
    }


class PingIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    # what the DEVICE thinks the time is. Never used as the event time — it is
    # subtracted from server time to record skew, per §7.3's time integrity rule.
    client_time: datetime | None = None
    # the fix's own timestamp, which can differ from the device clock. F3 flags the
    # divergence rather than silently preferring one.
    gps_time: datetime | None = None
    accuracy_m: float | None = None
    speed_mps: float | None = None
    # F3's adaptive sampling (PRD §7.3): significant-change by default, high-accuracy
    # while a stop is armed. The client says which mode produced the fix so the trace
    # records how it was taken.
    mode: str | None = None


@router.post("/ping", status_code=201)
def ping(
    body: PingIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    now = datetime.now(UTC)
    skew_ms = None
    if body.client_time is not None:
        client_time = body.client_time
        if client_time.tzinfo is None:
            client_time = client_time.replace(tzinfo=UTC)
        skew_ms = int((client_time - now).total_seconds() * 1000)
    try:
        mode = (
            location.LocationMode(body.mode)
            if body.mode
            else location.LocationMode.significant_change
        )
    except ValueError:
        # an unknown mode is not worth refusing a position over — the fix is still
        # true, and dropping it would lose an arrival to a typo
        mode = location.LocationMode.significant_change
    events = location.evaluate_ping(
        db,
        account.id,
        body.lat,
        body.lon,
        occurred_at=now,
        client_skew_ms=skew_ms,
        gps_time=body.gps_time,
        accuracy_m=body.accuracy_m,
        speed_mps=body.speed_mps,
        mode=mode,
    )
    # M5-FR5's EXIT carve-out. This is the composition point — the same shape as
    # `/load/{stop}/arrive`, which already joins F3, M3 and M5 — because a foundation
    # must not reach up into a module to tell it something happened.
    for event in events:
        if event.event_type is location.GeofenceEventType.EXIT:
            _warn_of_unrecoverable_gaps(db, account, event.facility_id, now)
    # §23 entry 112: independent of the geofence, and it has to be. Events only fire
    # for ARMED facilities, so a driver parked at a truck stop for the night produces
    # none — this reads the ping trail instead and writes nothing to the location
    # tables. The prompt's own checks are ordered cheapest-first inside M1.
    _ask_about_the_lot(db, account, body.lat, body.lon, now)


    # the events go back so the client can react to its own movement without polling —
    # an EXIT is what tells the Load tab the driver has left the dock.
    return {
        "recorded_at": now.isoformat(),
        "client_skew_ms": skew_ms,
        "events": [
            {
                "event_type": e.event_type.value,
                "facility_id": str(e.facility_id),
                "occurred_at": e.occurred_at.isoformat(),
            }
            for e in events
        ],
    }

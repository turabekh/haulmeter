"""AI-CONTEXT: M1 Road Intelligence Map HTTP endpoints. Thin over the m01_map
module public — the router serializes and authenticates; all logic stays in the
module (which composes F2/F10/F11/F12). The status pipeline is live end-to-end
here: POST /map/report → F10 belief → the next GET /map/overlay reflects it.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import canonical_facility_id, current_account, get_db, require_module
from app.api.events import publish_status
from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f08_notifications import public as notify
from app.foundation.f10_crowd import public as crowd
from app.foundation.f13_flags import public as flags
from app.modules.m01_map import public as m1
from app.modules.m03_detention import public as m3
from app.modules.m06_parking import public as m6
from app.modules.m07_fuel import public as m7
from app.modules.m13_vendor import public as m13

router = APIRouter(prefix="/map", tags=["map"],
    # PRD §6: the module's own flag, gating every route in it (§23 entry 105)
    dependencies=[Depends(require_module("m01_map"))],
)


def _serialize_pin(pin) -> dict:
    return {
        "facility_id": str(pin.facility_id),
        "name": pin.name,
        "facility_type": pin.facility_type,
        "shape": pin.shape,
        "lat": pin.lat,
        "lon": pin.lon,
        "status": pin.status,
        "availability": pin.availability,  # int count or "Low" category (never int-parsed)
        "capacity": pin.capacity,
        # A5: what the SITE offers, and how to reach it. `services` reached the Pin
        # object long before this and stopped there — never serialized, so the client
        # could not have rendered a service list if it wanted to.
        "services": pin.services,
        "phone": pin.phone,
        "opening_hours": pin.opening_hours,
        "badges": [{"kind": b.kind, "value": b.value} for b in pin.badges],
        "freshness": (
            {
                "reported_at": pin.freshness.reported_at,
                "sample_size": pin.freshness.sample_size,
                "source": pin.freshness.source,
            }
            if pin.freshness is not None
            else None
        ),
    }


def _serialize_cluster(cluster) -> dict:
    # §11.5: a cluster chip shows count + dominant status color (client renders color)
    return {
        "cluster": True,
        "count": cluster.count,
        "lat": cluster.center_lat,
        "lon": cluster.center_lon,
        "status": cluster.dominant_status,
    }


@router.get("/overlay")
def overlay(
    preset: str = "drive",
    amenities: str = "",
    min_lat: float | None = None,
    min_lon: float | None = None,
    max_lat: float | None = None,
    max_lon: float | None = None,
    lat: float | None = None,
    lon: float | None = None,
    radius_m: float = 8000,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    # PRIMARY: viewport bbox (min/max lat/lon) — the map fetches what's in view.
    # SECONDARY: point + radius (corridor / nearby). Sparse -> pins; dense or huge
    # area -> server-side clusters (bounded payload, §11.5/§20).
    required = [a for a in amenities.split(",") if a] or None
    # AI-CONTEXT: an unknown preset is the CLIENT's mistake, so it answers 422 rather
    # than 500. It reached production as a 500 because `Preset(preset)` was called bare:
    # the Food chip sends `preset=food`, `food` has never been a member of this enum,
    # and the surface's own catch swallowed the error into its offline path — so every
    # tap on Food fell back to FIXTURES and looked merely empty rather than broken.
    # A 500 that a client silently absorbs is the hardest kind of defect to see.
    try:
        preset_enum = m1.Preset(preset)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"error": "unknown_preset", "preset": preset,
             "known": [p.value for p in m1.Preset]},
        ) from exc
    if None not in (min_lat, min_lon, max_lat, max_lon):
        view = m1.map_overlay_view_bbox(
            db,
            account.id,
            min_lat,
            min_lon,
            max_lat,
            max_lon,
            preset=preset_enum,
            required_amenities=required,
        )
    elif None not in (lat, lon):
        view = m1.map_overlay_view(
            db, account.id, lat, lon, radius_m, preset=preset_enum, required_amenities=required
        )
    else:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "provide a bbox (min_lat,min_lon,max_lat,max_lon) or a point (lat,lon)",
        )
    pins = [_enrich(db, p) for p in view["pins"]]
    _apply_claims(db, pins)
    return {
        "clustered": view["clustered"],
        "total": view["total"],
        "pins": pins,
        "clusters": [_serialize_cluster(c) for c in view["clusters"]],
    }


@router.get("/presets")
def presets(
    _account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    """AI-CONTEXT: which preset chips a driver may actually use, from the server.

    The chip row was a hardcoded array, so it rendered Food whatever the flags said. A
    flag that hides the DATA but not the CONTROL leaves a driver tapping a chip that
    answers nothing — the §21.3 rule that a control leading nowhere is decoration, and
    the same reasoning §23 entry 415 used to make a rail item type-conditional.

    Food is the case that forced this: v2.0 §4 defers it indefinitely, and it is not a
    member of `Preset` at all — it is a client-side mode over the M13 endpoints, which
    is why `preset=food` was a 500. So its liveness is M13's flag, resolved here at the
    composition layer because M1 may not import a later module.

    Returned as a LIST rather than per-preset booleans so a preset added later rides
    along without another field, the same shape the vendor portal uses for
    `halal_claims_available` — the client offers only what the server will honour.
    """
    live = [p.value for p in m1.Preset if p != m1.Preset.service]
    if not flags.is_switched_off(db, m1.SERVICE_PRESET_FLAG):
        live.append(m1.Preset.service.value)
    if m13.is_active_for(db, m13.VendorType.food_mobile):
        live.append("food")
    return {"presets": live}


def _apply_claims(db: Session, pins: list[dict]) -> None:
    """AI-CONTEXT: A6 — where CLAIMING finally reaches the card a driver calls from.

    FR7 has always improved `/facility/<id>`, the full profile. But A5 put tap-to-call
    on the map CARD, and A6's validation is "one real repair shop claims its facility
    and receives one call through the app" — so a shop could claim its site, add the
    number it actually answers, and the driver tapping that pin would still see the
    OSM phone, or for 28 of 45 repair facilities no call action at all. The feature
    was improving the surface nobody in a breakdown is looking at.

    Claimed values WIN over ingested ones here, which is the opposite of the E3.2 rule
    for services and deliberately so: `services` is a union because ingestion recorded
    a fact and the shop is adding to it, while `phone` and `opening_hours` are single
    values where the business is simply the better authority about itself. Nothing is
    overwritten in the registry — this is a read-time overlay, so an unclaimed or
    un-curated field falls straight back to what OSM said.

    Attribution rides along in `claimed_by` because §11.7 forbids presenting a
    business's own claim as the platform's finding. The card names who is telling the
    driver, exactly as the profile card already does.
    """
    if not m13.is_active_for(db, m13.VendorType.service_center):
        return
    claimed = m13.claimed_facility_views(db, [uuid.UUID(p["facility_id"]) for p in pins])
    if not claimed:
        return
    for pin in pins:
        view = claimed.get(uuid.UUID(pin["facility_id"]))
        if view is None:
            continue
        if view.phone:
            pin["phone"] = view.phone
        if view.hours:
            pin["opening_hours"] = view.hours
        if view.services:
            pin["services"] = view.services
        pin["claimed_by"] = {"name": view.vendor_name, "verify_status": view.verify_status}


def _fuel_badge(db: Session, facility_id, lat: float, lon: float) -> dict | None:
    """AI-CONTEXT: ONE definition of a station's price badge, because two screens now
    render it. The map pin and the corridor stack must not be able to quote a driver
    different figures for the same pump — which is exactly what a second, hand-rolled
    price read on the corridor path would eventually do.

    net feed price -> crowd consensus -> EIA regional baseline (§ m7.fuel_summary).
    lat/lon let the regional fallback pick the right PADD when no per-station price.
    """
    summary = m7.fuel_summary(db, facility_id, lat=lat, lon=lon)
    if not summary:
        return None
    return {
        "kind": "fuel_net",
        "value": summary["net"],
        "net": summary["net"],
        "gross": summary["gross"],
        "savings": summary["savings"],
        "is_network": summary["is_network"],
        "source": summary["source"],
        "indicative": summary["indicative"],
        "as_of": summary["as_of"],
        "sample_size": summary["sample_size"],
        "station_ref": str(facility_id),
    }


# AI-CONTEXT: §11.2's third badge slot — "clock (dwell risk)" — which had no signal
# behind it until M2-FR3 was implemented (§23 entry 87). Two numbers decide whether it
# is drawn, and both are §11.7 rather than taste:
#
# · MIN_SAMPLES = 3 is M8's own `MEDIUM_MIN`, reused rather than invented. Below it a
#   rate is one or two visits and a badge would be a rumour with a clock on it.
# · RISK_THRESHOLD = 0.5 is the owner-logged line: a dock that runs past the free time
#   it CONTRACTED for on half or more of its tracked stops is a detention risk by any
#   reading. It is deliberately a blunt number — this badge is a mark on a 28 dp puck,
#   not a figure, and the card behind it carries the rate and the sample size.
#
# A badge on every receiver we happen to have data for would be a data-coverage
# indicator, not a risk one; §11.1 keeps the map quiet, so the mark only appears where
# it changes a decision.
DWELL_RISK_MIN_SAMPLES = 3
DWELL_RISK_THRESHOLD = 0.5


def _dwell_risk_badge(db: Session, facility_id) -> dict | None:
    stats = m3.facility_detention_stats(db, facility_id)
    rate = stats["exceed_rate"]
    if rate is None or stats["sample_size"] < DWELL_RISK_MIN_SAMPLES:
        return None
    if rate < DWELL_RISK_THRESHOLD:
        return None
    return {
        "kind": "dwell_risk",
        "value": round(rate, 2),
        # the sample travels with the badge so the card can state it without a second
        # request — §11.7 never shows a rate without what it was measured over
        "sample_size": stats["sample_size"],
        "basis": stats["basis"],
    }


def _enrich(db: Session, pin) -> dict:
    # M1 can't import later modules, so the marketplace badges (M6 bookable spot,
    # M7 net fuel price) that drive the map's Book / Fuel actions are attached here
    # at the composition layer.
    data = _serialize_pin(pin)
    if pin.facility_type == "parking_property":
        summary = m6.bookable_summary(db, pin.facility_id)
        if summary:
            data["badges"].append(
                {
                    "kind": "bookable",
                    "value": summary["price_cents_per_night"],
                    "spot_id": summary["spot_id"],
                }
            )
    elif m1.sells_fuel(pin.facility_type, pin.services):
        badge = _fuel_badge(db, pin.facility_id, pin.lat, pin.lon)
        if badge is not None:
            data["badges"].append(badge)
    elif pin.facility_type == "shipper_receiver":
        badge = _dwell_risk_badge(db, pin.facility_id)
        if badge is not None:
            data["badges"].append(badge)
    return data


@router.get("/corridor")
def corridor(
    lat: float,
    lon: float,
    heading_deg: float,
    max_distance_m: float = 40000,
    preset: str = "drive",
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> list[dict]:
    """AI-CONTEXT: §11.4's stack, and until now nothing had ever called it.

    The endpoint shipped with M1 and the Map surface passed a hardcoded
    `SAMPLE_CORRIDOR` to the component instead — three invented facilities with
    invented parking statuses, rendered in DRIVING, the one state where a driver
    cannot look anything up. The fixture carried a `status` this route did not
    return, which is why wiring it was never as simple as swapping the prop: a
    fixture whose shape does not match its endpoint hides the endpoint.

    So the response now carries what the component renders — the crowd status with
    its freshness, and the same fuel badge the pin behind it would show.
    """
    rows = []
    for entry in m1.corridor_ahead(
        db, account.id, lat, lon, heading_deg, max_distance_m, preset=m1.Preset(preset)
    ):
        badges = []
        if m1.sells_fuel(entry["facility_type"], entry.get("services")):
            badge = _fuel_badge(db, entry["facility_id"], entry["lat"], entry["lon"])
            if badge is not None:
                badges.append(badge)
        rows.append(
            {
                "facility_id": str(entry["facility_id"]),
                "name": entry["name"],
                "facility_type": entry["facility_type"],
                # AI-CONTEXT: WHERE it is (§23 entry 86). §11.4's saved-for-stop queue
                # hands a driver a Navigate button, and without coordinates that button
                # could only route through the facility page — a control that half
                # works. The corridor already computes these to measure the bearing
                # cone; it was throwing them away on the way out.
                "lat": entry["lat"],
                "lon": entry["lon"],
                "distance_m": entry["distance_m"],
                "status": entry["status"],
                "reported_at": (
                    entry["reported_at"].isoformat() if entry["reported_at"] else None
                ),
                "sample_size": entry["sample_size"],
                "badges": badges,
            }
        )
    return rows


class ReportIn(BaseModel):
    facility_id: uuid.UUID
    signal_type: str
    value: dict
    submitted_at: datetime | None = None


@router.post("/report")
def report(
    body: ReportIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    # the facility_id rides in the BODY here, so the path-level resolver cannot reach
    # it — and this is the write where a stale id hurt most: the report was accepted,
    # a submission_id returned, and the belief written onto a pin that no longer
    # renders, so a driver was told their "lot is full" landed and nobody would see it.
    submission = m1.submit_status(
        db,
        account.id,
        canonical_facility_id(body.facility_id, db),
        crowd.SignalType(body.signal_type),
        body.value,
        body.submitted_at or datetime.now(UTC),
    )
    # §23 entry 104: tell the drivers nearby that this lot just changed. After the
    # write, and carrying only the id — see `publish_status`.
    target = canonical_facility_id(body.facility_id, db)
    fac = facility.get_facility(db, target)
    if fac is not None:
        lat, lon = facility.coordinates(db, fac)
        publish_status(target, lat, lon)
    return {
        "submission_id": str(submission.id),
        "presence_proven": submission.presence_proven,
    }


# AI-CONTEXT: silencing the lot-status prompt at ONE lot (§13.1's per-subject mute,
# §23 entry 114 — owner-chose the placement).
#
# F8 has had `mute_subject` since the vendor class shipped and no surface used it for
# this class, so the only control a driver had was the whole class. These three routes
# are the per-subject half, and they live in M1 rather than on M2's `/facility` router
# because that one is gated on `require_module("m02_facility_intel")` and this is M1's
# notification class.
#
# CANONICALISING IS LOAD-BEARING, not tidiness. The prompt writes `subject_ref` from the
# facility F2 resolved, so a mute recorded against a MERGED id would never match it: the
# driver would tap "don't ask about this lot", get a 200, and be asked again the next
# night. That is §23 entry 73's scoping mistake in a new place, and a test holds it.
#
# Two POSTs rather than one PUT with a boolean: both directions then go through the
# client's `queuedPost`, so a driver who mutes a lot with no signal still mutes it
# (§22.3's offline clause). The class-level switch is a PUT because it is not queued.
# AI-CONTEXT: A5's validation observation. v2.0 §2 makes "done" an observation about
# a person, and a `tel:` anchor leaves none — so the tap posts here. 204: the driver is
# already dialling and there is nothing to say back.
#
# `canonical_facility_id` rather than the raw id, because a merged facility must record
# against the pin that survived — the same resolution every other route here uses, and
# the one `/admin/facilities/*` still does not (carried debt).
@router.post("/facility/{facility_id}/called", status_code=204)
def record_call(
    facility_id: uuid.UUID = Depends(canonical_facility_id),
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> None:
    m1.record_service_call(db, account.id, facility_id, datetime.now(UTC))


@router.get("/facility/{facility_id}/prompt-pref")
def prompt_pref(
    facility_id: uuid.UUID = Depends(canonical_facility_id),
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    return {
        "facility_id": str(facility_id),
        "muted": notify.is_subject_muted(
            db, account.id, notify.LOT_STATUS_PROMPT_CLASS, str(facility_id)
        ),
    }


@router.post("/facility/{facility_id}/mute-prompts")
def mute_prompts(
    facility_id: uuid.UUID = Depends(canonical_facility_id),
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    notify.mute_subject(db, account.id, notify.LOT_STATUS_PROMPT_CLASS, str(facility_id))
    return {"facility_id": str(facility_id), "muted": True}


@router.post("/facility/{facility_id}/unmute-prompts")
def unmute_prompts(
    facility_id: uuid.UUID = Depends(canonical_facility_id),
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    """Answers 200 whether or not a mute was there — the driver asked for a state and is
    now in it, the same posture `/push/unsubscribe` takes. It leaves the CLASS alone: a
    driver un-silencing one lot has not asked to be asked everywhere."""
    notify.unmute_subject(db, account.id, notify.LOT_STATUS_PROMPT_CLASS, str(facility_id))
    return {"facility_id": str(facility_id), "muted": False}


@router.get("/scales-ahead")
def scales_ahead(
    lat: float,
    lon: float,
    heading_deg: float = 0,
    max_distance_m: float = 64000,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> list[dict]:
    """E3.1: weigh stations on the heading, freshest crowd status first. Returns an
    empty list while the layer flag is off — a driver never downloads a layer they
    have not been given."""
    return [
        {
            "facility_id": str(s["facility_id"]),
            "name": s["name"],
            "facility_type": s["facility_type"],
            "distance_m": s["distance_m"],
            # None means nobody has reported recently. "Unknown" is the honest state
            # for a scale nobody has passed, and the client says so (§11.7).
            "status": s["status"],
            "reported_at": s["reported_at"].isoformat() if s["reported_at"] else None,
            "sample_size": s["sample_size"],
        }
        for s in m1.scales_ahead(db, account.id, lat, lon, heading_deg, max_distance_m)
    ]

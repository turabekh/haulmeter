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

from app.api.deps import canonical_facility_id, current_account, get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f10_crowd import public as crowd
from app.modules.m01_map import public as m1
from app.modules.m03_detention import public as m3
from app.modules.m06_parking import public as m6
from app.modules.m07_fuel import public as m7

router = APIRouter(prefix="/map", tags=["map"])


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
    preset_enum = m1.Preset(preset)
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
    return {
        "clustered": view["clustered"],
        "total": view["total"],
        "pins": [_enrich(db, p) for p in view["pins"]],
        "clusters": [_serialize_cluster(c) for c in view["clusters"]],
    }


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
    return {
        "submission_id": str(submission.id),
        "presence_proven": submission.presence_proven,
    }


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

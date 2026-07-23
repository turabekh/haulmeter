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

from app.api.deps import current_account, get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f10_crowd import public as crowd
from app.modules.m01_map import public as m1
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
            {"reported_at": pin.freshness.reported_at, "sample_size": pin.freshness.sample_size}
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
            db, account.id, min_lat, min_lon, max_lat, max_lon,
            preset=preset_enum, required_amenities=required,
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
    elif pin.facility_type == "fuel_station":
        # net feed price -> crowd consensus -> EIA regional baseline (§ m7.fuel_summary).
        # lat/lon let the regional fallback pick the right PADD when no per-station price.
        summary = m7.fuel_summary(db, pin.facility_id, lat=pin.lat, lon=pin.lon)
        if summary:
            data["badges"].append(
                {
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
                    "station_ref": str(pin.facility_id),
                }
            )
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
    entries = m1.corridor_view(
        db, account.id, lat, lon, heading_deg, max_distance_m, preset=m1.Preset(preset)
    )
    return [
        {
            "facility_id": str(e.facility_id),
            "name": e.name,
            "facility_type": e.facility_type,
            "distance_m": e.distance_m,
        }
        for e in entries
    ]


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
    submission = m1.submit_status(
        db,
        account.id,
        body.facility_id,
        crowd.SignalType(body.signal_type),
        body.value,
        body.submitted_at or datetime.now(UTC),
    )
    return {
        "submission_id": str(submission.id),
        "presence_proven": submission.presence_proven,
    }

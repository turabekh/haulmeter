"""AI-CONTEXT: M1 Road Intelligence Map HTTP endpoints. Thin over the m01_map
module public — the router serializes and authenticates; all logic stays in the
module (which composes F2/F10/F11/F12). The status pipeline is live end-to-end
here: POST /map/report → F10 belief → the next GET /map/overlay reflects it.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
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
        "badges": [{"kind": b.kind, "value": b.value} for b in pin.badges],
        "freshness": (
            {"reported_at": pin.freshness.reported_at, "sample_size": pin.freshness.sample_size}
            if pin.freshness is not None
            else None
        ),
    }


@router.get("/overlay")
def overlay(
    lat: float,
    lon: float,
    radius_m: float = 8000,
    preset: str = "drive",
    amenities: str = "",
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> list[dict]:
    required = [a for a in amenities.split(",") if a] or None
    pins = m1.map_overlay(
        db, account.id, lat, lon, radius_m, preset=m1.Preset(preset), required_amenities=required
    )
    return [_enrich(db, p) for p in pins]


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
        summary = m7.fuel_summary(db, pin.facility_id)
        if summary:
            data["badges"].append(
                {
                    "kind": "fuel_net",
                    "value": summary["net"],
                    "net": summary["net"],
                    "gross": summary["gross"],
                    "savings": summary["savings"],
                    "is_network": summary["is_network"],
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

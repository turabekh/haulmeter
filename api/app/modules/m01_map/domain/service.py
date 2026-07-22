"""AI-CONTEXT: M1 Road Intelligence Map (PRD §8.1) — the daily-open surface.

A thin module composing Common Ground services via their public interfaces only
(import-linter enforced): F11 for POI overlay + corridor, F10 for live crowd
belief + contributions, F12 for offline queueing, F1 for the rig profile, F7 for
points (through F10). No module reaches a foundation's internals. Everything the
map shows is honest about freshness (design-prd §11.7); prediction is explicitly
heuristic until M8. Runs behind the F13 flag `m01_map`.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.foundation.f02_facility import public as facility
from app.foundation.f10_crowd import public as crowd
from app.foundation.f11_map import public as mapsvc
from app.foundation.f12_offline import public as offline
from app.foundation.f13_flags import public as flags
from app.foundation.f14_admin import public as admin

from .enums import NavProvider, Preset

FLAG_KEY = "m01_map"
MODULE = "m01"

# design-prd §11.3: presets ARE the interface. Each maps to the layers it shows.
PRESET_TYPES: dict[Preset, list] = {
    Preset.drive: [
        facility.FacilityType.truck_stop,
        facility.FacilityType.rest_area,
        facility.FacilityType.fuel_station,
    ],
    Preset.tonight: [
        facility.FacilityType.truck_stop,
        facility.FacilityType.rest_area,
        facility.FacilityType.parking_property,
    ],
    Preset.work: [facility.FacilityType.shipper_receiver],
    Preset.fuel: [facility.FacilityType.fuel_station],
}

# parking availability ordering for the Tonight preset (best first)
_PARKING_RANK = {"empty": 0, "some": 1, None: 2, "full": 3}


@dataclass
class ParkingPrediction:
    status: str
    basis: str
    note: str


def register_module(db: Session) -> None:
    flags.register_flag(db, FLAG_KEY, description="M1 Road Intelligence Map")
    admin.register_admin_view(db, "m01.map", MODULE, "Road Intelligence Map", "/admin/m01/map")


def map_overlay(
    db: Session,
    account_id,
    center_lat: float,
    center_lon: float,
    radius_m: float,
    preset: Preset = Preset.drive,
    required_amenities: list[str] | None = None,
):
    pins = mapsvc.overlay_pins(
        db, center_lat, center_lon, radius_m, facility_types=PRESET_TYPES[preset]
    )
    if required_amenities:
        pins = [p for p in pins if _has_amenities(db, p, required_amenities)]
    if preset == Preset.tonight:
        pins = sorted(pins, key=lambda p: _PARKING_RANK.get(p.status, 2))
    return pins


# above this many pins in view, the server clusters (design-prd §11.5) so the map
# payload stays bounded at real national density and the client budget (§20) holds
OVERLAY_PIN_CAP = 300


def map_overlay_view(
    db: Session,
    account_id,
    center_lat: float,
    center_lon: float,
    radius_m: float,
    preset: Preset = Preset.drive,
    required_amenities: list[str] | None = None,
    cap: int = OVERLAY_PIN_CAP,
):
    # returns individual pins when sparse; server-side clusters when dense. Payload
    # size is bounded either way (≤ cap pins, or the number of cluster cells).
    pins = map_overlay(db, account_id, center_lat, center_lon, radius_m, preset, required_amenities)
    if len(pins) <= cap:
        return {"clustered": False, "pins": pins, "clusters": [], "total": len(pins)}
    clusters = mapsvc.cluster_pins(pins)
    return {"clustered": True, "pins": [], "clusters": clusters, "total": len(pins)}


def _has_amenities(db: Session, pin, required: list[str]) -> bool:
    fac = facility.get_facility(db, pin.facility_id)
    amenities = (fac.attributes or {}).get("amenities", []) if fac is not None else []
    return all(a in amenities for a in required)


def corridor_view(
    db: Session,
    account_id,
    origin_lat: float,
    origin_lon: float,
    heading_deg: float,
    max_distance_m: float,
    preset: Preset = Preset.drive,
):
    return mapsvc.corridor(
        db,
        origin_lat,
        origin_lon,
        heading_deg,
        max_distance_m,
        facility_types=PRESET_TYPES[preset],
    )


def predict_parking_fill(db: Session, facility_id, hour_of_day: int) -> ParkingPrediction:
    # AI-CONTEXT: heuristic until M8 upgrades it to a learned model (PRD M1-FR3);
    # basis is always surfaced so the UI never fakes precision (design-prd §11.7).
    if hour_of_day >= 18 or hour_of_day < 4:
        status = "full"
    elif hour_of_day >= 15:
        status = "some"
    else:
        status = "empty"
    return ParkingPrediction(status=status, basis="heuristic", note="usually fills by 6pm")


def submit_status(
    db: Session,
    account_id,
    facility_id,
    signal_type: crowd.SignalType,
    value: dict,
    submitted_at: datetime,
):
    # geofence-presence proof + points are enforced inside F10 (PRD M1-FR7)
    submission = crowd.submit(
        db, account_id, facility_id, signal_type, value, submitted_at=submitted_at
    )
    # refresh the aggregated belief so the pin reflects it immediately
    # (M1 DoD: report -> aggregate -> pin badge under 60s)
    crowd.update_belief(db, facility_id, signal_type, as_of=submitted_at)
    return submission


def queue_status_offline(
    db: Session,
    account_id,
    idempotency_key: str,
    facility_id,
    signal_type: crowd.SignalType,
    value: dict,
    submitted_at: datetime,
):
    # PRD M1-FR9: contributions written locally first, synced idempotently via F12;
    # the handler applies the F10 submission exactly once on first sync.
    def apply(_envelope):
        crowd.submit(db, account_id, facility_id, signal_type, value, submitted_at=submitted_at)

    return offline.ingest(
        db,
        account_id,
        idempotency_key,
        "crowd_status",
        {"facility_id": str(facility_id), "signal": signal_type.value, "value": value},
        occurred_at=submitted_at,
        handler=apply,
    )


def nav_deeplink(lat: float, lon: float, provider: NavProvider = NavProvider.google) -> str:
    # PRD M1-FR8: deep-link handoff to external nav — explicitly NO in-house routing.
    if provider == NavProvider.google:
        return f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}"
    if provider == NavProvider.apple:
        return f"https://maps.apple.com/?daddr={lat},{lon}"
    if provider == NavProvider.hammer:
        return f"hammer://navigate?lat={lat}&lon={lon}"
    return f"copilot://navigate?lat={lat}&lon={lon}"


def record_map_open(db: Session, account_id, occurred_at: datetime):
    return admin.emit(db, "map_open", MODULE, occurred_at, account_id=account_id)

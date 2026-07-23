"""AI-CONTEXT: F11 Map & POI Serving (PRD §7.11) — a schema-less serving layer.

Composes F2 facility geometry + F10 crowd beliefs into map overlays server-side.
It owns no tables; it returns SEMANTIC data (pin shape, parking status, badges,
freshness) and the client renders colors from design tokens (design-prd §6/§11)
— no color/visual decision is made here. Pin-shape mapping is transcribed from
design-prd §11.2 (unspecified POI types fall back to the generic circle, which
composes existing shapes rather than inventing one). Mapbox tiles + night/day
styling are a client concern; no tile secret lives server-side.
"""

import math
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.foundation.f02_facility import public as facility_registry
from app.foundation.f10_crowd import public as crowd

# design-prd §11.2 pin taxonomy: shape encodes facility type
PIN_SHAPES: dict[str, str] = {
    "truck_stop": "circle",
    "rest_area": "circle",
    "parking_property": "square",
    "shipper_receiver": "diamond",
    "scale": "small_square",
    "weigh_station": "small_square",
    "fuel_station": "circle",
    "repair": "circle",
    "composite": "circle",
}
DEFAULT_SHAPE = "circle"


@dataclass
class Badge:
    kind: str
    value: object


@dataclass
class Freshness:
    reported_at: object
    sample_size: int
    source: str | None = None  # provenance of the winning reading ("tpims" feed, else None)


@dataclass
class Pin:
    facility_id: object
    name: str
    facility_type: str
    shape: str
    lat: float
    lon: float
    status: str | None = None
    badges: list[Badge] = field(default_factory=list)
    freshness: Freshness | None = None
    # TPIMS availability as reported (int count OR the "Low" category — NEVER an int
    # parse of "Low", condition A) + the site's total capacity, so the card can show
    # "Low · N spots" honestly. None for crowd-only / no-reading facilities.
    availability: object = None
    capacity: int | None = None


@dataclass
class Cluster:
    count: int
    center_lat: float
    center_lon: float
    dominant_status: str | None


@dataclass
class CorridorEntry:
    facility_id: object
    name: str
    facility_type: str
    lat: float
    lon: float
    distance_m: float
    bearing_deg: float


# --- geo helpers ---
def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _angle_diff(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d


# --- badge providers (module hooks compose here; more register as modules land) ---
def fuel_price_badge(db: Session, facility) -> Badge | None:
    belief = crowd.get_belief(db, facility.id, crowd.SignalType.fuel_price)
    if belief is not None and "price_cents" in (belief.value or {}):
        return Badge("fuel_price", belief.value["price_cents"])
    return None


DEFAULT_BADGE_PROVIDERS = [fuel_price_badge]


def _parking_status(db: Session, facility):
    belief = crowd.get_belief(db, facility.id, crowd.SignalType.parking_fullness)
    if belief is None:
        return None, None, None
    value = belief.value or {}
    status = value.get("status")
    freshness = Freshness(
        reported_at=belief.freshest_at,
        sample_size=belief.sample_size,
        source=value.get("source"),  # "tpims" when a feed reading wins; None for crowd
    )
    return status, freshness, value.get("available")  # "available" present only for TPIMS


def _pin_for(db: Session, facility, badge_providers) -> Pin:
    lat, lon = facility_registry.coordinates(db, facility)
    status, freshness, availability = _parking_status(db, facility)
    capacity = (facility.attributes or {}).get("capacity") if availability is not None else None
    badges = [b for provider in badge_providers if (b := provider(db, facility)) is not None]
    return Pin(
        facility_id=facility.id,
        name=facility.name,
        facility_type=facility.facility_type.value,
        shape=PIN_SHAPES.get(facility.facility_type.value, DEFAULT_SHAPE),
        lat=lat,
        lon=lon,
        status=status,
        badges=badges,
        freshness=freshness,
        availability=availability,
        capacity=capacity,
    )


def _facilities_in_area(db: Session, lat, lon, radius_m, facility_types):
    if not facility_types:
        return facility_registry.nearest(db, lat, lon, radius_m)
    seen: dict = {}
    for ftype in facility_types:
        for fac in facility_registry.nearest(db, lat, lon, radius_m, facility_type=ftype):
            seen[fac.id] = fac
    return list(seen.values())


def overlay_pins(
    db: Session,
    center_lat: float,
    center_lon: float,
    radius_m: float,
    facility_types=None,
    badge_providers=None,
) -> list[Pin]:
    providers = badge_providers or DEFAULT_BADGE_PROVIDERS
    facilities = _facilities_in_area(db, center_lat, center_lon, radius_m, facility_types)
    return [_pin_for(db, fac, providers) for fac in facilities]


def _facilities_in_bbox(db, min_lat, min_lon, max_lat, max_lon, facility_types):
    if not facility_types:
        return facility_registry.in_bbox(db, min_lat, min_lon, max_lat, max_lon)
    seen: dict = {}
    for ftype in facility_types:
        for fac in facility_registry.in_bbox(
            db, min_lat, min_lon, max_lat, max_lon, facility_type=ftype
        ):
            seen[fac.id] = fac
    return list(seen.values())


def overlay_pins_bbox(
    db: Session,
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    facility_types=None,
    badge_providers=None,
) -> list[Pin]:
    providers = badge_providers or DEFAULT_BADGE_PROVIDERS
    facilities = _facilities_in_bbox(db, min_lat, min_lon, max_lat, max_lon, facility_types)
    return [_pin_for(db, fac, providers) for fac in facilities]


def cluster_pins(pins: list[Pin], precision_deg: float = 0.1) -> list[Cluster]:
    buckets: dict[tuple[int, int], list[Pin]] = {}
    for pin in pins:
        cell = (round(pin.lat / precision_deg), round(pin.lon / precision_deg))
        buckets.setdefault(cell, []).append(pin)

    clusters: list[Cluster] = []
    for members in buckets.values():
        statuses: dict[str, int] = {}
        for pin in members:
            if pin.status is not None:
                statuses[pin.status] = statuses.get(pin.status, 0) + 1
        dominant = max(statuses, key=statuses.get) if statuses else None
        clusters.append(
            Cluster(
                count=len(members),
                center_lat=sum(p.lat for p in members) / len(members),
                center_lon=sum(p.lon for p in members) / len(members),
                dominant_status=dominant,
            )
        )
    return clusters


def corridor(
    db: Session,
    origin_lat: float,
    origin_lon: float,
    heading_deg: float,
    max_distance_m: float,
    facility_types=None,
    half_angle_deg: float = 45.0,
) -> list[CorridorEntry]:
    facilities = _facilities_in_area(db, origin_lat, origin_lon, max_distance_m, facility_types)
    entries: list[CorridorEntry] = []
    for fac in facilities:
        lat, lon = facility_registry.coordinates(db, fac)
        bearing = _bearing_deg(origin_lat, origin_lon, lat, lon)
        if _angle_diff(bearing, heading_deg) > half_angle_deg:
            continue
        entries.append(
            CorridorEntry(
                facility_id=fac.id,
                name=fac.name,
                facility_type=fac.facility_type.value,
                lat=lat,
                lon=lon,
                distance_m=_haversine_m(origin_lat, origin_lon, lat, lon),
                bearing_deg=bearing,
            )
        )
    entries.sort(key=lambda e: e.distance_m)
    return entries

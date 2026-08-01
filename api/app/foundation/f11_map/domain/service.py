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
    # E3.3: what the SITE offers, independent of the kind it is filed under. A badge
    # keyed on facility_type can only be drawn on the pin a co-location merge is about
    # to remove; keyed on this, it follows the fact onto the surviving pin.
    services: list[str] = field(default_factory=list)
    # A5: the card renders from a pin, so a phone that stops at the facility row is a
    # phone the driver cannot tap. Absent rather than empty — the card decides whether
    # to offer a call by asking whether there IS one, and "" answers yes.
    phone: str | None = None
    opening_hours: str | None = None


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
    services: list[str] = field(default_factory=list)


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


# AI-CONTEXT: which crowd signal a pin's status comes from depends on what the
# facility IS. A truck stop's status is how full it is; a weigh station's is whether
# it is open. Reading parking fullness off a scale would render a status that means
# nothing about it — the signal has to follow the kind.
_STATUS_SIGNAL = {
    "weigh_station": crowd.SignalType.weigh_station_status,
    "scale": crowd.SignalType.weigh_station_status,
}
_DEFAULT_STATUS_SIGNAL = crowd.SignalType.parking_fullness


def status_signal_for(facility_type: str):
    return _STATUS_SIGNAL.get(facility_type, _DEFAULT_STATUS_SIGNAL)


def _parking_status(db: Session, facility):
    signal = status_signal_for(facility.facility_type.value)
    belief = crowd.get_belief(db, facility.id, signal)
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


def _statuses_for(db: Session, facilities) -> dict:
    """AI-CONTEXT: every parking/crowd status in one query PER SIGNAL, not per pin.

    `_parking_status` asked F10 for one belief at a time, so a 609-facility viewport
    issued 609 belief queries. F10 has had `beliefs_for_signal` since the vendor layer
    — its comment says "the map overlay needs this without an N+1" — and the map never
    used it. Signals are grouped because the signal a facility carries depends on its
    KIND, and there are a handful of kinds, not a handful of hundreds.

    `subject_ref` is filtered to "" to match `get_belief`'s default: the parking status
    of a SITE, not a belief some vendor holds about it."""
    by_signal: dict = {}
    for fac in facilities:
        by_signal.setdefault(status_signal_for(fac.facility_type.value), []).append(fac.id)
    out: dict = {}
    for signal, ids in by_signal.items():
        for belief in crowd.beliefs_for_signal(db, ids, signal):
            if belief.subject_ref:
                continue
            value = belief.value or {}
            out[belief.facility_id] = (
                value.get("status"),
                Freshness(
                    reported_at=belief.freshest_at,
                    sample_size=belief.sample_size,
                    source=value.get("source"),
                ),
                value.get("available"),
            )
    return out


def _default_badges_for(db: Session, facilities) -> dict:
    """The DEFAULT provider set, batched. `fuel_price_badge` was a third per-pin belief
    read; the fast path answers it for the whole viewport in one query. A caller that
    passes its OWN providers keeps the per-facility seam — extension is not the hot
    path, and a custom provider must not be forced to grow a bulk form."""
    out: dict = {}
    for belief in crowd.beliefs_for_signal(
        db, [f.id for f in facilities], crowd.SignalType.fuel_price
    ):
        if belief.subject_ref:
            continue
        value = belief.value or {}
        if "price_cents" in value:
            out.setdefault(belief.facility_id, []).append(
                Badge("fuel_price", value["price_cents"])
            )
    return out


# AI-CONTEXT: ONE place a Pin is built from a facility. There were two — the bulk
# builder below and the single-facility one further down — and A5 walked straight
# into the trap §23 entry 113 documents: `phone` was added to one of them, every
# unit test passed, and the map (which uses the other) still had no phone number.
# Two constructors for one object is an agreement owned by neither, exactly like the
# token the tray answer never had. Everything a pin says about a facility is said
# here; the callers differ only in how they FETCHED the pieces.
def _build_pin(fac, lat, lon, status, badges, freshness, availability, capacity) -> Pin:
    attrs = fac.attributes or {}
    return Pin(
        facility_id=fac.id,
        name=fac.name,
        facility_type=fac.facility_type.value,
        shape=PIN_SHAPES.get(fac.facility_type.value, DEFAULT_SHAPE),
        lat=lat,
        lon=lon,
        status=status,
        badges=badges,
        freshness=freshness,
        availability=availability,
        capacity=capacity,
        services=list(attrs.get("services") or []),
        phone=attrs.get("phone"),
        opening_hours=attrs.get("opening_hours"),
    )


def pins_for(db: Session, facilities, badge_providers=None) -> list[Pin]:
    """The list-shaped builder. Coordinates, statuses and the default badges are each
    fetched for the whole set in one query rather than once per pin."""
    facilities = list(facilities)
    coords = facility_registry.coordinates_for(db, [f.id for f in facilities])
    statuses = _statuses_for(db, facilities)
    batched = _default_badges_for(db, facilities) if badge_providers is None else None
    pins = []
    for fac in facilities:
        lat, lon = coords.get(fac.id, (None, None))
        if lat is None:
            continue
        status, freshness, availability = statuses.get(fac.id, (None, None, None))
        capacity = (fac.attributes or {}).get("capacity") if availability is not None else None
        badges = (
            list(batched.get(fac.id, ()))
            if batched is not None
            else [b for provider in badge_providers if (b := provider(db, fac)) is not None]
        )
        pins.append(
            _build_pin(fac, lat, lon, status, badges, freshness, availability, capacity)
        )
    return pins


def clusters_for(db: Session, facilities, precision_deg: float = 0.1) -> list[Cluster]:
    """AI-CONTEXT: cluster WITHOUT building pins.

    A clustered response contains a count, a centre and a dominant status — it never
    contains a pin. The old path built every pin in full, badges and all, and then
    discarded them: a statewide pan cost 2,155 queries to return 146 chips. Nothing
    here needs a badge, a name or a shape, so nothing here asks for one."""
    facilities = list(facilities)
    coords = facility_registry.coordinates_for(db, [f.id for f in facilities])
    statuses = _statuses_for(db, facilities)
    buckets: dict[tuple[int, int], list[tuple[float, float, str | None]]] = {}
    for fac in facilities:
        lat, lon = coords.get(fac.id, (None, None))
        if lat is None:
            continue
        status = (statuses.get(fac.id) or (None,))[0]
        buckets.setdefault(
            (round(lat / precision_deg), round(lon / precision_deg)), []
        ).append((lat, lon, status))
    clusters = []
    for members in buckets.values():
        counts: dict[str, int] = {}
        for _, _, status in members:
            if status is not None:
                counts[status] = counts.get(status, 0) + 1
        clusters.append(
            Cluster(
                count=len(members),
                center_lat=sum(m[0] for m in members) / len(members),
                center_lon=sum(m[1] for m in members) / len(members),
                dominant_status=max(counts, key=counts.get) if counts else None,
            )
        )
    return clusters


def _pin_for(db: Session, facility, badge_providers) -> Pin:
    lat, lon = facility_registry.coordinates(db, facility)
    status, freshness, availability = _parking_status(db, facility)
    capacity = (facility.attributes or {}).get("capacity") if availability is not None else None
    badges = [b for provider in badge_providers if (b := provider(db, facility)) is not None]
    return _build_pin(facility, lat, lon, status, badges, freshness, availability, capacity)


# AI-CONTEXT: None means EVERY type; an empty list means NO types. They were the same
# thing here — both falsy, both answered "all" — and a caller that filtered its type
# list down to nothing got the whole registry back instead of nothing. A5 walked into
# it switching the Service preset off: the kill switch returned every facility in the
# viewport. "No filter" and "filtered to nothing" are opposite instructions.
def _facilities_in_area(db: Session, lat, lon, radius_m, facility_types):
    if facility_types is not None and len(facility_types) == 0:
        return []
    if not facility_types:
        return facility_registry.nearest(db, lat, lon, radius_m)
    seen: dict = {}
    for ftype in facility_types:
        for fac in facility_registry.nearest(db, lat, lon, radius_m, facility_type=ftype):
            seen[fac.id] = fac
    return list(seen.values())


def facilities_in_area(db: Session, center_lat, center_lon, radius_m, facility_types=None):
    """The rows, before anything is built from them. Exposed so a caller can FILTER and
    COUNT on cheap data and only then decide whether it needs pins at all."""
    return _facilities_in_area(db, center_lat, center_lon, radius_m, facility_types)


def overlay_pins(
    db: Session,
    center_lat: float,
    center_lon: float,
    radius_m: float,
    facility_types=None,
    badge_providers=None,
) -> list[Pin]:
    facilities = _facilities_in_area(db, center_lat, center_lon, radius_m, facility_types)
    return pins_for(db, facilities, badge_providers)


def _facilities_in_bbox(db, min_lat, min_lon, max_lat, max_lon, facility_types):
    if facility_types is not None and len(facility_types) == 0:
        return []
    if not facility_types:
        return facility_registry.in_bbox(db, min_lat, min_lon, max_lat, max_lon)
    seen: dict = {}
    for ftype in facility_types:
        for fac in facility_registry.in_bbox(
            db, min_lat, min_lon, max_lat, max_lon, facility_type=ftype
        ):
            seen[fac.id] = fac
    return list(seen.values())


def facilities_in_bbox(db: Session, min_lat, min_lon, max_lat, max_lon, facility_types=None):
    return _facilities_in_bbox(db, min_lat, min_lon, max_lat, max_lon, facility_types)


def overlay_pins_bbox(
    db: Session,
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    facility_types=None,
    badge_providers=None,
) -> list[Pin]:
    facilities = _facilities_in_bbox(db, min_lat, min_lon, max_lat, max_lon, facility_types)
    return pins_for(db, facilities, badge_providers)


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
                services=list((fac.attributes or {}).get("services") or []),
            )
        )
    entries.sort(key=lambda e: e.distance_m)
    return entries

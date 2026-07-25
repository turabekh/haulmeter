"""AI-CONTEXT: source adapters for F2 real-POI ingestion (PRD §12).

Each adapter is a pure `parse(raw) -> [StagedRecord]` (tested against committed
fixtures) plus a monkeypatch-able HTTP/read seam (live pulls happen only from make
targets, never in CI). Sources: NTAD (BTS truck-stop parking, authoritative
capacity), TPIMS (MAASTO real-time availability), OSM (Geofabrik extracts, ODbL),
and a chain-locator STUB (no scraping — ToS review pending). Never Google Places.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from ..enums import FacilityType, SourceKind
from .normalize import normalize_name

# reportedAvailable="Low" (TPIMS) is a category, not a number — it must NEVER hit an
# int parse (condition A). Represent it with this sentinel.
LOW = "low"


@dataclass
class StagedRecord:
    source_kind: SourceKind
    external_ref: str
    name: str
    lat: float
    lon: float
    facility_type: FacilityType
    attributes: dict = field(default_factory=dict)
    raw_payload: dict = field(default_factory=dict)


@dataclass
class DynamicStatus:
    """A TPIMS dynamic availability reading for one site (feeds the M1 belief)."""

    site_id: str
    reported_at: datetime
    available: int | str | None  # int, LOW, or None
    capacity: int | None
    trend: str | None
    open: bool
    trust_data: bool


class SourceAdapter(Protocol):
    def parse(self, raw: object) -> list[StagedRecord]: ...


# --- NTAD (BTS Truck Stop Parking, ArcGIS FeatureServer) ---
def _ntad_type(name: str) -> FacilityType:
    return FacilityType.rest_area if "rest area" in name.lower() else FacilityType.truck_stop


def parse_ntad(geojson: dict) -> list[StagedRecord]:
    out: list[StagedRecord] = []
    for feature in geojson.get("features", []):
        props = feature.get("properties") or {}
        geom = feature.get("geometry") or {}
        coords = geom.get("coordinates") or [None, None]
        lon, lat = coords[0], coords[1]
        if lat is None or lon is None:
            continue
        raw_name = props.get("nhs_rest_stop") or ""
        name = normalize_name(raw_name) or f"Truck parking {props.get('OBJECTID')}"
        spots = props.get("number_of_spots")
        out.append(
            StagedRecord(
                source_kind=SourceKind.ntad,
                external_ref=str(props.get("OBJECTID")),
                name=name,
                lat=float(lat),
                lon=float(lon),
                facility_type=_ntad_type(name),
                attributes={
                    "capacity": int(spots) if spots not in (None, "") else None,
                    "city": props.get("municipality"),
                    "state": props.get("state"),
                    "highway": props.get("highway_route"),
                },
                raw_payload=props,
            )
        )
    return out


def fetch_ntad_page(base_url: str, offset: int, page_size: int) -> dict:
    import httpx

    params = {
        "where": "1=1",
        "outFields": "*",
        "outSR": "4326",
        "f": "geojson",
        "resultOffset": offset,
        "resultRecordCount": page_size,
    }
    resp = httpx.get(f"{base_url}/query", params=params, timeout=120.0)
    resp.raise_for_status()
    return resp.json()


def fetch_ntad_max_record_count(base_url: str, default: int = 1000) -> int:
    # service-reported page size (condition B) — the layer metadata's maxRecordCount
    import httpx

    try:
        resp = httpx.get(base_url, params={"f": "json"}, timeout=60.0)
        resp.raise_for_status()
        n = int(resp.json().get("maxRecordCount") or default)
        return n if n > 0 else default
    except Exception:
        return default


def iter_ntad_pages(base_url: str, page_size: int, get_page=fetch_ntad_page):
    # paginate by the service-reported page size; stop on a short page unless the
    # server flags exceededTransferLimit (condition B).
    offset = 0
    while True:
        page = get_page(base_url, offset, page_size)
        feats = page.get("features") or []
        yield page
        exceeded = bool(page.get("exceededTransferLimit"))
        if not feats or (len(feats) < page_size and not exceeded):
            break
        offset += len(feats)


# --- TPIMS (MAASTO Truck Parking Data Exchange V2.2) ---
def parse_available(raw) -> int | str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if s.lower() == LOW:
        return LOW  # category, never int-parsed (condition A)
    if s.lower() in ("unknown", "n/a", ""):
        return None  # real IL feeds emit "Unknown" (not in spec) -> no reading
    try:
        return int(s)
    except ValueError:
        return None


def _parse_ts(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(UTC)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC)


def parse_tpims_static(records: list[dict]) -> list[StagedRecord]:
    out: list[StagedRecord] = []
    for r in records:
        loc = r.get("location") or {}
        lat, lon = loc.get("latitude"), loc.get("longitude")
        if lat is None or lon is None:
            continue
        name = normalize_name(r.get("name") or "") or f"Truck parking {r.get('siteId')}"
        ftype = FacilityType.truck_stop if r.get("ownership") == "PR" else FacilityType.rest_area
        out.append(
            StagedRecord(
                source_kind=SourceKind.tpims,
                external_ref=str(r.get("siteId")),
                name=name,
                lat=float(lat),
                lon=float(lon),
                facility_type=ftype,
                attributes={
                    "capacity": r.get("capacity"),
                    "amenities": r.get("amenities") or [],
                    "city": loc.get("city"),
                    "state": loc.get("state"),
                    "highway": r.get("relevantHighway"),
                    "ownership": r.get("ownership"),
                },
                raw_payload=r,
            )
        )
    return out


def _parse_trend(raw) -> str | None:
    # real IL feeds emit trend "Unknown" (not in spec) -> treat as no trend
    if raw is None or str(raw).strip().lower() == "unknown":
        return None
    return raw


def parse_tpims_dynamic(records: list[dict]) -> list[DynamicStatus]:
    out: list[DynamicStatus] = []
    for r in records:
        out.append(
            DynamicStatus(
                site_id=str(r.get("siteId")),
                reported_at=_parse_ts(r.get("timeStamp")),
                available=parse_available(r.get("reportedAvailable")),
                capacity=r.get("capacity"),
                trend=_parse_trend(r.get("trend")),
                open=bool(r.get("open")) if r.get("open") is not None else True,  # null -> open
                trust_data=bool(r.get("trustData")) if r.get("trustData") is not None else True,
            )
        )
    return out


def has_usable_reading(status: DynamicStatus) -> bool:
    # a belief needs a real signal: a known availability, or a closed station (which
    # is itself "no spots"). "Unknown"/absent availability on an OPEN station says
    # nothing — no belief, regardless of trustData (real IL feeds are mostly these).
    return status.available is not None or not status.open


def derive_parking_status(status: DynamicStatus) -> str:
    # map availability -> the existing {empty, some, full} vocabulary (design-prd §11.7);
    # no new status token invented.
    if not status.open:
        return "full"  # closed -> no usable spots
    avail = status.available
    if avail == LOW:
        return "some"  # few left
    if isinstance(avail, int):
        if avail <= 0:
            return "full"
        cap = status.capacity or 0
        if cap and avail <= max(1, round(cap * 0.25)):
            return "some"
        return "empty"
    return "some"  # unknown count but open -> conservative "some"


def fetch_tpims(url: str) -> list[dict]:
    import httpx

    resp = httpx.get(url, timeout=60.0)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else data.get("sites", [])


# --- OSM (Geofabrik extract, osmium-filtered GeoJSON) ---
def _osm_hgv(tags: dict) -> bool:
    # truck-relevant: a fuel/parking POI only counts if it admits heavy goods
    # vehicles — otherwise we'd ingest every gas station and parking lot in a state.
    return (
        tags.get("hgv") in ("yes", "designated")
        or tags.get("access") == "hgv"
        or tags.get("truck") == "yes"
    )


# AI-CONTEXT: E3.2 service-center granularity (PRD extension §E3, owner decision
# Q12 = ATTRIBUTES, not new kinds). A wash / tire bay / repair yard is the `repair`
# kind carrying a `services` list, because real sites are composite (a truck stop
# WITH a tire bay keeps both facts) and design-prd §11.1 says extra signals render
# as badges on existing pins, never as more pins. M13-FR7 reads the same list, so
# the service list has exactly one source of truth.
SERVICE_TIRE = "tire"
SERVICE_WASH = "wash"
SERVICE_REPAIR = "truck_repair"
SERVICE_MOBILE_REPAIR = "mobile_repair"
SERVICE_TOWING = "towing"
SERVICE_PARTS = "parts"
# E3.1: a truck scale. Carried as a SERVICE as well as a kind so that a weighbridge
# mapped inside an existing truck stop enriches that facility (E3.2's union rule)
# instead of planting a second pin on top of it.
SERVICE_SCALE = "scale"

_OSM_SERVICE_RULES = [
    (lambda t: t.get("shop") == "tyres" or t.get("service:vehicle:tyres") == "yes", SERVICE_TIRE),
    (
        lambda t: t.get("amenity") == "car_wash" or t.get("service:vehicle:car_wash") == "yes",
        SERVICE_WASH,
    ),
    (
        lambda t: (
            t.get("shop") in ("truck_repair", "car_repair")
            or t.get("service:vehicle:truck_repair") == "yes"
        ),
        SERVICE_REPAIR,
    ),
    (lambda t: t.get("service:vehicle:mobile_repair") == "yes", SERVICE_MOBILE_REPAIR),
    (
        lambda t: t.get("shop") == "truck_parts" or t.get("service:vehicle:parts") == "yes",
        SERVICE_PARTS,
    ),
    # E3.1: a weighbridge is also a SERVICE, which is what lets one mapped inside an
    # existing truck stop enrich that facility (E3.2's union rule) instead of
    # planting a second pin on top of it.
    (lambda t: _osm_is_weighbridge(t), SERVICE_SCALE),
]
# SERVICE_TOWING has no dependable OSM tag — it arrives from an admin edit or a
# claiming service-center vendor (M13-FR7), never from the extract.


def osm_services(tags: dict) -> list[str]:
    # every matching service, not the first — a yard that washes AND does tires is both
    return [name for rule, name in _OSM_SERVICE_RULES if rule(tags)]


# AI-CONTEXT: E3.1 weigh-station tags, taken from real OSM usage (taginfo, Jul 2026)
# rather than from the documentation's aspirations:
#   amenity=weighbridge    12,178 uses  -> the tag that actually carries these
#   amenity=weigh_station      38 uses  -> marginal but real, cheap to accept
#   highway=weigh_station       0 uses  -> DOES NOT EXIST; a rule for it would be dead code
#   amenity=vehicle_inspection 13,344   -> deliberately NOT mapped: MOT/state safety
#                                          inspection, nothing to do with weighing
_OSM_WEIGHBRIDGE_VALUES = ("weighbridge", "weigh_station")
# commercial scale brands. In the US the CAT Scale network dominates truck-stop
# weighing; a branded scale is a service a driver PAYS for, not an enforcement stop
# they are compelled into, and the two mean opposite things on a map.
_COMMERCIAL_SCALE_OPERATORS = ("cat scale", "certified scale", "truckers choice")


def _osm_is_weighbridge(tags: dict) -> bool:
    return tags.get("amenity") in _OSM_WEIGHBRIDGE_VALUES


def _osm_is_commercial_scale(tags: dict) -> bool:
    operator = " ".join(
        str(tags.get(key, "")) for key in ("operator", "brand", "name")
    ).lower()
    return any(brand in operator for brand in _COMMERCIAL_SCALE_OPERATORS)


_OSM_TYPE_RULES = [
    (lambda t: t.get("highway") in ("rest_area", "services"), FacilityType.rest_area),
    (lambda t: t.get("amenity") == "truck_stop", FacilityType.truck_stop),
    (lambda t: t.get("amenity") == "fuel" and _osm_hgv(t), FacilityType.fuel_station),
    (lambda t: t.get("amenity") == "parking" and _osm_hgv(t), FacilityType.parking_property),
    # a service POI only counts as a truck facility when it admits heavy goods
    # vehicles — otherwise every neighbourhood car wash lands in the registry.
    (lambda t: bool(osm_services(t)) and _osm_hgv(t), FacilityType.repair),
    # E3.1: a weighbridge. Commercial (CAT-scale style) and public enforcement
    # scales are different facts to a driver — one is a service, the other is a
    # stop you cannot skip — so they get different kinds. NOT hgv-gated: an
    # enforcement scale exists precisely FOR heavy vehicles whether or not the
    # mapper tagged access, and gating it would drop most of them.
    (lambda t: _osm_is_weighbridge(t) and _osm_is_commercial_scale(t), FacilityType.scale),
    (lambda t: _osm_is_weighbridge(t), FacilityType.weigh_station),
]


def _osm_type(tags: dict) -> FacilityType | None:
    for rule, ftype in _OSM_TYPE_RULES:
        if rule(tags):
            return ftype
    return None


def _centroid(geom: dict) -> tuple[float, float] | None:
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if gtype == "Point":
        return coords[1], coords[0]
    ring = coords
    while isinstance(ring, list) and ring and isinstance(ring[0][0], list):
        ring = ring[0]  # descend Polygon/MultiPolygon to a coordinate ring
    if isinstance(ring, list) and ring and isinstance(ring[0], list):
        lons = [p[0] for p in ring]
        lats = [p[1] for p in ring]
        return sum(lats) / len(lats), sum(lons) / len(lons)
    return None


def parse_osm(geojson: dict) -> list[StagedRecord]:
    out: list[StagedRecord] = []
    for feature in geojson.get("features", []):
        tags = feature.get("properties") or {}
        ftype = _osm_type(tags)
        if ftype is None:
            continue
        center = _centroid(feature.get("geometry") or {})
        if center is None:
            continue
        lat, lon = center
        osm_id = str(tags.get("@id") or tags.get("id") or feature.get("id") or f"{lat},{lon}")
        name = normalize_name(tags.get("name") or "") or f"{ftype.value.replace('_', ' ').title()}"
        amenities = []
        if tags.get("shower") == "yes" or tags.get("amenity") == "shower":
            amenities.append("showers")
        if tags.get("hgv") in ("yes", "designated") or tags.get("access") == "hgv":
            amenities.append("truck_parking")
        attributes = {"amenities": amenities, "osm_tags": tags}
        # E3.2: services ride alongside the kind, so a truck stop with a tire bay
        # keeps BOTH facts (the kind stays truck_stop; the service list gains "tire").
        services = osm_services(tags)
        if services:
            attributes["services"] = services
        out.append(
            StagedRecord(
                source_kind=SourceKind.osm,
                external_ref=osm_id,
                name=name,
                lat=float(lat),
                lon=float(lon),
                facility_type=ftype,
                attributes=attributes,
                raw_payload=tags,
            )
        )
    return out


def read_geojson_file(path: str) -> dict:
    import json

    with open(path) as fh:
        return json.load(fh)


# --- Chain locators (Pilot/Love's/TA) — STUB ONLY ---
class ChainLocatorAdapter:
    """AI-CONTEXT: source-adapter seam for chain locators. Deliberately unimplemented
    this session — scraping/API terms review is pending (PRD §12). Fails loud so no
    one wires a scraper by accident. Never scrape; never use Google Places."""

    def parse(self, raw: object) -> list[StagedRecord]:
        raise NotImplementedError(
            "chain-locator ingestion is a seam; ToS review pending — do not scrape"
        )

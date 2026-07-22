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
        ftype = (
            FacilityType.truck_stop if r.get("ownership") == "PR" else FacilityType.rest_area
        )
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


def parse_tpims_dynamic(records: list[dict]) -> list[DynamicStatus]:
    out: list[DynamicStatus] = []
    for r in records:
        out.append(
            DynamicStatus(
                site_id=str(r.get("siteId")),
                reported_at=_parse_ts(r.get("timeStamp")),
                available=parse_available(r.get("reportedAvailable")),
                capacity=r.get("capacity"),
                trend=r.get("trend"),
                open=bool(r.get("open")) if r.get("open") is not None else True,
                trust_data=bool(r.get("trustData")) if r.get("trustData") is not None else True,
            )
        )
    return out


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
_OSM_TYPE_RULES = [
    (lambda t: t.get("highway") in ("rest_area", "services"), FacilityType.rest_area),
    (lambda t: t.get("amenity") == "fuel", FacilityType.fuel_station),
    (lambda t: t.get("amenity") == "truck_stop", FacilityType.truck_stop),
    (lambda t: t.get("amenity") == "parking", FacilityType.parking_property),
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
        out.append(
            StagedRecord(
                source_kind=SourceKind.osm,
                external_ref=osm_id,
                name=name,
                lat=float(lat),
                lon=float(lon),
                facility_type=ftype,
                attributes={"amenities": amenities, "osm_tags": tags},
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

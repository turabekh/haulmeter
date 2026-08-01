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
    # AI-CONTEXT: this record describes an AMENITY AT a site rather than a site of
    # its own — a CAT scale in a Pilot's lot, not a place a driver navigates to as a
    # destination. Such a record merges into whatever facility it stands in, by
    # PROXIMITY alone, because its name ("Cat Scale") will never resemble its host's
    # ("Pilot") and the ordinary fuzzy-name dedupe therefore cannot see the two are
    # one place. Set by the adapter, which is the only layer that knows the tags.
    # See `colocated_host` in ..service.
    colocated_amenity: bool = False


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
# AI-CONTEXT: the tags the osmium extract must pass, and the ONLY copy of that list.
# `make osm-extract` renders its filter from here (scripts/osm_filter_args.py), so the
# extract and the rules below cannot drift.
#
# They HAD drifted, totally. The Makefile carried its own hand-kept list of five
# patterns, and six of the eight service rules read tags it never passed — measured
# across the filtered Wisconsin and Texas extracts, `shop=tyres`, `shop=truck_repair`,
# `shop=truck_parts` and `service:vehicle:*` appeared ZERO times in either. Those rules
# had never fired. `_osm_hgv` read `truck=yes` that never arrived either, and
# `fuel:diesel` — the tag E3.3 added so a Flying J carries its own diesel fact — only
# ever arrived on features admitted for some OTHER reason.
#
# A tag added here costs extract size and nothing else: a feature the type rules do not
# claim is skipped at parse time and never reaches the database.
OSM_EXTRACT_TAGS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("highway", ("rest_area", "services")),
    ("amenity", ("truck_stop", "fuel", "parking", "weighbridge", "weigh_station", "car_wash")),
    ("shop", ("tyres", "truck_repair", "car_repair", "truck_parts")),
    ("hgv", ()),
    ("access", ("hgv",)),
    ("truck", ("yes",)),
    ("fuel:diesel", ()),
    ("fuel:hgv_diesel", ()),
    ("service:vehicle:tyres", ()),
    ("service:vehicle:car_wash", ()),
    ("service:vehicle:truck_repair", ()),
    ("service:vehicle:mobile_repair", ()),
    ("service:vehicle:parts", ()),
)


def osm_extract_filter_args() -> list[str]:
    """osmium `tags-filter` selectors. `nwr/key=v1,v2` for a value list, `nwr/key` for
    any value."""
    return [
        f"nwr/{key}={','.join(values)}" if values else f"nwr/{key}"
        for key, values in OSM_EXTRACT_TAGS
    ]


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
# E3.3: diesel. Carried as a SERVICE as well as a kind for exactly the reason a scale
# is — a fuel island mapped inside a truck stop is a FACT ABOUT that site, and 474 of
# the 546 fuel stations in the first pull stood within 150 m of a destination that
# already had a pin. It is also what gates the M7 price badge: a badge drawn from the
# facility KIND can only appear on a pin the merge is about to remove, while one drawn
# from this list follows the fuel onto whichever pin survives.
SERVICE_FUEL = "fuel"

# the whole vocabulary, in one place, so a consumer offering these as choices cannot
# drift from what ingestion writes. WHO may set which of them is not decided here.
SERVICE_KINDS = (
    SERVICE_TIRE,
    SERVICE_WASH,
    SERVICE_REPAIR,
    SERVICE_MOBILE_REPAIR,
    SERVICE_TOWING,
    SERVICE_PARTS,
    SERVICE_SCALE,
    SERVICE_FUEL,
)

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
    # E3.3: the same treatment for diesel. Read from the site's OWN tags as well as
    # from a co-located pump, so a Flying J tagged `fuel:diesel=yes` carries the fact
    # whether or not OSM also mapped the island as a separate node.
    (lambda t: _osm_sells_diesel(t), SERVICE_FUEL),
]
# SERVICE_TOWING has no dependable OSM tag — it arrives from an admin edit or a
# claiming service-center vendor (M13-FR7), never from the extract.


def osm_services(tags: dict) -> list[str]:
    # every matching service, not the first — a yard that washes AND does tires is both
    return [name for rule, name in _OSM_SERVICE_RULES if rule(tags)]


# AI-CONTEXT: A5 — whether a service POI serves TRUCKS. Measured on the full Wisconsin
# extract (2,638 features carrying a service tag) rather than reasoned about, and the
# measurement inverted the obvious answer:
#
#   `_osm_hgv` matches ZERO of the 2,638. Not one. A repair shop is not an access-
#   controlled area, so nobody tags `hgv` on it — the only access tags present at all
#   are `customers` (19) and `private` (9). Gating services on `_osm_hgv`, as the type
#   rule did, meant the filter fix alone would have produced exactly nothing.
#
# What DOES separate them, hand-audited over all 76 matches:
#   · an explicitly truck-specific TAG — 30 features
#   · trucks NAMED in the business name — 57 features, and two-thirds of the real finds
#     carry no truck tag at all: "Diesel Doctors", "Portage Diesel Repair", "Truck
#     Country", "Ottery Brothers Truck Wash" are all plain `shop=car_repair`. So is
#     "TA Truck Service", and so is Love's. Dropping the name signal drops most of them.
#
# The remaining 2,562 are the car trade — 1,347 `shop=car_repair`, 1,060 `amenity=
# car_wash` — and they must stay out. A truck driver's map that answers "where can I
# get fixed" with a neighbourhood oil-change bay is worse than one that answers nothing.
#
# TERMS EARN THEIR PLACE ON THE DATA, which is why two obvious ones are missing:
#   · `fleet` — 13 of its 14 Wisconsin matches are "Fleet Farm", a regional retail
#     chain, whose CAR WASH would have become a truck repair facility. "Fleet XL" is
#     caught by its own `shop=truck_repair` tag, so the term buys nothing and costs 13.
#   · `trailer` — its one match is "…Trailer Sales & Accessories", a false positive.
#     Genuine "Truck & Trailer Repair" yards are caught by `truck`.
# Both are one-state measurements; a term that starts earning its place elsewhere can
# be added on the same evidence that removed these.
_TRUCK_NAME_TERMS = (
    "truck",
    "semi",
    "diesel",
    "big rig",
    "18 wheel",
    "18-wheeler",
    "freightliner",
    "peterbilt",
    "kenworth",
)
# tags that mean "trucks" on their own, with no access tag and no name needed
_TRUCK_EXPLICIT_TAGS = (
    ("shop", ("truck_repair", "truck_parts")),
    ("service:vehicle:truck_repair", ("yes",)),
    ("service:vehicle:parts", ("yes",)),
    ("service:vehicle:mobile_repair", ("yes",)),
)


def _osm_truck_named(tags: dict) -> bool:
    name = str(tags.get("name") or "").lower()
    return any(term in name for term in _TRUCK_NAME_TERMS)


def _osm_truck_explicit(tags: dict) -> bool:
    return any(tags.get(key) in values for key, values in _TRUCK_EXPLICIT_TAGS)


def osm_serves_trucks(tags: dict) -> bool:
    """`_osm_hgv` stays in the disjunction: it is the existing rule, it costs nothing,
    and a state that tags access properly should still be believed."""
    return _osm_hgv(tags) or _osm_truck_explicit(tags) or _osm_truck_named(tags)


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
    operator = " ".join(str(tags.get(key, "")) for key in ("operator", "brand", "name")).lower()
    return any(brand in operator for brand in _COMMERCIAL_SCALE_OPERATORS)


def placeholder_name(ftype: FacilityType) -> str:
    """The name an UNNAMED feature gets — "Parking Property", "Rest Area". Exposed
    because a merge has to be able to tell a placeholder from a name somebody chose:
    collapsing a branded pump into an unnamed host would take the only real name on
    the site off the map."""
    return ftype.value.replace("_", " ").title()


def _osm_sells_diesel(tags: dict) -> bool:
    if tags.get("fuel:diesel") == "yes" or tags.get("fuel:hgv_diesel") == "yes":
        return True
    return tags.get("amenity") == "fuel" and _osm_hgv(tags)


# AI-CONTEXT: E3.3. A branded highway service area is a TRUCK STOP, not a rest area.
# `highway=services` is how every US chain is tagged and it sat above the truck-stop
# rule, so 309 Pilots, Flying Js, Love's and TAs filed themselves as rest areas and
# NOT ONE facility in the first pull was typed truck_stop from this tag. That put them
# outside the Fuel preset entirely — a Flying J carrying `fuel:diesel=yes` in its own
# tags was absent from the one preset built to find it.
#
# The discriminator is the BRAND, and it was measured rather than chosen. `hgv` alone
# fails: 135 of the matching rows are public rest areas ("Rest Area", "I-80 EB (trucks
# Only)") that admit trucks and are not truck stops. Requiring a brand as well leaves
# 347 rows whose brands are Love's (124), Pilot (102), Flying J (37), TA (37), Petro
# (17), ONE9, Road Ranger, Mr. Fuel, Sapp Bros. and Waspy's — every one a chain.
# Reordering alone would have fixed nothing: `amenity=truck_stop` appears on ZERO of
# them, which is why this tests the brand instead of the rule order.
def _osm_is_branded_service_area(tags: dict) -> bool:
    return (
        tags.get("highway") in ("rest_area", "services")
        and bool(str(tags.get("brand", "")).strip())
        and _osm_hgv(tags)
    )


# AI-CONTEXT: measured, not assumed. The first Wisconsin/Indiana/Iowa/Minnesota pull
# produced 253 commercial scales, of which 239 stood within 150 m of a facility that
# already had a pin (169 within 50 m) — every one of them a second pin on top of a
# Pilot, a Love's or a rest area. A branded scale is an amenity AT a truck stop, so
# it is marked co-located and merges into its host by proximity.
#
# A PUBLIC weigh station is deliberately NOT co-located: it is a destination in its
# own right, a driver navigates to it, and 69 of the 103 found stood more than 2 km
# from anything else. The 22 that sit beside a rest area really are separate places
# that happen to be adjacent, and collapsing them would lose the scale entirely.
#
# Takes the RESOLVED type, not the tags alone. The two were derived independently at
# first, and a weighbridge that another rule had claimed came out flagged co-located
# while typed something else entirely — which made `_contribution` compare two kinds
# that happened to be equal and let the tenant's identity through. Deriving one from
# the other means they cannot disagree again.
#
# E3.3 adds fuel on the same evidence and the same reasoning: 474 of 546 fuel stations
# stood within 150 m of a destination pin, so the map drew a truck stop and its own
# fuel island as two places 30 m apart — and the PRICE landed on the island, which
# carries the pump's name ("Pilot") rather than the site's ("Flying J Travel Center").
# Unlike a scale, a fuel station IS a destination when it stands alone, which needs no
# special case: `colocated_host` returns None when nothing hosts it and it keeps its
# own pin. What it does need is `fuel_station` OUT of COLOCATED_HOST_TYPES, so the two
# rules below still hold and one pump cannot host another.
# A5 adds `repair` on the same evidence and the same reasoning. Measured on the new
# Wisconsin extract: 10 of the 65 repair records stand within the 150 m co-location
# radius of a destination facility, and they are the service bays of the truck stops
# a driver already knows — TA Truck Service (×3), Love's Truck Care, Bosselman's Boss
# Shop. As their own pins they would be a second TA beside every TA. Standing alone a
# repair shop IS a destination, which needs no special case: `colocated_host` returns
# None and it keeps its pin (exactly the fuel_station argument).
_COLOCATED_AMENITY_TYPES = frozenset(
    {FacilityType.scale, FacilityType.fuel_station, FacilityType.repair}
)


def _osm_is_colocated_amenity(tags: dict, ftype: FacilityType) -> bool:
    if ftype is FacilityType.scale:
        return _osm_is_commercial_scale(tags)
    return ftype in _COLOCATED_AMENITY_TYPES


_OSM_TYPE_RULES = [
    # E3.3: a BRANDED service area outranks the bare `highway=services` catch-all,
    # for the same reason the weighbridge rules outrank the generic repair one below:
    # a specific, unambiguous tag must beat a catch-all.
    (lambda t: _osm_is_branded_service_area(t), FacilityType.truck_stop),
    (lambda t: t.get("highway") in ("rest_area", "services"), FacilityType.rest_area),
    (lambda t: t.get("amenity") == "truck_stop", FacilityType.truck_stop),
    (lambda t: t.get("amenity") == "fuel" and _osm_hgv(t), FacilityType.fuel_station),
    (lambda t: t.get("amenity") == "parking" and _osm_hgv(t), FacilityType.parking_property),
    # E3.1: a weighbridge. Commercial (CAT-scale style) and public enforcement
    # scales are different facts to a driver — one is a service, the other is a
    # stop you cannot skip — so they get different kinds. NOT hgv-gated: an
    # enforcement scale exists precisely FOR heavy vehicles whether or not the
    # mapper tagged access, and gating it would drop most of them.
    #
    # These sit ABOVE the generic repair rule deliberately. Making a weighbridge a
    # SERVICE (so it can enrich its host) also made it match "some service + hgv",
    # and with the order reversed a CAT scale tagged hgv=designated filed itself as
    # a REPAIR SHOP — found in the first real pull. A specific, unambiguous tag must
    # outrank a catch-all.
    (lambda t: _osm_is_weighbridge(t) and _osm_is_commercial_scale(t), FacilityType.scale),
    (lambda t: _osm_is_weighbridge(t), FacilityType.weigh_station),
    # a service POI only counts as a truck facility when it serves TRUCKS — otherwise
    # every neighbourhood car wash lands in the registry. `_osm_hgv` alone was the
    # gate and it matched nothing at all here; see `osm_serves_trucks` for the measured
    # replacement it is now one third of.
    (lambda t: bool(osm_services(t)) and osm_serves_trucks(t), FacilityType.repair),
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
        name = normalize_name(tags.get("name") or "") or placeholder_name(ftype)
        amenities = []
        if tags.get("shower") == "yes" or tags.get("amenity") == "shower":
            amenities.append("showers")
        if tags.get("hgv") in ("yes", "designated") or tags.get("access") == "hgv":
            amenities.append("truck_parking")
        attributes = {"amenities": amenities, "osm_tags": tags}
        # A5: promote contact facts OUT of the raw blob. They were always in it — 633
        # facilities in the live registry carry `phone` inside `osm_tags` and 245 carry
        # `opening_hours` — and nothing read them, so not one facility in the registry
        # had a phone number a driver could tap. Absent rather than empty: the card
        # asks whether there IS a phone, and "" answers yes.
        for key, tag_names in (
            ("phone", ("phone", "contact:phone")),
            ("opening_hours", ("opening_hours",)),
        ):
            value = next((str(tags[t]).strip() for t in tag_names if tags.get(t)), "")
            if value:
                attributes[key] = value
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
                colocated_amenity=_osm_is_colocated_amenity(tags, ftype),
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

from geoalchemy2 import Geography
from geoalchemy2.elements import WKTElement
from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session

from . import geocode as geocode_module
from . import geohash as geohash_util
from .enums import FacilityStatus, FacilityType, SourceKind
from .models import Facility, FacilitySource

CANDIDATE_SOURCES = {SourceKind.user_checkin}
DEDUP_GEOHASH_PRECISION = 7
DEDUP_NAME_SIMILARITY = 0.4


def _point(lat: float, lon: float) -> WKTElement:
    return WKTElement(f"POINT({lon} {lat})", srid=4326)


def create_facility(
    db: Session,
    facility_type: FacilityType,
    name: str,
    lat: float,
    lon: float,
    source_kind: SourceKind = SourceKind.admin,
    address: str | None = None,
    attributes: dict | None = None,
    hours: dict | None = None,
    is_dev: bool = False,
) -> Facility:
    facility = Facility(
        facility_type=facility_type,
        status=FacilityStatus.confirmed,
        name=name,
        address=address,
        geom=_point(lat, lon),
        geohash=geohash_util.encode(lat, lon),
        attributes=attributes or {},
        hours=hours or {},
        is_dev=is_dev,
    )
    db.add(facility)
    db.flush()
    add_source(db, facility, source_kind)
    return facility


def create_candidate_from_checkin(
    db: Session,
    facility_type: FacilityType,
    name: str,
    lat: float,
    lon: float,
) -> Facility:
    facility = Facility(
        facility_type=facility_type,
        status=FacilityStatus.candidate,
        name=name,
        geom=_point(lat, lon),
        geohash=geohash_util.encode(lat, lon),
        attributes={},
        hours={},
    )
    db.add(facility)
    db.flush()
    add_source(db, facility, SourceKind.user_checkin)
    return facility


def add_source(
    db: Session,
    facility: Facility,
    source_kind: SourceKind,
    external_ref: str | None = None,
    attributes: dict | None = None,
) -> FacilitySource:
    source = FacilitySource(
        facility_id=facility.id,
        source_kind=source_kind,
        external_ref=external_ref,
        attributes=attributes or {},
    )
    db.add(source)
    db.flush()
    return source


def confirm_with_second_signal(
    db: Session,
    facility: Facility,
    source_kind: SourceKind,
    external_ref: str | None = None,
) -> Facility:
    add_source(db, facility, source_kind, external_ref)
    db.refresh(facility)
    distinct_kinds = {s.source_kind for s in facility.sources}
    if facility.status == FacilityStatus.candidate and len(distinct_kinds) >= 2:
        facility.status = FacilityStatus.confirmed
        db.flush()
    return facility


# the bar for OFFERING a match to a human. Lower than DEDUP_NAME_SIMILARITY, which
# decides whether an ingest run merges two rows unattended: a wrong automatic merge
# corrupts the registry, while a wrong suggestion costs the driver one tap to reject.
SEARCH_NAME_SIMILARITY = 0.25


def search_by_name(db: Session, name: str, limit: int = 5) -> list[tuple[Facility, float]]:
    """Find facilities by NAME alone, best match first, each with its score.

    `find_duplicate_candidates` blocks on a geohash, so it needs coordinates. A rate
    confirmation gives an address string and no coordinates, and this codebase has no
    geocoder — so a text search is what a parsed load can actually offer. The score
    travels with the row because the caller is deciding whether to show a human a
    suggestion, not whether to merge two records unattended.
    """
    if not (name or "").strip():
        return []
    score = func.similarity(Facility.name, name)
    stmt = (
        select(Facility, score)
        .where(Facility.status != FacilityStatus.merged)
        .where(score >= SEARCH_NAME_SIMILARITY)
        .order_by(score.desc())
        .limit(limit)
    )
    return [(row[0], float(row[1])) for row in db.execute(stmt)]


def find_duplicate_candidates(db: Session, name: str, lat: float, lon: float) -> list[Facility]:
    block = geohash_util.encode(lat, lon, DEDUP_GEOHASH_PRECISION)
    stmt = (
        select(Facility)
        .where(Facility.geohash.like(f"{block}%"))
        .where(Facility.status != FacilityStatus.merged)
        .where(~Facility.is_dev)  # real-data ingest never merges into DEV_SEED facilities
        .where(func.similarity(Facility.name, name) >= DEDUP_NAME_SIMILARITY)
        .order_by(func.similarity(Facility.name, name).desc())
    )
    return list(db.scalars(stmt))


# AI-CONTEXT: a co-located amenity merges into the site it stands in by PROXIMITY
# alone (see StagedRecord.colocated_amenity). Two rules keep this from becoming a
# general proximity merge, which would collapse the Pilot and the Love's across the
# road into one pin:
#   · only a record the ADAPTER marked co-located may take this path, and
#   · only a DESTINATION may host one, so amenities never chain into each other.
# 150 m is the measured figure, not a guess: it covers 239 of the 253 commercial
# scales in the first four-state pull while a truck-stop lot is itself ~200 m across,
# so the radius stays inside "the same site" rather than reaching the next exit.
COLOCATED_RADIUS_M = 150.0
COLOCATED_HOST_TYPES = frozenset(
    {
        FacilityType.truck_stop,
        FacilityType.rest_area,
        FacilityType.fuel_station,
        FacilityType.parking_property,
        FacilityType.repair,
        FacilityType.shipper_receiver,
    }
)


def colocated_host(
    db: Session, lat: float, lon: float, radius_m: float = COLOCATED_RADIUS_M
) -> Facility | None:
    """The nearest destination facility this amenity stands in, or None if it stands
    alone — in which case it earns a pin of its own."""
    point = cast(_point(lat, lon), Geography)
    stmt = (
        select(Facility)
        .where(Facility.status != FacilityStatus.merged)
        .where(~Facility.is_dev)
        .where(Facility.facility_type.in_(COLOCATED_HOST_TYPES))
        .where(func.ST_DWithin(cast(Facility.geom, Geography), point, radius_m))
        .order_by(func.ST_Distance(cast(Facility.geom, Geography), point))
        .limit(1)
    )
    return db.scalars(stmt).first()


def merge_facilities(db: Session, canonical: Facility, duplicate: Facility) -> Facility:
    for source in list(duplicate.sources):
        source.facility_id = canonical.id
    duplicate.status = FacilityStatus.merged
    duplicate.merged_into_id = canonical.id
    db.flush()
    return canonical


def resolve_canonical(db: Session, facility_id) -> Facility | None:
    facility = db.get(Facility, facility_id)
    seen = set()
    while facility is not None and facility.merged_into_id is not None:
        if facility.id in seen:
            break
        seen.add(facility.id)
        facility = db.get(Facility, facility.merged_into_id)
    return facility


def get_facility(db: Session, facility_id) -> Facility | None:
    return db.get(Facility, facility_id)


def facility_for_source(db: Session, source_kind: SourceKind, external_ref: str) -> Facility | None:
    # resolve the canonical facility a given source record maps to (e.g. a TPIMS
    # siteId -> facility), following any merges.
    source = db.scalar(
        select(FacilitySource).where(
            FacilitySource.source_kind == source_kind,
            FacilitySource.external_ref == external_ref,
        )
    )
    if source is None:
        return None
    return resolve_canonical(db, source.facility_id)


def nearest(
    db: Session,
    lat: float,
    lon: float,
    radius_m: float,
    facility_type: FacilityType | None = None,
) -> list[Facility]:
    point = _point(lat, lon)
    stmt = (
        select(Facility)
        .where(Facility.status != FacilityStatus.merged)
        .where(func.ST_DWithin(cast(Facility.geom, Geography), cast(point, Geography), radius_m))
        .order_by(func.ST_Distance(cast(Facility.geom, Geography), cast(point, Geography)))
    )
    if facility_type is not None:
        stmt = stmt.where(Facility.facility_type == facility_type)
    return list(db.scalars(stmt))


# AI-CONTEXT: straight-line metres from one origin to a set of known facilities, in
# ONE query. Facility geometry belongs to F2, so consumers that need a distance ask
# for it here rather than growing their own haversine — the same discipline that
# keeps M13's corridor layer reading M1's geometry instead of duplicating it.
#
# What this returns is a DIRECT distance, not a driving distance. Callers rendering
# it to a driver must not imply routing precision (§11.7): truck routing is PRD §17
# Q9 and unresolved, so no arrival time can honestly be derived from this number.
def facility_distances(db: Session, facility_ids, lat: float, lon: float) -> dict:
    ids = list(facility_ids)
    if not ids:
        return {}
    point = _point(lat, lon)
    rows = db.execute(
        select(
            Facility.id,
            func.ST_Distance(cast(Facility.geom, Geography), cast(point, Geography)),
        ).where(Facility.id.in_(ids))
    ).all()
    return {fid: float(metres) for fid, metres in rows}


BBOX_QUERY_LIMIT = 5000  # DB safety ceiling; the map clusters well before this


def in_bbox(
    db: Session,
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    facility_type: FacilityType | None = None,
) -> list[Facility]:
    # facilities intersecting the map viewport (the primary overlay mode). Includes
    # is_dev facilities — they must render for field-testing. Hard LIMIT is a safety
    # ceiling; the M1 layer clusters at density well before it.
    envelope = func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
    stmt = (
        select(Facility)
        .where(Facility.status != FacilityStatus.merged)
        .where(func.ST_Intersects(Facility.geom, envelope))
    )
    if facility_type is not None:
        stmt = stmt.where(Facility.facility_type == facility_type)
    return list(db.scalars(stmt.limit(BBOX_QUERY_LIMIT)))


# AI-CONTEXT: M13-FR7 needs to find a facility BY NAME from a desk — every other
# lookup here is geographic, and a claimant typing their own business name has no
# viewport. The `services` list is the E3.2 one source of truth for "is there
# anything here to claim", so a facility without one is never a search result: the
# claimable set is answered by the picker rather than by a rejection after the fact.
# `attributes` is a JSON (not JSONB) column, so the services test is applied in
# Python over a name-narrowed window rather than pushed into SQL.
SERVICE_SEARCH_WINDOW = 200


def search_service_facilities(db: Session, q: str, limit: int = 20) -> list[Facility]:
    term = " ".join((q or "").strip().split())
    if len(term) < 2:
        return []
    stmt = (
        select(Facility)
        .where(Facility.status != FacilityStatus.merged)
        .where(Facility.merged_into_id.is_(None))
        .where(Facility.name.ilike(f"%{term}%"))
        .order_by(func.length(Facility.name), Facility.name)
        .limit(SERVICE_SEARCH_WINDOW)
    )
    out = []
    for facility in db.scalars(stmt):
        if (facility.attributes or {}).get("services"):
            out.append(facility)
            if len(out) >= limit:
                break
    return out


def set_lot_polygon(db: Session, facility: Facility, polygon_wkt: str) -> Facility:
    facility.lot_polygon = WKTElement(polygon_wkt, srid=4326)
    db.flush()
    return facility


def contains_point(
    db: Session, facility: Facility, lat: float, lon: float, radius_m: float
) -> bool:
    point = _point(lat, lon)
    stmt = select(
        func.coalesce(
            func.ST_Contains(Facility.lot_polygon, point),
            func.ST_DWithin(cast(Facility.geom, Geography), cast(point, Geography), radius_m),
        )
    ).where(Facility.id == facility.id)
    return bool(db.execute(stmt).scalar())


def coordinates(db: Session, facility: Facility) -> tuple[float, float]:
    lon, lat = db.execute(
        select(func.ST_X(Facility.geom), func.ST_Y(Facility.geom)).where(Facility.id == facility.id)
    ).one()
    return lat, lon


def facility_locality(db: Session, facility: Facility) -> str | None:
    """Where this facility is, in the words a driver uses (§23 entry 76).

    AI-CONTEXT: the registry legitimately holds facilities that share a name — a chain
    with a warehouse in two cities, or a duplicate left behind by an earlier defect —
    and any screen that offers them as choices must say which is which. Resolved once
    and cached on the row, because a reverse geocode per render of a picker is a
    network call the driver waits for on every open.

    `address` first: a stated address is the driver's own answer and beats the
    geocoder's guess about a coordinate.
    """
    attributes = dict(facility.attributes or {})
    if attributes.get("locality"):
        return attributes["locality"]
    if facility.address:
        parts = [p.strip() for p in facility.address.split(",") if p.strip()]
        if len(parts) >= 2:
            # "8450 Lakeside Ave, Columbus, OH 43228" -> "Columbus, OH"
            region = parts[-1].split()[0] if parts[-1] else ""
            resolved = f"{parts[-2]}, {region}".strip(", ")
        else:
            resolved = facility.address
    else:
        lat, lon = coordinates(db, facility)
        resolved = geocode_module.locality(lat, lon)
    if not resolved:
        return None
    attributes["locality"] = resolved
    facility.attributes = attributes
    db.flush()
    return resolved

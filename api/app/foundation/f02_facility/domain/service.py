from geoalchemy2 import Geography
from geoalchemy2.elements import WKTElement
from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session

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


def find_duplicate_candidates(db: Session, name: str, lat: float, lon: float) -> list[Facility]:
    block = geohash_util.encode(lat, lon, DEDUP_GEOHASH_PRECISION)
    stmt = (
        select(Facility)
        .where(Facility.geohash.like(f"{block}%"))
        .where(Facility.status != FacilityStatus.merged)
        .where(func.similarity(Facility.name, name) >= DEDUP_NAME_SIMILARITY)
        .order_by(func.similarity(Facility.name, name).desc())
    )
    return list(db.scalars(stmt))


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

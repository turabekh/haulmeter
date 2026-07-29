"""AI-CONTEXT: F2 ingestion pipeline (PRD §12 / §7.2). Every source lands the same
way: stage (raw retained) -> normalize -> geohash blocking + fuzzy dedupe ->
canonical upsert with provenance + confidence. Idempotent: the same input twice
never duplicates a facility (keyed on (source_kind, external_ref), then geohash+name
dedupe). Conflict resolution is DATA, not ifs (PRD §12: chain > NTAD > OSM for
amenities; NTAD wins capacity counts).
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import geohash as geohash_util
from ..enums import SourceKind
from ..models import Facility, FacilitySource, SourceRecord
from ..service import (
    add_source,
    colocated_host,
    create_facility,
    find_duplicate_candidates,
    host_should_adopt_name,
    resolve_canonical,
)
from .adapters import StagedRecord

# amenity/attribute conflicts: higher priority wins per key (PRD §12)
AMENITY_PRIORITY = {
    SourceKind.chain_list: 3,
    SourceKind.ntad: 2,
    SourceKind.fhwa: 2,
    SourceKind.tpims: 2,
    SourceKind.admin: 2,
    SourceKind.osm: 1,
    SourceKind.user_checkin: 0,
}
# list-valued attributes merged by UNION across sources rather than overwritten
# by the highest-priority one (E3.2 — see _recompute_canonical)
UNION_KEYS = frozenset({"services"})
# capacity/spot counts: NTAD is authoritative (PRD §12)
CAPACITY_PRIORITY = {
    SourceKind.ntad: 3,
    SourceKind.tpims: 2,
    SourceKind.fhwa: 2,
    SourceKind.chain_list: 1,
    SourceKind.osm: 1,
    SourceKind.admin: 1,
    SourceKind.user_checkin: 0,
}


@dataclass
class IngestStats:
    staged: int = 0
    created: int = 0
    matched: int = 0  # attached to an existing facility (dedupe or re-run)
    skipped: int = 0
    facility_ids: set = field(default_factory=set)


def _confidence(sources: list[FacilitySource]) -> float:
    kinds = {s.source_kind for s in sources}
    top = max((AMENITY_PRIORITY.get(k, 0) for k in kinds), default=0)
    return round(min(1.0, 0.5 + 0.15 * len(kinds) + 0.05 * top), 3)


def _recompute_canonical(db: Session, facility: Facility) -> None:
    # merge each source's contributed attributes by priority (ascending -> higher
    # priority overwrites), then apply the capacity rule (NTAD wins), then confidence.
    db.refresh(facility)
    sources = list(facility.sources)
    merged: dict = {}
    for src in sorted(sources, key=lambda s: AMENITY_PRIORITY.get(s.source_kind, 0)):
        for key, value in (src.attributes or {}).items():
            if value is None or value == []:
                continue
            if key in UNION_KEYS:
                # E3.2: a service list is ADDITIVE across sources, not overwritten —
                # an OSM extract knowing "tire" and an admin edit knowing "towing"
                # both describe the same yard, so the higher-priority source must not
                # erase the other's knowledge. A deliberate exception to
                # overwrite-by-priority, in the same spirit as the capacity rule below.
                merged[key] = sorted({*merged.get(key, []), *value})
            else:
                merged[key] = value
    cap_source = max(
        (s for s in sources if (s.attributes or {}).get("capacity") is not None),
        key=lambda s: CAPACITY_PRIORITY.get(s.source_kind, 0),
        default=None,
    )
    if cap_source is not None:
        merged["capacity"] = cap_source.attributes["capacity"]
    facility.attributes = merged
    facility.confidence = _confidence(sources)
    db.flush()


def _contribution(rec: StagedRecord, facility: Facility) -> dict:
    """What this record may say about the facility it landed on.

    AI-CONTEXT: a co-located amenity that merged into a HOST contributes only what it
    knows about the SITE — its own name, tags, phone and website describe the scale,
    and letting them through would dress a Pilot in its tenant's identity. Landing on
    its own pin (nothing nearby, or fuzzy-matched to another scale) it contributes
    everything, because there it IS the place.

    This is applied on EVERY write, not only the first merge, because the re-ingest
    path replaces a source's attributes wholesale — narrowing once at merge time was
    silently undone by the next pull, which is how 203 truck stops briefly ended up
    advertising catscale.com.
    """
    if rec.colocated_amenity and facility.facility_type != rec.facility_type:
        return {k: v for k, v in rec.attributes.items() if k in UNION_KEYS}
    return rec.attributes


def stage_record(db: Session, rec: StagedRecord, batch_id: str | None = None) -> SourceRecord:
    # idempotent staging row keyed on (source_kind, external_ref); raw retained
    existing = db.scalar(
        select(SourceRecord).where(
            SourceRecord.source_kind == rec.source_kind,
            SourceRecord.external_ref == rec.external_ref,
        )
    )
    gh = geohash_util.encode(rec.lat, rec.lon)
    if existing is None:
        existing = SourceRecord(source_kind=rec.source_kind, external_ref=rec.external_ref)
        db.add(existing)
    existing.batch_id = batch_id
    existing.raw_payload = rec.raw_payload
    existing.normalized = {"name": rec.name, "attributes": rec.attributes}
    existing.name = rec.name
    existing.lat = rec.lat
    existing.lon = rec.lon
    existing.geohash = gh
    existing.facility_type = rec.facility_type
    db.flush()
    return existing


def upsert_record(
    db: Session, rec: StagedRecord, batch_id: str | None = None
) -> tuple[Facility, str]:
    """Returns (facility, outcome) where outcome is 'created' | 'matched' | 'updated'."""
    staged = stage_record(db, rec, batch_id)

    # 1. seen this exact (source, external_ref) before? -> update its facility in place
    existing_src = db.scalar(
        select(FacilitySource).where(
            FacilitySource.source_kind == rec.source_kind,
            FacilitySource.external_ref == rec.external_ref,
        )
    )
    if existing_src is not None:
        facility = resolve_canonical(db, existing_src.facility_id)
        existing_src.attributes = _contribution(rec, facility)
        outcome = "updated"
    else:
        # 2. cross-source dedupe: same geohash block + fuzzy name -> same physical site
        candidates = find_duplicate_candidates(db, rec.name, rec.lat, rec.lon)
        host = colocated_host(db, rec.lat, rec.lon) if rec.colocated_amenity else None
        if candidates:
            facility = candidates[0]
            add_source(db, facility, rec.source_kind, rec.external_ref, rec.attributes)
            outcome = "matched"
        elif host is not None:
            # 2b. an amenity standing inside a destination is a FACT ABOUT that
            # destination, not a second place.
            #
            # The rename sits INSIDE this branch on purpose: a record that fuzzy-matched
            # a candidate above never merges into `host`, and renaming it there would
            # have retitled a facility this record does not belong to.
            if host_should_adopt_name(host, rec.name):
                # the host is an unnamed OSM feature; the pump carries the only real
                # name on the site, so the merge takes it across (§23 96)
                host.name = rec.name
                db.flush()
            facility = host
            add_source(
                db, facility, rec.source_kind, rec.external_ref, _contribution(rec, facility)
            )
            outcome = "matched"
        else:
            # 3. new canonical facility (authoritative source -> confirmed)
            facility = create_facility(
                db,
                rec.facility_type,
                rec.name,
                rec.lat,
                rec.lon,
                source_kind=rec.source_kind,
                attributes={},
            )
            src = db.scalar(select(FacilitySource).where(FacilitySource.facility_id == facility.id))
            src.external_ref = rec.external_ref
            src.attributes = rec.attributes
            db.flush()
            outcome = "created"

    _recompute_canonical(db, facility)
    staged.canonical_facility_id = facility.id
    db.flush()
    return facility, outcome


def ingest_records(
    db: Session, records: list[StagedRecord], batch_id: str | None = None
) -> IngestStats:
    stats = IngestStats()
    for rec in records:
        if rec.lat is None or rec.lon is None or not rec.external_ref:
            stats.skipped += 1
            continue
        facility, outcome = upsert_record(db, rec, batch_id)
        stats.staged += 1
        if outcome == "created":
            stats.created += 1
        else:
            stats.matched += 1
        stats.facility_ids.add(facility.id)
    return stats


__all__ = [
    "AMENITY_PRIORITY",
    "CAPACITY_PRIORITY",
    "UNION_KEYS",
    "IngestStats",
    "ingest_records",
    "stage_record",
    "upsert_record",
]

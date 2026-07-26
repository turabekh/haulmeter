"""AI-CONTEXT: one-off repair for facilities ingested BEFORE the co-located-amenity
rule existed (`make repair-scales`, `DRY_RUN=0` to apply).

The first four-state OSM pull created 253 commercial scales as facilities of their
own, 239 of them standing within 150 m of a truck stop that already had a pin,
because the fuzzy-name dedupe cannot see that "Cat Scale" and "Pilot" are one place.
The ingest path now merges them (StagedRecord.colocated_amenity), but re-running the
ingest does NOT fix the rows already written: an already-seen (source, external_ref)
takes the update-in-place branch and never revisits which facility it belongs to.

So this walks them once. For each `scale` facility standing inside a destination it
moves the OSM source onto the host, narrows that source's contribution to the service
fact (its name, phone and website describe the SCALE — merging them would overwrite
the host's identity with its tenant's), marks the scale merged, and recomputes the
host. `merge_facilities` is the sanctioned path, so nothing is deleted and every
`facility_id` anyone already holds still resolves.

Idempotent: a second run finds nothing to do.
"""

import os
import sys

import db_registry

db_registry.import_all_models()

from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.foundation.f02_facility.domain.enums import FacilityStatus, FacilityType  # noqa: E402
from app.foundation.f02_facility.domain.ingest.pipeline import (  # noqa: E402
    UNION_KEYS,
    _recompute_canonical,
)
from app.foundation.f02_facility.domain.models import Facility  # noqa: E402
from app.foundation.f02_facility.domain.service import (  # noqa: E402
    colocated_host,
    merge_facilities,
)


def _retype_misfiled_weighbridges(db, dry_run: bool) -> int:
    """Pass 1. Before the weighbridge rules outranked the generic "some service + hgv
    -> repair" catch-all, a CAT scale tagged hgv=designated filed itself as a REPAIR
    SHOP. The pipeline never re-types an existing facility (it sets the kind once at
    creation, exactly as it does the name), so a re-ingest cannot fix these either."""
    retyped = 0
    for fac in db.scalars(
        select(Facility)
        .where(Facility.status != FacilityStatus.merged)
        .where(Facility.facility_type == FacilityType.repair)
    ):
        tags = [(s.attributes or {}).get("osm_tags", {}) for s in fac.sources]
        if not tags or not all(t.get("amenity") in ("weighbridge", "weigh_station") for t in tags):
            continue
        commercial = any(
            "cat scale"
            in " ".join(str(t.get(k, "")) for k in ("operator", "brand", "name")).lower()
            for t in tags
        )
        want = FacilityType.scale if commercial else FacilityType.weigh_station
        print(f"  retype {fac.name!r}: repair -> {want.value}")
        if not dry_run:
            fac.facility_type = want
        retyped += 1
    if not dry_run:
        db.flush()
    return retyped


def main() -> None:
    dry_run = os.environ.get("DRY_RUN", "1") != "0"
    db = SessionLocal()
    merged = standalone = 0
    try:
        retyped = _retype_misfiled_weighbridges(db, dry_run)
        scales = list(
            db.scalars(
                select(Facility)
                .where(Facility.facility_type == FacilityType.scale)
                .where(Facility.status != FacilityStatus.merged)
            )
        )
        for scale in scales:
            lat, lon = db.execute(
                select(Facility.geom.ST_Y(), Facility.geom.ST_X()).where(Facility.id == scale.id)
            ).one()
            host = colocated_host(db, lat, lon)
            if host is None or host.id == scale.id:
                standalone += 1
                continue
            print(f"  {scale.name!r} -> {host.name!r} ({host.facility_type.value})")
            if not dry_run:
                for src in list(scale.sources):
                    src.attributes = {
                        k: v for k, v in (src.attributes or {}).items() if k in UNION_KEYS
                    }
                merge_facilities(db, host, scale)
                _recompute_canonical(db, host)
            merged += 1

        print(
            f"\n{'DRY RUN — ' if dry_run else ''}{retyped} misfiled weighbridge(s) re-typed, "
            f"{merged} scale(s) merged into their host, {standalone} left standing alone"
        )
        if dry_run:
            print("re-run with DRY_RUN=0 to apply")
            db.rollback()
        else:
            db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

"""AI-CONTEXT: E3.3 one-off repair for facilities ingested BEFORE the branded-service-
area and co-located-fuel rules existed (`make repair-fuel`, `DRY_RUN=0` to apply).

Two defects, both found by reading the deployed map rather than by a test:

1. `highway=services` sat ABOVE the truck-stop rule, so every US chain — which is
   tagged that way — filed itself as a REST AREA. 309 branded truck stops were rest
   areas and not one facility was typed truck_stop from that tag. The Fuel preset is
   `[fuel_station]`, so a Flying J carrying `fuel:diesel=yes` in its own tags was
   absent from the one preset built to find it.
2. 474 of 546 fuel stations stood within 150 m of a destination that already had a
   pin, so one truck stop drew as two places ~30 m apart — and the PRICE landed on
   the island, which carries the pump's name ("Pilot") rather than the site's
   ("Flying J Travel Center"). design-prd §11.1: extra signals render as badges on
   existing pins, never as more pins.

A re-ingest fixes neither. An already-seen (source, external_ref) takes the
update-in-place branch and never revisits which facility it belongs to, and the
pipeline never re-types an existing facility — it sets the kind once at creation.

Pass 1 re-types branded service areas. Pass 2 backfills the `fuel` service onto sites
whose own tags sell diesel, so the price badge has an honest gate before any merge
moves a pump. Pass 3 merges each co-located fuel station into its host, narrowing the
source's contribution to the service fact — the pump's name, phone and website
describe the ISLAND, and letting them through would dress a Flying J as a Pilot.

Order matters: pass 1 runs first so a newly-typed truck_stop can host in pass 3, and
pass 2 before pass 3 so a host that sells diesel keeps its badge even where the merge
finds nothing to move.

`merge_facilities` is the sanctioned path, so nothing is deleted and every
`facility_id` anyone already holds still resolves. Idempotent: a second run finds
nothing to do.
"""

import os
import sys

import db_registry

db_registry.import_all_models()

from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.foundation.f02_facility.domain.enums import FacilityStatus, FacilityType  # noqa: E402
from app.foundation.f02_facility.domain.ingest.adapters import (  # noqa: E402
    SERVICE_FUEL,
    _osm_is_branded_service_area,
    _osm_sells_diesel,
)
from app.foundation.f02_facility.domain.ingest.pipeline import (  # noqa: E402
    UNION_KEYS,
    _recompute_canonical,
)
from app.foundation.f02_facility.domain.models import Facility  # noqa: E402
from app.foundation.f02_facility.domain.service import (  # noqa: E402
    colocated_host,
    host_should_adopt_name,
    merge_facilities,
)


def _osm_tags(fac) -> list[dict]:
    return [(s.attributes or {}).get("osm_tags") or {} for s in fac.sources]


def _live(db, *types):
    stmt = (
        select(Facility)
        .where(Facility.status != FacilityStatus.merged)
        .where(~Facility.is_dev)
    )
    if types:
        stmt = stmt.where(Facility.facility_type.in_(types))
    return list(db.scalars(stmt))


def _retype_branded_service_areas(db, dry_run: bool) -> int:
    retyped = 0
    for fac in _live(db, FacilityType.rest_area):
        if not any(_osm_is_branded_service_area(t) for t in _osm_tags(fac)):
            continue
        print(f"  retype {fac.name!r}: rest_area -> truck_stop")
        if not dry_run:
            fac.facility_type = FacilityType.truck_stop
        retyped += 1
    if not dry_run:
        db.flush()
    return retyped


def _backfill_fuel_service(db, dry_run: bool) -> int:
    """A site whose OWN tags sell diesel carries the service whether or not OSM also
    mapped the island separately. Without this the badge gate would depend entirely on
    a merge having something to move."""
    added = 0
    for fac in _live(db):
        attrs = fac.attributes or {}
        if SERVICE_FUEL in (attrs.get("services") or []):
            continue
        if not any(_osm_sells_diesel(t) for t in _osm_tags(fac)):
            continue
        print(f"  +fuel service {fac.name!r} ({fac.facility_type.value})")
        if not dry_run:
            for src in fac.sources:
                tags = (src.attributes or {}).get("osm_tags") or {}
                if not _osm_sells_diesel(tags):
                    continue
                services = list((src.attributes or {}).get("services") or [])
                if SERVICE_FUEL not in services:
                    src.attributes = {
                        **(src.attributes or {}),
                        "services": [*services, SERVICE_FUEL],
                    }
            # `_recompute_canonical` opens with db.refresh(), which reloads the source
            # collection and would read straight past an unflushed edit — the first
            # run of this pass reported 553 sites updated and the second reported 109
            # of them again, because those writes never reached the row.
            db.flush()
            _recompute_canonical(db, fac)
        added += 1
    if not dry_run:
        db.flush()
    return added


def _merge_colocated_fuel(db, dry_run: bool) -> tuple[int, int, int]:
    merged = standalone = adopted = 0
    for station in _live(db, FacilityType.fuel_station):
        lat, lon = db.execute(
            select(Facility.geom.ST_Y(), Facility.geom.ST_X()).where(Facility.id == station.id)
        ).one()
        host = colocated_host(db, lat, lon)
        if host is None or host.id == station.id:
            standalone += 1
            continue
        if host_should_adopt_name(host, station.name):
            print(f"  ADOPT {host.name!r} -> {station.name!r} (host was unnamed)")
            if not dry_run:
                host.name = station.name
                db.flush()
            adopted += 1
        print(f"  {station.name!r} -> {host.name!r} ({host.facility_type.value})")
        if not dry_run:
            for src in list(station.sources):
                narrowed = {k: v for k, v in (src.attributes or {}).items() if k in UNION_KEYS}
                services = list(narrowed.get("services") or [])
                if SERVICE_FUEL not in services:
                    services.append(SERVICE_FUEL)
                narrowed["services"] = services
                src.attributes = narrowed
            merge_facilities(db, host, station)
            _recompute_canonical(db, host)
        merged += 1
    return merged, standalone, adopted


def main() -> None:
    dry_run = os.environ.get("DRY_RUN", "1") != "0"
    db = SessionLocal()
    try:
        retyped = _retype_branded_service_areas(db, dry_run)
        fuelled = _backfill_fuel_service(db, dry_run)
        merged, standalone, adopted = _merge_colocated_fuel(db, dry_run)
        print(
            f"\n{'DRY RUN — ' if dry_run else ''}{retyped} branded service area(s) re-typed to "
            f"truck_stop, {fuelled} site(s) gained the fuel service, {merged} fuel station(s) "
            f"merged into their host, {standalone} left standing alone, "
            f"{adopted} unnamed host(s) adopted the pump's name so the merge kept it"
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

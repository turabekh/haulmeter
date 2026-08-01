"""AI-CONTEXT: A9 §5 one-off — merge the duplicates the OLD geohash blocking missed
(`make repair-duplicates`, `DRY_RUN=0` to apply).

The rule is fixed for future ingests, but a re-ingest does NOT fix these: an already
seen (source, external_ref) takes the update-in-place branch and never revisits which
facility it belongs to. Meanwhile they are on the map today — "Flying J Travel Center"
twice, 3 m apart, is two pins for one place in front of a driver.

Measured on the nine-state registry: 191 live pairs within 60 m at ≥0.5 similarity, in
DIFFERENT geohash-7 cells. 122 have real names; the other 69 are two placeholders and
are deliberately left alone, because a name this code invented is not evidence.

It reuses `find_duplicate_candidates` rather than re-deriving the rule, so the repair
and the ingest cannot disagree about what a duplicate is — the §23 entry 94 lesson,
which this session has now paid for twice.

`merge_facilities` is the sanctioned path: nothing is deleted, `merged_into_id` is set,
and every facility_id anyone already holds still resolves. Idempotent — a second run
finds nothing, because the first run's losers are `status=merged` and no longer
candidates.
"""

import os
import sys

import db_registry

db_registry.import_all_models()

from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.foundation.f02_facility.domain.enums import FacilityStatus  # noqa: E402
from app.foundation.f02_facility.domain.models import Facility  # noqa: E402
from app.foundation.f02_facility.domain.service import (  # noqa: E402
    coordinates,
    find_duplicate_candidates,
    merge_facilities,
)


def _live(db):
    return list(
        db.scalars(
            select(Facility)
            .where(Facility.status != FacilityStatus.merged)
            .where(~Facility.is_dev)
            .order_by(Facility.created_at)
        )
    )


def repair(db, dry_run: bool = True) -> dict:
    stats = {"scanned": 0, "merged": 0}
    seen: set = set()
    for facility in _live(db):
        stats["scanned"] += 1
        if facility.id in seen or facility.status == FacilityStatus.merged:
            continue
        lat, lon = coordinates(db, facility)
        if lat is None:
            continue
        for candidate in find_duplicate_candidates(db, facility.name, lat, lon):
            if candidate.id == facility.id or candidate.id in seen:
                continue
            # KEEP THE OLDER ROW. Whichever survives, the other's sources move onto it —
            # but the older id is the one other tables and any URL a driver has already
            # points at, so it is the cheaper survivor.
            keeper, loser = (
                (facility, candidate)
                if facility.created_at <= candidate.created_at
                else (candidate, facility)
            )
            if loser.facility_type != keeper.facility_type:
                # different KINDS at 60 m is a co-location question, not a duplicate one,
                # and that path has its own rules. Leave it to them.
                continue
            print(f"  merge {loser.name!r} -> {keeper.name!r}")
            if not dry_run:
                merge_facilities(db, keeper, loser)
            seen.add(loser.id)
            stats["merged"] += 1
    return stats


def main() -> None:
    dry_run = os.environ.get("DRY_RUN", "1") != "0"
    db = SessionLocal()
    try:
        stats = repair(db, dry_run=dry_run)
        if dry_run:
            db.rollback()
            print(f"DRY RUN — {stats}. Re-run with DRY_RUN=0 to apply.")
        else:
            db.commit()
            print(f"applied — {stats}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    sys.exit(0)


if __name__ == "__main__":
    main()

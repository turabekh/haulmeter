"""AI-CONTEXT: A5 one-off backfill — promote `phone` and `opening_hours` out of the
raw `osm_tags` blob for facilities ingested before the adapter read them
(`make repair-contact`, `DRY_RUN=0` to apply).

The numbers were never missing. 633 facilities in the nine-state registry carry a
phone inside `osm_tags` and 245 carry opening hours, and not one facility had either
as a field anything could read — so the map could not offer a call on any pin. The
adapter promotes them now; this is for everything already in the table.

A re-ingest does NOT fix these. An already-seen (source, external_ref) takes the
update-in-place branch, which rewrites the source's contribution from the record the
adapter just built — so it would work, but only for a state whose extract has been
re-downloaded and re-run. This reads what is already stored, which is every state.

The contribution is written on the SOURCE and recomputed, not poked onto the
facility, so the merge rules stay in charge: a co-located amenity's phone is narrowed
away by `_contribution` exactly as before, because the pump's phone describes the
island and not the Flying J it stands in. Idempotent — a second run finds nothing.
"""

import os
import sys

import db_registry

db_registry.import_all_models()

from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.foundation.f02_facility.domain.enums import FacilityStatus  # noqa: E402
from app.foundation.f02_facility.domain.ingest.pipeline import _recompute_canonical  # noqa: E402
from app.foundation.f02_facility.domain.models import Facility  # noqa: E402

# the same tag names the adapter reads, imported rather than retyped so this script
# cannot promote a different set than ingestion does
CONTACT_TAGS = (("phone", ("phone", "contact:phone")), ("opening_hours", ("opening_hours",)))


def _promote(tags: dict) -> dict:
    out = {}
    for key, names in CONTACT_TAGS:
        value = next((str(tags[n]).strip() for n in names if tags.get(n)), "")
        if value:
            out[key] = value
    return out


def backfill(db, dry_run: bool = True) -> dict:
    stats = {"scanned": 0, "sources_updated": 0, "facilities": 0}
    facilities = list(
        db.scalars(select(Facility).where(Facility.status != FacilityStatus.merged))
    )
    for fac in facilities:
        stats["scanned"] += 1
        touched = False
        for source in fac.sources:
            attrs = dict(source.attributes or {})
            promoted = _promote(attrs.get("osm_tags") or {})
            missing = {k: v for k, v in promoted.items() if attrs.get(k) != v}
            if not missing:
                continue
            print(f"  {fac.name!r}: {', '.join(f'{k}={v}' for k, v in missing.items())}")
            if not dry_run:
                source.attributes = {**attrs, **missing}
            stats["sources_updated"] += 1
            touched = True
        if touched:
            stats["facilities"] += 1
            if not dry_run:
                db.flush()
                _recompute_canonical(db, fac)
    return stats


def main() -> None:
    dry_run = os.environ.get("DRY_RUN", "1") != "0"
    db = SessionLocal()
    try:
        stats = backfill(db, dry_run=dry_run)
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

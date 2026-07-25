"""AI-CONTEXT: one-off dev-DB cleanup (PRD §12) — `make purge-demo`. Deletes
facilities whose every source is `admin` (the manual-test / demo leftovers:
"Dallas", "CT Test", "Dock", "R", "Perth …", "Smoke …", "… (demo)", "DEV —") AND
the whole test-data subtree hanging off them — the demo loads/stops (F05), armed
geofences + presence/events (F03), crowd submissions/beliefs (F10), and facility
profiles/reviews (M2) that only exist because someone exercised a flow against a
throwaway facility. Real POI data (NTAD/OSM/TPIMS, non-admin sources) is untouched:
the scope is exactly the admin-only facility id set and records keyed to it. Demo
re-ingest is guarded (seed_demo is gated on DEV_SEED=1; those rows carry is_dev).
Idempotent — a second run is a no-op. Dev only; never run against real data.
"""

import db_registry

db_registry.import_all_models()

from sqlalchemy import bindparam, func, select, text  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.foundation.f02_facility.domain.enums import SourceKind  # noqa: E402
from app.foundation.f02_facility.domain.models import FacilitySource  # noqa: E402

# records keyed directly to a facility_id, deleted before the facility itself.
# Order is child-safe: none of these reference each other (verified FK graph).
FACILITY_DEPENDENTS = [
    # M13: a demo vendor's appearances hang off a demo facility. Offerings cascade
    # from the appearance; the vendor row itself is dropped separately (below) since
    # it is keyed to an account, not a facility.
    "m13.appearance",
    # Session B: reviews, promotions, claims and reports all hang off a demo
    # vendor (cascade) or a demo facility (here). Both routes are covered.
    "m13.facility_claim",
    "f03.geofence_event",
    "f03.geofence_presence",
    "f03.geofence_arming",
    "f03.facility_geofence",
    "f10.belief",
    "f10.submission",
    "m02.facility_review",
    "m02.facility_profile",
]


def _delete_in(db, sql: str, ids: list) -> int:
    stmt = text(sql).bindparams(bindparam("ids", expanding=True))
    return db.execute(stmt, {"ids": ids}).rowcount


def main() -> None:
    db = SessionLocal()
    try:
        # facilities whose sources are ALL admin (no real-source contribution)
        admin_only = (
            select(FacilitySource.facility_id)
            .group_by(FacilitySource.facility_id)
            .having(func.bool_or(FacilitySource.source_kind != SourceKind.admin).is_(False))
        )
        ids = list(db.scalars(admin_only))
        if not ids:
            print("no admin-only (demo/test) facilities — nothing to purge")
            return

        # the demo loads these facilities are a stop on — delete every stop of those
        # loads (both ends) then the loads, so no real-facility dest stop is orphaned.
        load_ids = list(
            db.scalars(
                text("SELECT DISTINCT load_id FROM f05.stop WHERE facility_id IN :ids").bindparams(
                    bindparam("ids", expanding=True)
                ),
                {"ids": ids},
            )
        )

        for table in FACILITY_DEPENDENTS:
            _delete_in(db, f"DELETE FROM {table} WHERE facility_id IN :ids", ids)
        if load_ids:
            _delete_in(db, "DELETE FROM f05.stop WHERE load_id IN :ids", load_ids)
            _delete_in(db, "DELETE FROM f05.load WHERE id IN :ids", load_ids)
        # DEV_SEED vendors are self-identifying (is_dev), like DEV_SEED facilities —
        # their appearances went with the facilities above, so this drops the profiles
        vendors = db.execute(text("DELETE FROM m13.vendor WHERE is_dev = true")).rowcount
        purged = _delete_in(db, "DELETE FROM f02.facility WHERE id IN :ids", ids)
        db.commit()
        print(
            f"purged {purged} admin-only facilities + {len(load_ids)} demo loads "
            f"+ {vendors} demo vendors (test subtree)"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()

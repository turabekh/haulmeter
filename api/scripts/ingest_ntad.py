"""AI-CONTEXT: manual NTAD ingest (PRD §12) — `make ingest-ntad`. Live pull of the
BTS Truck Stop Parking FeatureServer through the F2 pipeline (idempotent). Not run
in CI (CI drives the pipeline against committed fixtures).
"""

import db_registry

db_registry.import_all_models()

from app.core.db import SessionLocal  # noqa: E402
from app.ingest import flags as ingest_flags  # noqa: E402
from app.ingest import runners, sources  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        ingest_flags.register_ingest_flags(db)
        sources.register_source_config(db)
        db.commit()
        stats = runners.run_ntad(db)
        print(
            f"NTAD ingest — staged={stats.staged} created={stats.created} "
            f"matched={stats.matched} facilities={len(stats.facility_ids)}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()

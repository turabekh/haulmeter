"""AI-CONTEXT: manual OSM ingest (PRD §12) — `make ingest-osm STATE=wisconsin`.
Reads an osmium-filtered GeoJSON (produced by `make osm-extract`) through the F2
pipeline. OSM rows stay separable (source_kind=osm) for ODbL compliance. Not run in
CI (CI drives parse_osm against a committed fixture).
"""

import sys

import db_registry

db_registry.import_all_models()

from app.core.db import SessionLocal  # noqa: E402
from app.ingest import flags as ingest_flags  # noqa: E402
from app.ingest import runners, sources  # noqa: E402

DEFAULT_PATH = "/app/data/osm/wisconsin.geojson"


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PATH
    db = SessionLocal()
    try:
        ingest_flags.register_ingest_flags(db)
        sources.register_source_config(db)
        db.commit()
        stats = runners.run_osm(db, path)
        print(
            f"OSM ingest ({path}) — staged={stats.staged} created={stats.created} "
            f"matched={stats.matched} facilities={len(stats.facility_ids)}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()

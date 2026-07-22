"""AI-CONTEXT: manual one-shot TPIMS ingest (PRD §12) — `make ingest-tpims`. Pulls
the static site metadata (facilities) then one dynamic availability cycle (beliefs
with real freshness). The worker runs these on a cadence when the flags are on; this
is the on-demand trigger for dev. Not run in CI.
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
        static = runners.run_tpims_static(db)
        print(
            f"TPIMS static — staged={static.staged} "
            f"created={static.created} matched={static.matched}"
        )
        dynamic = runners.run_tpims_dynamic(db)
        print(f"TPIMS dynamic — {dynamic}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

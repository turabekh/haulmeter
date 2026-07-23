"""AI-CONTEXT: F13 activation flags for the F2 ingestion jobs (PRD §12).

Each source refreshes behind its own flag (off by default). TPIMS runs as worker
jobs; NTAD + OSM are manual make-target pulls. Registered idempotently.
"""

from app.foundation.f13_flags import public as flags

FLAG_NTAD = "f02_ingest_ntad"
FLAG_TPIMS_STATIC = "f02_ingest_tpims_static"
FLAG_TPIMS_DYNAMIC = "f02_ingest_tpims_dynamic"
FLAG_OSM = "f02_ingest_osm"
FLAG_EIA = "m07_ingest_eia"

_DESCRIPTIONS = {
    FLAG_NTAD: "F2 ingest — NTAD truck-stop parking (manual make target)",
    FLAG_TPIMS_STATIC: "F2 ingest — TPIMS static site metadata (daily worker job)",
    FLAG_TPIMS_DYNAMIC: "F2 ingest — TPIMS dynamic availability (worker job, ~3 min)",
    FLAG_OSM: "F2 ingest — OpenStreetMap extract (manual make target)",
    FLAG_EIA: "M7 ingest — EIA weekly regional diesel baseline (worker job; EIA publishes Mondays)",
}


def register_ingest_flags(db) -> None:
    for key, description in _DESCRIPTIONS.items():
        flags.register_flag(db, key, description=description)

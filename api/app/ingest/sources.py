"""AI-CONTEXT: source endpoints for F2 real-POI ingestion (PRD §12).

The exact discovered URLs live in the F13 config registry (scope `data_sources`),
not baked into code — the constants below are only the seed defaults, overridable
per environment without a deploy. `register_source_config` seeds them once.
"""

from app.foundation.f13_flags import public as flags

CONFIG_SCOPE = "data_sources"

# discovered 2026-07-22 (HANDOFF-065); TPIMS switched to the verified-live Travel
# Midwest IL feed 2026-07-23 (HANDOFF-068). Overridable via the config registry.
DEFAULTS = {
    "ntad_featureserver": (
        "https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services/"
        "NTAD_Truck_Stop_Parking/FeatureServer/0"
    ),
    "tpims_static": "https://truckparking.travelmidwest.com/TPIMS_Static.json",
    "tpims_dynamic": "https://truckparking.travelmidwest.com/TPIMS_Dynamic.json",
    "geofabrik_base": "https://download.geofabrik.de/north-america/us",
}


def register_source_config(db) -> None:
    for key, value in DEFAULTS.items():
        if flags.get_config(db, f"{CONFIG_SCOPE}.{key}") is None:
            flags.set_config(db, f"{CONFIG_SCOPE}.{key}", value, scope=CONFIG_SCOPE)


def source_url(db, key: str) -> str:
    return flags.get_config(db, f"{CONFIG_SCOPE}.{key}", DEFAULTS[key]) or DEFAULTS[key]

"""AI-CONTEXT: Public interface for M1 Road Intelligence Map.

The ONLY import surface other packages may use to reach M1 (import-linter
enforced). The daily-open map surface, composed from F1/F2/F10/F11/F12; runs
behind the F13 flag `m01_map`. Consumed by later modules and the UI layer.
"""

from .domain.enums import NavProvider, Preset
from .domain.service import (
    FLAG_KEY,
    MAX_CORRIDOR_SCALES,
    MODULE,
    OVERLAY_PIN_CAP,
    WEIGH_STATION_FLAG,
    ParkingPrediction,
    corridor_view,
    map_overlay,
    map_overlay_bbox,
    map_overlay_view,
    map_overlay_view_bbox,
    nav_deeplink,
    predict_parking_fill,
    queue_status_offline,
    record_map_open,
    register_module,
    scales_ahead,
    submit_status,
)

__all__ = [
    "scales_ahead",
    "WEIGH_STATION_FLAG",
    "MAX_CORRIDOR_SCALES",
    "NavProvider",
    "Preset",
    "FLAG_KEY",
    "MODULE",
    "ParkingPrediction",
    "corridor_view",
    "OVERLAY_PIN_CAP",
    "map_overlay",
    "map_overlay_bbox",
    "map_overlay_view",
    "map_overlay_view_bbox",
    "nav_deeplink",
    "predict_parking_fill",
    "queue_status_offline",
    "record_map_open",
    "register_module",
    "submit_status",
]

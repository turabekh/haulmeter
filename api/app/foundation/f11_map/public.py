"""AI-CONTEXT: Public interface for F11 Map & POI Serving.

The ONLY import surface other packages may use to reach F11 (import-linter
enforced). Server-side POI overlays (pins + badges + freshness), clustering, and
the corridor query primitive, composed from F2 geometry and F10 beliefs. Returns
semantic data; the client renders colors from design tokens. Consumed by M1, M2,
M6, M7, M8, M10.
"""

from .domain.service import (
    DEFAULT_BADGE_PROVIDERS,
    PIN_SHAPES,
    Badge,
    Cluster,
    CorridorEntry,
    Freshness,
    Pin,
    cluster_pins,
    clusters_for,
    corridor,
    facilities_in_area,
    facilities_in_bbox,
    fuel_price_badge,
    overlay_pins,
    overlay_pins_bbox,
    pins_for,
    status_signal_for,
)

__all__ = [
    "DEFAULT_BADGE_PROVIDERS",
    "PIN_SHAPES",
    "Badge",
    "Cluster",
    "CorridorEntry",
    "Freshness",
    "Pin",
    "cluster_pins",
    "clusters_for",
    "facilities_in_area",
    "facilities_in_bbox",
    "pins_for",
    "corridor",
    "fuel_price_badge",
    "overlay_pins",
    "status_signal_for",
    "overlay_pins_bbox",
]

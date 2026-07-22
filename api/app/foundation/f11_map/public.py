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
    corridor,
    fuel_price_badge,
    overlay_pins,
    overlay_pins_bbox,
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
    "corridor",
    "fuel_price_badge",
    "overlay_pins",
    "overlay_pins_bbox",
]

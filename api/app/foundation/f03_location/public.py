"""AI-CONTEXT: Public interface for F3 Location & Geofence Engine.

The ONLY import surface other packages may use to reach F3 (import-linter
enforced). Server time is authoritative; client clock skew is recorded per
ping; ENTER/EXIT/DWELL_TICK events fire against F2 geometries. Consumed by
M1, M2, M3, M4, M5, M8, M9, M10.
"""

from .domain.enums import GeofenceEventType, LocationMode
from .domain.models import (
    FacilityGeofence,
    GeofenceArming,
    GeofenceEvent,
    GeofencePresence,
    LocationPing,
)
from .domain.service import (
    DEFAULT_RADIUS_M,
    DWELL_TICK_INTERVAL,
    GPS_DIVERGENCE_THRESHOLD,
    FacilityNotFound,
    arm_geofence,
    build_trace,
    disarm_geofence,
    dwell_samples,
    evaluate_ping,
    facility_radius,
    is_present,
    last_known_position,
    list_events,
    purge_pings_older_than,
    record_ping,
    visit_window,
)

__all__ = [
    "FacilityGeofence",
    "GeofenceArming",
    "GeofenceEvent",
    "GeofencePresence",
    "LocationPing",
    "GeofenceEventType",
    "LocationMode",
    "DEFAULT_RADIUS_M",
    "DWELL_TICK_INTERVAL",
    "GPS_DIVERGENCE_THRESHOLD",
    "FacilityNotFound",
    "arm_geofence",
    "build_trace",
    "disarm_geofence",
    "dwell_samples",
    "evaluate_ping",
    "facility_radius",
    "is_present",
    "last_known_position",
    "list_events",
    "purge_pings_older_than",
    "record_ping",
    "visit_window",
]

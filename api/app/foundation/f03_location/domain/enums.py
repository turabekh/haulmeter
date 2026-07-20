import enum


class GeofenceEventType(enum.Enum):
    ENTER = "ENTER"
    EXIT = "EXIT"
    DWELL_TICK = "DWELL_TICK"


class LocationMode(enum.Enum):
    significant_change = "significant_change"
    high_accuracy = "high_accuracy"

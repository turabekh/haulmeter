import enum


class ClaimMode(enum.Enum):
    invoice = "invoice"  # own-authority / leased: bill the broker in the driver's name
    evidence_only = "evidence_only"  # company driver (P2): pack for their carrier, no invoice


class DetentionTrigger(enum.Enum):
    appointment = "appointment"
    arrival = "arrival"


class ClaimState(enum.Enum):
    open = "open"
    packaged = "packaged"
    invoiced = "invoiced"
    exported = "exported"  # company-driver pack handed to carrier
    escalated = "escalated"


class DetentionPhase(enum.Enum):
    within_free_time = "within_free_time"
    accruing = "accruing"
    ended = "ended"

import enum


class CapturePhase(enum.Enum):
    pickup = "pickup"
    delivery = "delivery"


# design/PRD M5-FR2: guided cargo-condition photo sequence
CONDITION_SEQUENCE = ["trailer_exterior", "seals", "load_blocking", "reefer_setpoint"]

# doc types surfaced in inspection mode (M5-FR3)
INSPECTION_DOC_TYPES = ["cdl", "med_card", "insurance", "permit"]


class StopPacketState(enum.Enum):
    """AI-CONTEXT: A1 requirement 5 — "the driver reviews before it sends. Nothing
    leaves silently. A packet the driver did not see is a document they cannot vouch
    for." Two states, and the gap between them is a person."""

    draft = "draft"
    sent = "sent"

import enum


class CapturePhase(enum.Enum):
    pickup = "pickup"
    delivery = "delivery"


# design/PRD M5-FR2: guided cargo-condition photo sequence
CONDITION_SEQUENCE = ["trailer_exterior", "seals", "load_blocking", "reefer_setpoint"]

# doc types surfaced in inspection mode (M5-FR3)
INSPECTION_DOC_TYPES = ["cdl", "med_card", "insurance", "permit"]

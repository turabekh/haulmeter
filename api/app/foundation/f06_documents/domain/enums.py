import enum


class DocType(enum.Enum):
    rate_con = "rate_con"
    bol = "bol"
    pod = "pod"
    lumper_receipt = "lumper_receipt"
    # AI-CONTEXT: A1's capture checklist named five artifacts; three were already doc
    # types and these two were not. A checklist row with nowhere to capture it is a tick
    # that can never turn green — decoration facing the other way (see `has_bol`).
    seal = "seal"
    damage = "damage"
    cdl = "cdl"
    med_card = "med_card"
    insurance = "insurance"
    permit = "permit"
    settlement = "settlement"
    other = "other"


class ExtractionStatus(enum.Enum):
    pending = "pending"
    extracted = "extracted"
    failed = "failed"

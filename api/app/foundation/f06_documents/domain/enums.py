import enum


class DocType(enum.Enum):
    rate_con = "rate_con"
    bol = "bol"
    pod = "pod"
    lumper_receipt = "lumper_receipt"
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

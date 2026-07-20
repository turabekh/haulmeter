import enum


class AccessorialKind(enum.Enum):
    tonu = "tonu"
    layover = "layover"
    lumper = "lumper"


class AccessorialState(enum.Enum):
    draft = "draft"
    invoiced = "invoiced"

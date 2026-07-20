import enum


class CounterpartyKind(enum.Enum):
    broker = "broker"
    shipper = "shipper"
    receiver = "receiver"
    carrier = "carrier"


class LoadSource(enum.Enum):
    manual = "manual"
    rate_con_parse = "rate_con_parse"
    tms_push = "tms_push"


class LoadStatus(enum.Enum):
    draft = "draft"
    active = "active"
    completed = "completed"
    canceled = "canceled"


class StopType(enum.Enum):
    pickup = "pickup"
    delivery = "delivery"


class StopStatus(enum.Enum):
    pending = "pending"
    armed = "armed"
    arrived = "arrived"
    departed = "departed"
    canceled = "canceled"

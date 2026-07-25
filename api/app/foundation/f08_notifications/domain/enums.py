import enum


class NotificationTier(enum.Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class NotificationStatus(enum.Enum):
    pending = "pending"
    sent = "sent"
    suppressed = "suppressed"
    digested = "digested"


class NotificationChannel(enum.Enum):
    push = "push"
    sms = "sms"
    email = "email"
    in_app = "in_app"
    audio = "audio"


class SuppressReason(enum.Enum):
    budget = "budget"
    quiet_hours = "quiet_hours"
    resting = "resting"
    # opt-in notification classes (design-prd §23 E-D1)
    not_opted_in = "not_opted_in"
    muted = "muted"


class DriverState(enum.Enum):
    idle = "idle"
    driving = "driving"
    on_site = "on_site"
    resting = "resting"


class MessageDirection(enum.Enum):
    outbound = "outbound"
    inbound = "inbound"


class TemplateAudience(enum.Enum):
    driver = "driver"
    counterparty = "counterparty"

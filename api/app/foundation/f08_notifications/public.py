"""AI-CONTEXT: Public interface for F8 Notifications & Outbound Communications.

The ONLY import surface other packages may use to reach F8 (import-linter
enforced). Enforces the design-prd §13 interruption budget (P0/P1/P2, 2/day,
quiet hours, DRIVING/RESTING safety). Counterparty templates are always English
(F15). Consumed by every module.
"""

from .domain.enums import (
    DriverState,
    MessageDirection,
    NotificationChannel,
    NotificationStatus,
    NotificationTier,
    SuppressReason,
    TemplateAudience,
)
from .domain.gateway import (
    NotificationGateway,
    RecordingNotificationGateway,
    SentMessage,
    StubNotificationGateway,
)
from .domain.models import (
    Notification,
    NotificationPrefs,
    NotificationTemplate,
    OutboundMessage,
    OutboundThread,
)
from .domain.service import (
    MAX_UNPROMPTED_P1_PER_DAY,
    CounterpartyMustBeEnglish,
    MissingDeepLink,
    create_thread,
    digest,
    dispatch,
    get_active_template,
    get_or_create_prefs,
    in_quiet_hours,
    mark_opened,
    p1_budget_used,
    record_inbound_reply,
    register_template,
    render_template,
    send_counterparty_message,
)

__all__ = [
    "DriverState",
    "MessageDirection",
    "NotificationChannel",
    "NotificationStatus",
    "NotificationTier",
    "SuppressReason",
    "TemplateAudience",
    "NotificationGateway",
    "RecordingNotificationGateway",
    "SentMessage",
    "StubNotificationGateway",
    "Notification",
    "NotificationPrefs",
    "NotificationTemplate",
    "OutboundMessage",
    "OutboundThread",
    "MAX_UNPROMPTED_P1_PER_DAY",
    "CounterpartyMustBeEnglish",
    "MissingDeepLink",
    "create_thread",
    "digest",
    "dispatch",
    "get_active_template",
    "get_or_create_prefs",
    "in_quiet_hours",
    "mark_opened",
    "p1_budget_used",
    "record_inbound_reply",
    "register_template",
    "render_template",
    "send_counterparty_message",
]

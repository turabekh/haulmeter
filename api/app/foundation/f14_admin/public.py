"""AI-CONTEXT: Public interface for F14 Admin Console & Analytics.

The ONLY import surface other packages may use to reach F14 (import-linter
enforced). Event instrumentation standard, per-module KPI aggregation, admin
audit log, content-moderation queue, and the admin-view registry. Consumed by
platform operations; every module registers its admin views here.
"""

from .domain.enums import ModerationStatus
from .domain.models import (
    AdminAction,
    AdminView,
    AnalyticsEvent,
    JobRun,
    JobSchedule,
    ModerationItem,
)
from .domain.service import (
    MODERATION_SLA_HOURS,
    claim_job,
    count_events,
    decide_moderation,
    emit,
    enqueue_moderation,
    ensure_job_schedule,
    events_for_account,
    finish_job_run,
    funnel,
    job_history,
    job_schedules,
    last_action_for,
    latest_job_runs,
    list_actions,
    list_admin_views,
    list_pending_moderation,
    overdue_moderation,
    record_action,
    register_admin_view,
    release_job,
    start_job_run,
)

__all__ = [
    "events_for_account",
    "start_job_run",
    "latest_job_runs",
    "last_action_for",
    "job_history",
    "finish_job_run",
    "JobRun",
    "JobSchedule",
    "claim_job",
    "ensure_job_schedule",
    "release_job",
    "job_schedules",
    "MODERATION_SLA_HOURS",
    "overdue_moderation",
    "ModerationStatus",
    "AdminAction",
    "AdminView",
    "AnalyticsEvent",
    "ModerationItem",
    "count_events",
    "decide_moderation",
    "emit",
    "enqueue_moderation",
    "funnel",
    "list_actions",
    "list_admin_views",
    "list_pending_moderation",
    "record_action",
    "register_admin_view",
]

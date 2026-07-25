"""AI-CONTEXT: Public interface for F14 Admin Console & Analytics.

The ONLY import surface other packages may use to reach F14 (import-linter
enforced). Event instrumentation standard, per-module KPI aggregation, admin
audit log, content-moderation queue, and the admin-view registry. Consumed by
platform operations; every module registers its admin views here.
"""

from .domain.enums import ModerationStatus
from .domain.models import AdminAction, AdminView, AnalyticsEvent, JobRun, ModerationItem
from .domain.service import (
    MODERATION_SLA_HOURS,
    count_events,
    decide_moderation,
    emit,
    enqueue_moderation,
    finish_job_run,
    funnel,
    job_history,
    last_action_for,
    latest_job_runs,
    list_actions,
    list_admin_views,
    list_pending_moderation,
    overdue_moderation,
    record_action,
    register_admin_view,
    start_job_run,
)

__all__ = [
    "start_job_run",
    "latest_job_runs",
    "last_action_for",
    "job_history",
    "finish_job_run",
    "JobRun",
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

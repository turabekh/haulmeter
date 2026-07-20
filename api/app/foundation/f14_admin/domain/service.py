"""AI-CONTEXT: F14 Admin Console & Analytics (PRD §7.14).

The ops/analytics backbone. Server side owns: the event instrumentation
standard (every module emits analytics events the same way), per-module KPI
aggregation (counts, funnels), an append-only admin audit log (who did what:
facility merge, refund, moderation), the content-moderation queue (reviews),
and the admin-view registry every module registers into. The ops console UI is
a web-first surface (design-prd §18) built later; this is its data spine.
"""
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .enums import ModerationStatus
from .models import AdminAction, AdminView, AnalyticsEvent, ModerationItem


# --- Event instrumentation standard ---
def emit(
    db: Session,
    event_name: str,
    module: str,
    occurred_at: datetime,
    account_id=None,
    properties: dict | None = None,
) -> AnalyticsEvent:
    event = AnalyticsEvent(
        event_name=event_name,
        module=module,
        account_id=account_id,
        properties=properties or {},
        occurred_at=occurred_at,
    )
    db.add(event)
    db.flush()
    return event


def count_events(
    db: Session,
    event_name: str,
    since: datetime | None = None,
    until: datetime | None = None,
    module: str | None = None,
) -> int:
    stmt = select(func.count()).select_from(AnalyticsEvent).where(
        AnalyticsEvent.event_name == event_name
    )
    if module is not None:
        stmt = stmt.where(AnalyticsEvent.module == module)
    if since is not None:
        stmt = stmt.where(AnalyticsEvent.occurred_at >= since)
    if until is not None:
        stmt = stmt.where(AnalyticsEvent.occurred_at <= until)
    return db.scalar(stmt)


def funnel(db: Session, steps: list[str], module: str | None = None) -> list[int]:
    stmt = select(AnalyticsEvent).where(AnalyticsEvent.event_name.in_(steps))
    if module is not None:
        stmt = stmt.where(AnalyticsEvent.module == module)

    earliest: dict = {}
    for event in db.scalars(stmt):
        if event.account_id is None:
            continue
        per_account = earliest.setdefault(event.account_id, {})
        current = per_account.get(event.event_name)
        if current is None or event.occurred_at < current:
            per_account[event.event_name] = event.occurred_at

    counts = [0] * len(steps)
    for step_times in earliest.values():
        last: datetime | None = None
        reached = 0
        for step in steps:
            time = step_times.get(step)
            if time is None or (last is not None and time < last):
                break
            last = time
            reached += 1
        for i in range(reached):
            counts[i] += 1
    return counts


# --- Admin audit log ---
def record_action(
    db: Session,
    action: str,
    actor_account_id=None,
    target_kind: str | None = None,
    target_ref=None,
    detail: dict | None = None,
) -> AdminAction:
    entry = AdminAction(
        action=action,
        actor_account_id=actor_account_id,
        target_kind=target_kind,
        target_ref=target_ref,
        detail=detail or {},
    )
    db.add(entry)
    db.flush()
    return entry


def list_actions(db: Session, action: str | None = None) -> list[AdminAction]:
    stmt = select(AdminAction)
    if action is not None:
        stmt = stmt.where(AdminAction.action == action)
    return list(db.scalars(stmt.order_by(AdminAction.created_at)))


# --- Moderation queue ---
def enqueue_moderation(
    db: Session, content_kind: str, content_ref, submitted_by=None
) -> ModerationItem:
    item = ModerationItem(
        content_kind=content_kind, content_ref=content_ref, submitted_by=submitted_by
    )
    db.add(item)
    db.flush()
    return item


def decide_moderation(
    db: Session,
    item: ModerationItem,
    status: ModerationStatus,
    moderator_account_id=None,
    reason: str | None = None,
) -> ModerationItem:
    item.status = status
    item.moderator_account_id = moderator_account_id
    item.reason = reason
    item.decided_at = datetime.now(UTC)
    db.flush()
    return item


def list_pending_moderation(db: Session, content_kind: str | None = None) -> list[ModerationItem]:
    stmt = select(ModerationItem).where(ModerationItem.status == ModerationStatus.pending)
    if content_kind is not None:
        stmt = stmt.where(ModerationItem.content_kind == content_kind)
    return list(db.scalars(stmt.order_by(ModerationItem.created_at)))


# --- Admin view registry ---
def register_admin_view(
    db: Session, key: str, module: str, title: str, path: str
) -> AdminView:
    existing = db.scalar(select(AdminView).where(AdminView.key == key))
    if existing is not None:
        existing.module = module
        existing.title = title
        existing.path = path
        db.flush()
        return existing
    view = AdminView(key=key, module=module, title=title, path=path)
    db.add(view)
    db.flush()
    return view


def list_admin_views(db: Session, module: str | None = None) -> list[AdminView]:
    stmt = select(AdminView)
    if module is not None:
        stmt = stmt.where(AdminView.module == module)
    return list(db.scalars(stmt.order_by(AdminView.module, AdminView.key)))

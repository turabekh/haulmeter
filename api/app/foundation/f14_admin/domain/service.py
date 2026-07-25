"""AI-CONTEXT: F14 Admin Console & Analytics (PRD §7.14).

The ops/analytics backbone. Server side owns: the event instrumentation
standard (every module emits analytics events the same way), per-module KPI
aggregation (counts, funnels), an append-only admin audit log (who did what:
facility merge, refund, moderation), the content-moderation queue (reviews),
and the admin-view registry every module registers into. The ops console UI is
a web-first surface (design-prd §18) built later; this is its data spine.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .enums import ModerationStatus
from .models import AdminAction, AdminView, AnalyticsEvent, JobRun, ModerationItem


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
    properties_match: dict | None = None,
) -> int:
    """AI-CONTEXT: `properties_match` narrows to events whose recorded properties
    carry these exact values — the difference between "how many vendor sheets were
    viewed" and "how many times was MY sheet viewed".

    It exists because the vendor portal reported the first as though it were the
    second: every vendor was shown the platform-wide total as their own view count.
    A number that flatters its reader is the §11.7 failure the portal's own header
    forbids, and the events already carried what was needed to be right."""
    stmt = (
        select(func.count())
        .select_from(AnalyticsEvent)
        .where(AnalyticsEvent.event_name == event_name)
    )
    if module is not None:
        stmt = stmt.where(AnalyticsEvent.module == module)
    if since is not None:
        stmt = stmt.where(AnalyticsEvent.occurred_at >= since)
    if until is not None:
        stmt = stmt.where(AnalyticsEvent.occurred_at <= until)
    for key, value in (properties_match or {}).items():
        stmt = stmt.where(AnalyticsEvent.properties[key].as_string() == str(value))
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
    target_key: str | None = None,
    detail: dict | None = None,
    before: dict | None = None,
    after: dict | None = None,
) -> AdminAction:
    """Every admin mutation lands here. `before`/`after` are what make this an audit
    log rather than an activity feed: after an incident the question is never "was
    the flag touched" but "what was it before someone touched it"."""
    entry = AdminAction(
        action=action,
        actor_account_id=actor_account_id,
        target_kind=target_kind,
        target_ref=target_ref,
        target_key=target_key,
        detail=detail or {},
        before=before,
        after=after,
    )
    db.add(entry)
    db.flush()
    return entry


def list_actions(
    db: Session,
    action: str | None = None,
    actor_account_id=None,
    target_kind: str | None = None,
    target_key: str | None = None,
    target_ref=None,
    limit: int | None = None,
) -> list[AdminAction]:
    """Newest first when limited — an operator opening the log wants what just
    happened, not the first thing that ever did. Unfiltered/unlimited stays oldest
    first for the existing callers that read it as a chronology."""
    stmt = select(AdminAction)
    if action is not None:
        stmt = stmt.where(AdminAction.action == action)
    if actor_account_id is not None:
        stmt = stmt.where(AdminAction.actor_account_id == actor_account_id)
    if target_kind is not None:
        stmt = stmt.where(AdminAction.target_kind == target_kind)
    if target_key is not None:
        stmt = stmt.where(AdminAction.target_key == target_key)
    if target_ref is not None:
        stmt = stmt.where(AdminAction.target_ref == target_ref)
    if limit is not None:
        rows = list(db.scalars(stmt.order_by(AdminAction.created_at.desc()).limit(limit)))
        return rows
    return list(db.scalars(stmt.order_by(AdminAction.created_at)))


def last_action_for(db: Session, action: str, target_key: str) -> AdminAction | None:
    """Who last touched this subject. Config provenance is built on this rather than
    on a column, so no table has to carry an actor it does not otherwise need."""
    db.flush()  # the row we are about to read may still be pending
    return db.scalar(
        select(AdminAction)
        .where(AdminAction.action == action, AdminAction.target_key == target_key)
        .order_by(AdminAction.created_at.desc())
        .limit(1)
    )


# --- Worker job telemetry (Overview: "did the feeds run?") ---
def start_job_run(db: Session, job_name: str, now: datetime) -> JobRun:
    run = JobRun(job_name=job_name, started_at=now, ok=False)
    db.add(run)
    db.flush()
    return run


def finish_job_run(
    db: Session,
    run: JobRun,
    now: datetime,
    ok: bool,
    summary: dict | None = None,
    error: str | None = None,
    consecutive_failures: int = 0,
    next_run_at: datetime | None = None,
) -> JobRun:
    run.finished_at = now
    run.ok = ok
    run.summary = summary or {}
    # a 500-char cap: an operator needs the shape of the failure, and an unbounded
    # traceback in a telemetry row is how tables quietly become log files
    run.error = error[:500] if error else None
    run.consecutive_failures = consecutive_failures
    run.next_run_at = next_run_at
    db.flush()
    return run


def latest_job_runs(db: Session, job_names: list[str] | None = None) -> dict[str, JobRun]:
    """The most recent ATTEMPT per job — success or failure. A job whose last attempt
    failed must not look healthy because an older success is still on file."""
    stmt = select(JobRun).order_by(JobRun.started_at.desc())
    if job_names:
        stmt = stmt.where(JobRun.job_name.in_(job_names))
    latest: dict[str, JobRun] = {}
    for run in db.scalars(stmt):
        latest.setdefault(run.job_name, run)
    return latest


def job_history(db: Session, job_name: str, limit: int = 20) -> list[JobRun]:
    return list(
        db.scalars(
            select(JobRun)
            .where(JobRun.job_name == job_name)
            .order_by(JobRun.started_at.desc())
            .limit(limit)
        )
    )


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
    # every content decision is an operator action -> the F14 audit log, so it
    # shows up in /admin/audit alongside flag/config changes (accountability)
    record_action(
        db,
        f"moderation_{status.value}",
        actor_account_id=moderator_account_id,
        target_kind=item.content_kind,
        target_ref=item.content_ref,
        detail={"reason": reason} if reason else {},
    )
    db.flush()
    return item


# AI-CONTEXT: the platform moderation promise — reported content is resolved within
# this window. It lives in F14 rather than in the module that first needed it (M13
# Q-8) because every module's queue makes the same promise to the same people, and a
# per-module SLA would quietly become several different promises.
MODERATION_SLA_HOURS = 72


def overdue_moderation(db: Session, now: datetime, sla_hours: float = MODERATION_SLA_HOURS):
    """Pending items past the SLA. An SLA nobody can see is not an SLA."""
    cutoff = now - timedelta(hours=sla_hours)
    return list(
        db.scalars(
            select(ModerationItem)
            .where(
                ModerationItem.status == ModerationStatus.pending,
                ModerationItem.created_at <= cutoff,
            )
            .order_by(ModerationItem.created_at)
        )
    )


def list_pending_moderation(db: Session, content_kind: str | None = None) -> list[ModerationItem]:
    stmt = select(ModerationItem).where(ModerationItem.status == ModerationStatus.pending)
    if content_kind is not None:
        stmt = stmt.where(ModerationItem.content_kind == content_kind)
    return list(db.scalars(stmt.order_by(ModerationItem.created_at)))


# --- Admin view registry ---
def register_admin_view(db: Session, key: str, module: str, title: str, path: str) -> AdminView:
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

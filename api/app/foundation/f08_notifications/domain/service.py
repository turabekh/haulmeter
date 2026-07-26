from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .enums import (
    DriverState,
    MessageDirection,
    NotificationChannel,
    NotificationStatus,
    NotificationTier,
    SuppressReason,
    TemplateAudience,
)
from .gateway import NotificationGateway
from .models import (
    Notification,
    NotificationClassPref,
    NotificationPrefs,
    NotificationTemplate,
    OutboundMessage,
    OutboundThread,
)

MAX_UNPROMPTED_P1_PER_DAY = 2
BUDGET_WINDOW = timedelta(hours=24)


# AI-CONTEXT: OPT-IN notification classes (design-prd §23 E-D1). A class is a named
# bundle of interruption laws stricter than the tier alone: it is off until the
# driver turns it on, it carries its own daily cap on top of the §13.1 budget, it
# can require route/favorite relevance, and it can be muted per subject. Classes are
# code-defined (like the tier table) so the laws are reviewable in one place; only
# the per-driver choice is data (NotificationClassPref).
@dataclass(frozen=True)
class NotificationClassSpec:
    key: str
    tier: NotificationTier
    max_per_day: int
    opt_in_default: bool = False
    route_relevant_only: bool = True


VENDOR_ALERT_CLASS = "vendor_alert"

NOTIFICATION_CLASSES: dict[str, NotificationClassSpec] = {
    # M13-FR6 anti-spam laws are PART of the class definition: opt-in only, at most
    # one vendor push per driver per day, route/favorite-relevant facilities only,
    # quiet hours respected (inherited from P1), one-tap mute per vendor.
    VENDOR_ALERT_CLASS: NotificationClassSpec(
        key=VENDOR_ALERT_CLASS,
        tier=NotificationTier.P1,
        max_per_day=1,
        opt_in_default=False,
        route_relevant_only=True,
    ),
}


def get_class(key: str) -> NotificationClassSpec | None:
    return NOTIFICATION_CLASSES.get(key)


class MissingDeepLink(Exception):
    pass


class NotRouteRelevant(Exception):
    pass


class CounterpartyMustBeEnglish(Exception):
    pass


# --- Preferences & timing ---
def get_or_create_prefs(db: Session, account_id) -> NotificationPrefs:
    prefs = db.get(NotificationPrefs, account_id)
    if prefs is None:
        prefs = NotificationPrefs(account_id=account_id)
        db.add(prefs)
        db.flush()
    return prefs


def in_quiet_hours(prefs: NotificationPrefs, now: datetime) -> bool:
    local = now.astimezone(ZoneInfo(prefs.timezone)).time()
    start, end = prefs.quiet_start, prefs.quiet_end
    if start <= end:
        return start <= local < end
    return local >= start or local < end


def p1_budget_used(db: Session, account_id, now: datetime) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.account_id == account_id,
            Notification.tier == NotificationTier.P1,
            Notification.status == NotificationStatus.sent,
            Notification.dispatched_at >= now - BUDGET_WINDOW,
        )
    )


# --- Opt-in class preferences (E-D1) ---
def get_class_pref(db: Session, account_id, class_key: str) -> NotificationClassPref | None:
    return db.scalar(
        select(NotificationClassPref).where(
            NotificationClassPref.account_id == account_id,
            NotificationClassPref.class_key == class_key,
        )
    )


def set_class_opt_in(
    db: Session, account_id, class_key: str, opted_in: bool
) -> NotificationClassPref:
    pref = get_class_pref(db, account_id, class_key)
    if pref is None:
        pref = NotificationClassPref(account_id=account_id, class_key=class_key)
        db.add(pref)
    pref.opted_in = opted_in
    db.flush()
    return pref


def is_opted_in(db: Session, account_id, class_key: str) -> bool:
    spec = get_class(class_key)
    if spec is None:
        return True  # not a governed class — ordinary tier rules apply
    pref = get_class_pref(db, account_id, class_key)
    if pref is None:
        return spec.opt_in_default  # no row = never asked = OFF for an opt-in class
    return pref.opted_in


def mute_subject(
    db: Session, account_id, class_key: str, subject_ref: str
) -> NotificationClassPref:
    # one-tap mute for a single vendor without leaving the whole class
    pref = get_class_pref(db, account_id, class_key)
    if pref is None:
        pref = NotificationClassPref(account_id=account_id, class_key=class_key)
        db.add(pref)
    pref.muted_subjects = sorted({*(pref.muted_subjects or []), str(subject_ref)})
    db.flush()
    return pref


def is_subject_muted(db: Session, account_id, class_key: str, subject_ref: str | None) -> bool:
    if subject_ref is None:
        return False
    pref = get_class_pref(db, account_id, class_key)
    return bool(pref and str(subject_ref) in (pref.muted_subjects or []))


# AI-CONTEXT: following — the positive half of the per-subject preference.
#
# A follow does three things at once, deliberately. It records the subject, it OPTS
# THE CLASS IN, and it clears any existing mute on that subject. E-D1 says silence is
# never consent, and a deliberate tap on "follow this cook" is not silence — it is a
# request to be told. The other two are failure modes the driver could never debug: a
# follow recorded into a class that is switched off, or onto a vendor they muted
# months ago, would be a control that reports success and does nothing.
def follow_subject(
    db: Session, account_id, class_key: str, subject_ref: str
) -> NotificationClassPref:
    pref = get_class_pref(db, account_id, class_key)
    if pref is None:
        pref = NotificationClassPref(account_id=account_id, class_key=class_key)
        db.add(pref)
    ref = str(subject_ref)
    pref.followed_subjects = sorted({*(pref.followed_subjects or []), ref})
    pref.muted_subjects = [s for s in (pref.muted_subjects or []) if s != ref]
    pref.opted_in = True
    db.flush()
    return pref


def unfollow_subject(
    db: Session, account_id, class_key: str, subject_ref: str
) -> NotificationClassPref | None:
    """Unfollowing leaves the class ON. Turning the whole class off is a separate,
    louder choice, and silently making it for someone who dropped one cook would take
    away notifications they never asked to lose."""
    pref = get_class_pref(db, account_id, class_key)
    if pref is None:
        return None
    ref = str(subject_ref)
    pref.followed_subjects = [s for s in (pref.followed_subjects or []) if s != ref]
    db.flush()
    return pref


def is_following(db: Session, account_id, class_key: str, subject_ref: str | None) -> bool:
    if subject_ref is None:
        return False
    pref = get_class_pref(db, account_id, class_key)
    return bool(pref and str(subject_ref) in (pref.followed_subjects or []))


def followers_of(db: Session, class_key: str, subject_ref: str) -> list:
    """The reverse lookup a caller needs to build an audience. Returns account ids
    that asked about this subject AND are still opted in — an account that later left
    the class is not an audience, whatever its follow list still says."""
    ref = str(subject_ref)
    rows = db.scalars(
        select(NotificationClassPref).where(
            NotificationClassPref.class_key == class_key,
            NotificationClassPref.opted_in.is_(True),
        )
    )
    return [p.account_id for p in rows if ref in (p.followed_subjects or [])]


def class_sends_today(db: Session, account_id, class_key: str, now: datetime) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.account_id == account_id,
            Notification.category == class_key,
            Notification.status == NotificationStatus.sent,
            Notification.dispatched_at >= now - BUDGET_WINDOW,
        )
    )


def _push_channel(driver_state: DriverState) -> NotificationChannel:
    return (
        NotificationChannel.audio
        if driver_state == DriverState.driving
        else NotificationChannel.push
    )


def dispatch(
    db: Session,
    account_id,
    tier: NotificationTier,
    category: str,
    title: str,
    body: str,
    deep_link: str,
    gateway: NotificationGateway,
    now: datetime | None = None,
    driver_state: DriverState = DriverState.idle,
    to_ref: str | None = None,
    subject_ref: str | None = None,
) -> Notification:
    if not deep_link:
        raise MissingDeepLink(
            "every notification must deep-link to its exact screen (design-prd §13.5)"
        )
    now = now or datetime.now(UTC)
    to_ref = to_ref or str(account_id)

    notification = Notification(
        account_id=account_id,
        tier=tier,
        category=category,
        title=title,
        body=body,
        deep_link=deep_link,
        status=NotificationStatus.pending,
    )
    db.add(notification)
    db.flush()

    def _suppress(reason: SuppressReason) -> Notification:
        notification.status = NotificationStatus.suppressed
        notification.suppress_reason = reason
        db.flush()
        return notification

    def _send(channel: NotificationChannel) -> Notification:
        gateway.send_push(to_ref, title, body)
        notification.status = NotificationStatus.sent
        notification.channel = channel
        notification.dispatched_at = now
        db.flush()
        return notification

    # Opt-in class laws (E-D1) apply BEFORE any tier logic: a class the driver never
    # turned on must not reach them at all, whatever tier it claims. `category` names
    # the class; categories with no registered class are unaffected.
    spec = get_class(category)
    if spec is not None:
        if not is_opted_in(db, account_id, category):
            return _suppress(SuppressReason.not_opted_in)
        if is_subject_muted(db, account_id, category, subject_ref):
            return _suppress(SuppressReason.muted)
        if class_sends_today(db, account_id, category, now) >= spec.max_per_day:
            return _suppress(SuppressReason.budget)

    if tier == NotificationTier.P2:
        notification.status = NotificationStatus.digested
        notification.channel = NotificationChannel.in_app
        db.flush()
        return notification

    if tier == NotificationTier.P0:
        return _send(_push_channel(driver_state))

    # P1 — respects RESTING state, quiet hours, and the interruption budget
    if driver_state == DriverState.resting:
        return _suppress(SuppressReason.resting)
    prefs = get_or_create_prefs(db, account_id)
    if in_quiet_hours(prefs, now):
        return _suppress(SuppressReason.quiet_hours)
    if p1_budget_used(db, account_id, now) >= MAX_UNPROMPTED_P1_PER_DAY:
        return _suppress(SuppressReason.budget)
    return _send(_push_channel(driver_state))


def digest(db: Session, account_id) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification)
            .where(
                Notification.account_id == account_id,
                Notification.status == NotificationStatus.digested,
            )
            .order_by(Notification.created_at)
        )
    )


# --- Template registry (versioned; counterparty always English, F15) ---
def register_template(
    db: Session,
    key: str,
    body_template: str,
    audience: TemplateAudience,
    channel: NotificationChannel,
    locale: str = "en",
    version: int = 1,
    subject_template: str | None = None,
    active: bool = True,
) -> NotificationTemplate:
    if audience == TemplateAudience.counterparty and locale != "en":
        raise CounterpartyMustBeEnglish("counterparty-facing templates are always English (F15)")
    template = NotificationTemplate(
        key=key,
        locale=locale,
        version=version,
        audience=audience,
        channel=channel,
        subject_template=subject_template,
        body_template=body_template,
        active=active,
    )
    db.add(template)
    db.flush()
    return template


def get_active_template(db: Session, key: str, locale: str = "en") -> NotificationTemplate | None:
    return db.scalar(
        select(NotificationTemplate)
        .where(
            NotificationTemplate.key == key,
            NotificationTemplate.locale == locale,
            NotificationTemplate.active.is_(True),
        )
        .order_by(NotificationTemplate.version.desc())
        .limit(1)
    )


def render_template(template: NotificationTemplate, context: dict) -> tuple[str | None, str]:
    def _sub(text: str | None) -> str | None:
        if text is None:
            return None
        for key, value in context.items():
            text = text.replace("{" + key + "}", str(value))
        return text

    return _sub(template.subject_template), _sub(template.body_template)


# --- Outbound counterparty threads (sent/opened tracking, reply routing) ---
def create_thread(
    db: Session,
    account_id,
    subject: str,
    counterparty_ref=None,
    template_key: str | None = None,
    reply_to: str | None = None,
) -> OutboundThread:
    thread = OutboundThread(
        account_id=account_id,
        subject=subject,
        counterparty_ref=counterparty_ref,
        template_key=template_key,
        reply_to=reply_to,
    )
    db.add(thread)
    db.flush()
    return thread


def send_counterparty_message(
    db: Session,
    thread: OutboundThread,
    body: str,
    gateway: NotificationGateway,
    to_ref: str,
    now: datetime | None = None,
) -> OutboundMessage:
    now = now or datetime.now(UTC)
    provider_ref = gateway.send_email(to_ref, thread.subject, body)
    message = OutboundMessage(
        thread_id=thread.id,
        direction=MessageDirection.outbound,
        body=body,
        provider_ref=provider_ref,
        sent_at=now,
    )
    db.add(message)
    db.flush()
    return message


def mark_opened(
    db: Session, message: OutboundMessage, now: datetime | None = None
) -> OutboundMessage:
    message.opened_at = now or datetime.now(UTC)
    db.flush()
    return message


def record_inbound_reply(db: Session, thread: OutboundThread, body: str) -> OutboundMessage:
    message = OutboundMessage(thread_id=thread.id, direction=MessageDirection.inbound, body=body)
    db.add(message)
    db.flush()
    return message

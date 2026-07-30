from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
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
    PushSubscription,
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
    # AI-CONTEXT: §13.1's budget is a defence against nagging, and a DEADLINE is not a
    # nag. A budget-exempt class neither loses to the 2/day pool nor spends it — both
    # halves matter, because a class that skipped the check while still consuming a
    # slot would quietly cost the driver one of their two ordinary nudges.
    budget_exempt: bool = False


VENDOR_ALERT_CLASS = "vendor_alert"
PROTECTION_GAP_CLASS = "protection_gap"
LOT_STATUS_PROMPT_CLASS = "lot_status_prompt"

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
    # M5-FR5's EXIT carve-out (§23 entry 56, owner-approved — a notification class is
    # a §22 never-improvise category and was not composed here unilaterally).
    #
    # An irrecoverable gap at a state transition is a DEADLINE, not a nag: once the
    # driver has pulled off the dock they cannot photograph that trailer at that
    # facility, ever. So it is exempt from the 2/day budget — a deadline must not lose
    # to two softer nudges already spent — but capped at one a day, still muted in
    # quiet hours and while RESTING, and on by default because a driver cannot opt in
    # to a warning they have never seen.
    # M1-FR7's missing half (§23 entry 112, owner-approved). The product had never
    # ASKED a driver anything: the report chip is driver-initiated and the live fan-out
    # only delivers. This class is the ask, and every field of it is a claim.
    #
    # P1, not P0: nobody's money or safety turns on a lot's fullness.
    # ONE a day: a driver who stops three times should be asked once, not three times.
    # OPT-IN OFF by default, which is the field most worth arguing about — this asks
    #   the driver for LABOUR, and §21.8 forbids helping ourselves to it. The cost is
    #   real: most drivers will never see it unless they go looking, and the answer to
    #   low uptake is a better offer, not a default that takes without asking.
    # ROUTE-RELEVANCE OFF because they are standing in the lot; relevance is PROVEN by
    #   the geofence rather than inferred from a route, which is the opposite of the
    #   vendor case this flag was written for.
    # NOT BUDGET-EXEMPT, deliberately: `protection_gap` earned its exemption by being a
    #   DEADLINE — the trailer cannot be photographed at that dock ever again — and a
    #   survey is the exact opposite. It must LOSE to real news rather than crowd it out.
    LOT_STATUS_PROMPT_CLASS: NotificationClassSpec(
        key=LOT_STATUS_PROMPT_CLASS,
        tier=NotificationTier.P1,
        max_per_day=1,
        opt_in_default=False,
        route_relevant_only=False,
        budget_exempt=False,
    ),
    PROTECTION_GAP_CLASS: NotificationClassSpec(
        key=PROTECTION_GAP_CLASS,
        tier=NotificationTier.P1,
        max_per_day=1,
        opt_in_default=True,
        route_relevant_only=False,
        budget_exempt=True,
    ),
}

# the categories whose sends do not count against anyone's §13.1 allowance
BUDGET_EXEMPT_CLASSES = frozenset(
    key for key, spec in NOTIFICATION_CLASSES.items() if spec.budget_exempt
)


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


class UnknownTimezone(Exception):
    pass


def set_prefs(
    db: Session,
    account_id,
    timezone: str | None = None,
    quiet_start: time | None = None,
    quiet_end: time | None = None,
) -> NotificationPrefs:
    """§13.3's window and the zone it is measured in (§23 entry 115).

    AI-CONTEXT: `timezone` defaulted to "UTC" and **nothing in the tree ever wrote it**,
    so "22:00-06:00 local" landed on the wrong eight hours for every driver — silenced
    through the working afternoon and reachable at 03:00. The column existed and had no
    door; see tests/foundation/f08_notifications/test_quiet_hours.py for the measured
    per-zone table.

    EVERY FIELD IS OPTIONAL, and that is load-bearing rather than convenience: the client
    PUTs the browser's detected zone on every sign-in, and a whole-object write would
    silently undo a window the driver had set. A test holds it.

    The zone is validated by `ZoneInfo`'s own lookup — the only check that stays true as
    tzdata changes, and the same object `in_quiet_hours` will use, so a value that stores
    cannot fail at read time.
    """
    prefs = get_or_create_prefs(db, account_id)
    if timezone is not None:
        try:
            ZoneInfo(timezone)
        except Exception as exc:
            raise UnknownTimezone(timezone) from exc
        prefs.timezone = timezone
    if quiet_start is not None:
        prefs.quiet_start = quiet_start
    if quiet_end is not None:
        prefs.quiet_end = quiet_end
    db.flush()
    return prefs


def in_quiet_hours(prefs: NotificationPrefs, now: datetime) -> bool:
    local = now.astimezone(ZoneInfo(prefs.timezone)).time()
    start, end = prefs.quiet_start, prefs.quiet_end
    if start <= end:
        return start <= local < end
    return local >= start or local < end


def p1_budget_used(db: Session, account_id, now: datetime) -> int:
    # a budget-exempt class does not SPEND the allowance either — see
    # NotificationClassSpec.budget_exempt. Skipping the check while still consuming a
    # slot would take one of the driver's two ordinary nudges to pay for a deadline.
    return db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.account_id == account_id,
            Notification.tier == NotificationTier.P1,
            Notification.status == NotificationStatus.sent,
            Notification.dispatched_at >= now - BUDGET_WINDOW,
            Notification.category.notin_(BUDGET_EXEMPT_CLASSES),
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


def unmute_subject(
    db: Session, account_id, class_key: str, subject_ref: str
) -> NotificationClassPref | None:
    """The half `mute_subject` shipped without (§23 entry 114).

    AI-CONTEXT: the only existing way out of a mute was `follow_subject`, which is
    vendor-shaped and ALSO switches the whole class on — so a driver who silenced one
    lot had no way back that did not change something else. `core/push.js` states the
    rule this breaks outright: turning it off is exactly as easy as turning it on.

    It deliberately leaves `opted_in` alone, which is `unfollow_subject`'s reasoning
    mirrored: un-silencing one facility is not a class-level choice, and quietly making
    that louder choice for someone would hand them notifications they never asked for.
    Returns None when there was no preference row — asking for a state you are already
    in is not a failure (the same posture as `/push/unsubscribe`).
    """
    pref = get_class_pref(db, account_id, class_key)
    if pref is None:
        return None
    ref = str(subject_ref)
    pref.muted_subjects = [s for s in (pref.muted_subjects or []) if s != ref]
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
    actions: list[dict] | None = None,
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
        # §13.5 travels WITH the push: one definition of "where this is about" serves
        # the tray entry and the inbox row, so the two can never disagree.
        gateway.send_push(to_ref, title, body, deep_link, actions)
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
    # a budget-exempt class has already passed its own per-day cap above; it does not
    # then have to win a place in the shared 2/day pool. Quiet hours and RESTING still
    # apply — exempt from the BUDGET is not exempt from the driver's sleep.
    if not (spec is not None and spec.budget_exempt):
        if p1_budget_used(db, account_id, now) >= MAX_UNPROMPTED_P1_PER_DAY:
            return _suppress(SuppressReason.budget)
    return _send(_push_channel(driver_state))


# AI-CONTEXT: the driver's own inbox — the surface §23 entry 429 said had to exist
# before anything could be filed P2, generalised to everything F8 decides.
#
# It returns EVERY notification addressed to the account, including the ones the
# budget or quiet hours suppressed, and that is deliberate. §13.1's cap of two per day
# governs UNPROMPTED interruptions — a driver who opens a list is not being
# interrupted, they are asking.
#
# THIS LIST IS THE ONLY DELIVERY A SUPPRESSED NOTIFICATION EVER GETS (§13.3, owner
# decision in §23 entry 116). Nothing re-dispatches when the quiet window closes, so
# hiding a suppressed P1 here would not be "deferring" it — it would be destroying it.
# That is why the inbox renders them, and why no surface may say one is on its way.
#
# `pending` is excluded: it has not been decided yet, and showing a driver something
# the system has not finished thinking about is how a half-written row becomes a fact.
INBOX_STATUSES = (
    NotificationStatus.sent,
    NotificationStatus.digested,
    NotificationStatus.suppressed,
)
# a working inbox, not an archive. The driver's history lives in the records the
# notifications point AT — the load, the claim, the booking — never in the telling.
INBOX_LIMIT = 50


def inbox(db: Session, account_id, limit: int = INBOX_LIMIT) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification)
            .where(
                Notification.account_id == account_id,
                Notification.status.in_(INBOX_STATUSES),
            )
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
    )


def unread_count(db: Session, account_id) -> int:
    return len(
        [n for n in inbox(db, account_id) if n.read_at is None]
    )


def mark_notification_read(
    db: Session, notification: Notification, now: datetime | None = None
) -> Notification:
    # idempotent: the FIRST read is the interesting one, and a second tap must not
    # rewrite when the driver learned something
    if notification.read_at is None:
        notification.read_at = now or datetime.now(UTC)
        db.flush()
    return notification


def get_notification(db: Session, notification_id) -> Notification | None:
    return db.get(Notification, notification_id)


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


# --- Push subscriptions: where a P0 actually goes (§23 entry 111) ---
def save_subscription(db: Session, account_id, endpoint: str, p256dh: str, auth: str):
    """Idempotent by ENDPOINT, which is the natural key.

    AI-CONTEXT: a browser re-subscribes on its own schedule — a service-worker update,
    a key rotation by the push service, a reinstall — and every one of those returns
    the same endpoint or a new one for the same device. Keyed on endpoint, a
    re-subscribe updates; keyed on account it would either clobber a driver's second
    device or accumulate rows that all buzz the same phone.

    An endpoint that reappears under a DIFFERENT account is reassigned rather than
    duplicated: one browser has one owner, and the last person to log in on it is that
    owner. The alternative — two accounts pushing to one device — would send a driver
    someone else's money alerts.
    """
    existing = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
    now = datetime.now(UTC)
    if existing is not None:
        existing.account_id = account_id
        existing.p256dh = p256dh
        existing.auth = auth
        existing.last_seen_at = now
        db.flush()
        return existing
    sub = PushSubscription(
        account_id=account_id,
        endpoint=endpoint,
        p256dh=p256dh,
        auth=auth,
        last_seen_at=now,
    )
    db.add(sub)
    db.flush()
    return sub


def subscriptions_for(db: Session, account_id) -> list:
    return list(
        db.scalars(select(PushSubscription).where(PushSubscription.account_id == account_id))
    )


def drop_subscription(db: Session, subscription) -> None:
    db.delete(subscription)
    db.flush()


def drop_subscription_by_endpoint(db: Session, account_id, endpoint: str) -> bool:
    """Unsubscribe. Scoped to the account so one driver cannot silence another."""
    sub = db.scalar(
        select(PushSubscription).where(
            PushSubscription.endpoint == endpoint,
            PushSubscription.account_id == account_id,
        )
    )
    if sub is None:
        return False
    drop_subscription(db, sub)
    return True


def has_notification_since(db: Session, account_id, category: str, since) -> bool:
    """Was this class already OFFERED to this driver lately? (§23 entry 112)

    AI-CONTEXT: counts ATTEMPTS, not deliveries, and that distinction is the point. A
    caller that re-offers on every position ping would otherwise write a suppressed row
    each time it lost to the budget — and the inbox deliberately RENDERS suppressed rows
    (§23 entry 102), so a driver dwelling for eight hours would open it to find ninety
    identical held prompts. Suppression is a decision about ONE notification, not a
    licence to keep making the same one.

    Scoped to the CATEGORY and not to a subject, because `Notification` does not store
    `subject_ref` — that argument exists for the mute check and is not persisted. For a
    class capped at one a day the distinction does not arise, and inventing a column to
    make this read prettier would be the tail wagging the dog.
    """
    return (
        db.scalar(
            select(Notification.id)
            .where(
                Notification.account_id == account_id,
                Notification.category == category,
                Notification.created_at >= since,
            )
            .limit(1)
        )
        is not None
    )

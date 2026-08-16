from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings

from .enums import (
    DriverState,
    MessageDirection,
    NotificationChannel,
    NotificationStatus,
    NotificationTier,
    SuppressReason,
    TemplateAudience,
)
from .gateway import NotificationGateway, gateway_for, is_failure, is_retryable
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

# AI-CONTEXT: the states in which a notification has cost the driver an interruption.
# `queued` is here because the decision has been taken and the push is going; excluding
# it would let a burst inside one delivery sweep pass every cap in §13.1.
_SPENDS_ATTENTION = (NotificationStatus.queued, NotificationStatus.sent)


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


ARRIVAL_REMINDER_CLASS = "arrival_reminder"
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
    # J1-D1 (§23 entry 169, owner-signed — a notification class is a §22.2
    # never-improvise category and entry 118's delegation does not cover one).
    #
    # OPT-IN DEFAULT **ON**, which is the opposite of `lot_status_prompt` above and for a
    # stated reason: that class asks the driver for LABOUR (§21.8 forbids helping
    # ourselves to it), while this one fires only for an appointment the driver RECORDED,
    # on a stop the driver ARMED. They have already asked.
    # TWO a day, not one: a two-stop day is an ordinary day.
    # NOT BUDGET-EXEMPT: `protection_gap` earned its exemption by being a DEADLINE — that
    #   trailer cannot be photographed at that dock ever again — and a reminder about
    #   something still ahead of you must LOSE to real news rather than crowd it out.
    # ROUTE-RELEVANCE OFF: relevance is the driver's own armed stop, not a route. The
    #   geofence-free design is the point — this has to work on a handset that never
    #   granted background location (§15.5, Phase DoD #8).
    ARRIVAL_REMINDER_CLASS: NotificationClassSpec(
        key=ARRIVAL_REMINDER_CLASS,
        tier=NotificationTier.P1,
        max_per_day=2,
        opt_in_default=True,
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
            # AI-CONTEXT: `queued` COUNTS. §13.1's budget is a defence against nagging,
            # and a driver's attention is spent the moment the product commits to
            # interrupting them — not when a push service accepts the POST a minute
            # later. Counting only `sent` would have made the budget, and every
            # per-class daily cap, silently stop working the day delivery became
            # asynchronous: a burst inside one sweep window would all read zero used.
            #
            # The window moves to `decided_at` for the same reason: `dispatched_at` is
            # NULL until delivery, so a window measured on it cannot see a decision
            # already taken. NOT `created_at` — that is a server default and ignores the
            # `now` a caller passes, which would make this wrong for every job that
            # replays with a historical clock.
            Notification.status.in_(_SPENDS_ATTENTION),
            Notification.decided_at >= now - BUDGET_WINDOW,
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
            # see `p1_budget_used`: a decision to interrupt spends the cap whether or not
            # the push service has accepted it yet
            Notification.status.in_(_SPENDS_ATTENTION),
            Notification.decided_at >= now - BUDGET_WINDOW,
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
        """AI-CONTEXT: QUEUES it. The decision is made here; the HTTP call is not.

        `send_push` is a POST per subscription with a ten-second timeout, and it ran
        inside the request handler — holding a pooled database connection and a
        threadpool slot on a third party, for as many round trips as the driver has
        browsers. §23 records that exact outage: "QueuePool limit of size 5 overflow
        10 reached", the API out of connections and answering nothing.

        EVERYTHING THAT DECIDES STAYS HERE. The channel depends on `driver_state` at
        this moment, quiet hours on `now`, the budget on what has already gone — all
        of them are facts about the instant a driver would be interrupted, and none of
        them survive being re-evaluated a minute later by a janitor. Only the transport
        moves.

        §13.5 travels WITH the push: one definition of "where this is about" serves the
        tray entry and the inbox row, so the two can never disagree.
        """
        _ = gateway  # the transport is the delivery sweep's business now
        notification.status = NotificationStatus.queued
        notification.channel = channel
        notification.actions = actions
        # the interruption is spent HERE, at the caller's `now` — see `decided_at`
        notification.decided_at = now
        # `dispatched_at` stays NULL: it means the push service accepted it, and nothing
        # has been offered to a push service yet.
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
# `queued` IS rendered, and that is the same argument as `suppressed` one paragraph up.
# The decision has been taken — every §13.1 law was applied and the notification is going
# — so the only thing still outstanding is a POST to a push service. Hiding it until then
# would mean a driver who opens the app in the minute after their detention clock expired
# sees an empty inbox and concludes nothing happened, which is the one reading the whole
# §13.2 P0 exists to prevent. It is a notification; the tray is not the only place it lives.
INBOX_STATUSES = (
    NotificationStatus.queued,
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


# --- Driver-facing text, in the driver's language (finding N-02) ---
# AI-CONTEXT: every `dispatch` call site passed an English literal title and body, so a
# driver who reads none of it got M3's detention P0 — the product's most important alert —
# in a language they had not chosen. PRD §7.15's coverage rule names notifications in the
# same breath as UI and voice.
#
# THE LOOKUP LIVES HERE rather than in each module because F8 is what already knows the
# account: ten call sites resolving a locale ten times is ten chances to resolve it
# differently, and the one that forgot would be invisible. A module says WHAT to say; F8
# decides which language to say it in, exactly as it already decides the channel and
# whether quiet hours suppress it.
#
# A MISSING ROW FALLS BACK TO THE COMPILED ENGLISH, never to a blank or a raw key — the
# same rule N-01 applies to voice, and F-17's third option before that. A notification is
# the one surface where a silent failure IS the failure.
def localized_text(db: Session, account_id, key: str, fallback: str, **values) -> str:
    from app.foundation.f01_identity import public as identity
    from app.foundation.f15_localization import public as localization

    account = db.get(identity.Account, account_id)
    locale = (
        localization.get_user_locale(db, account)
        if account is not None
        else localization.DEFAULT_LOCALE
    )
    text = localization.get_message(db, key, locale) or fallback
    return text.format(**values) if values else text


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
    gateway: NotificationGateway | None = None,
    to_ref: str = "",
    now: datetime | None = None,
    dedupe_key: str | None = None,
    attachment_key: str | None = None,
    attachment_name: str | None = None,
) -> OutboundMessage:
    """Record the decision to send. The BYTES leave on the `outbound_mail` sweep.

    AI-CONTEXT: this used to open an SMTP connection inline, inside the request handler.
    Measured against the configured provider — connect, STARTTLS, AUTH, sending nothing —
    that is **2.5 seconds** before a single byte of a notice moves, and `timeout=10`
    means a bad minute costs ten seconds of a frozen button on the screen where a driver
    taps Send at a dock.

    The wait was the smaller half. A `def` handler runs in a bounded threadpool and holds
    a POOLED DATABASE CONNECTION for the whole round trip, so every send parked one of
    both on a third party. §23 already records that exact outage — *"QueuePool limit of
    size 5 overflow 10 reached"*, the API out of connections and answering nothing — and
    `run_dunning` walks a whole receivable list in one pass.

    Nothing here is new machinery. F8 has always modelled the row as the record that we
    DECIDED to send, `unsent_messages` has always been able to find one, and
    `retry_unsent_messages` has always been able to deliver it: the outbox existed and
    one inline call was jumping the queue. So this writes the row and returns.

    `gateway` is kept in the signature and deliberately unused. Every caller passes one,
    and a parameter removed here is a five-module edit for no behavioural gain — while
    leaving it means a future caller cannot accidentally re-introduce an inline send by
    passing a gateway and expecting it to be used. `_ = gateway` says that out loud.
    """
    _ = gateway  # the transport is the sweep's business now, not the caller's
    now = now or datetime.now(UTC)

    # AI-CONTEXT: ONE MESSAGE PER PURPOSE, and the constraint is what enforces it.
    #
    # This lookup is the fast path, not the guarantee. §23 closed the four money races on
    # the reasoning that **an application check reads rows a concurrent transaction has
    # not committed yet** — two taps landing together, or a request racing the offline
    # queue's replay, both pass this SELECT and both go on to insert. The partial unique
    # index is what makes the second one impossible; this only saves the round trip and
    # returns the same row a caller would have got anyway.
    if dedupe_key:
        existing = existing_by_dedupe_key(db, dedupe_key)
        if existing is not None:
            return existing

    message = OutboundMessage(
        thread_id=thread.id,
        direction=MessageDirection.outbound,
        body=body,
        to_ref=to_ref,
        dedupe_key=dedupe_key,
        # AI-CONTEXT: NULL, and the three NULLs mean three different things. `provider_ref`
        # NULL is "never attempted" — distinct from a `smtp-failed-…` ref, which is "tried
        # and did not go". `sent_at` NULL is what audit F-06 made load-bearing: only a send
        # that actually went out gets one, so a row can never claim a delivery it did not
        # get. `attempts` 0 is what tells the sweep this is a first delivery rather than a
        # retry, which is the difference between the driver seeing `queued` and `retrying`.
        provider_ref=None,
        sent_at=None,
        attempts=0,
        attachment_key=attachment_key,
        attachment_name=attachment_name,
    )
    # AI-CONTEXT: a SAVEPOINT, not a plain flush, and the difference matters twice over.
    #
    # This is the race the index exists for: another transaction commits the same purpose
    # between our SELECT above and our INSERT here — a double tap, or a request arriving
    # alongside the offline queue replaying the same capture. Postgres refuses the second
    # row, which is exactly right, and leaves the transaction unusable until something
    # unwinds it.
    #
    # `begin_nested()` scopes that unwind to THIS insert. A bare `db.rollback()` would
    # discard the caller's whole transaction — the claim, the evidence record, the
    # receivable — to recover from a duplicate we are choosing to tolerate. It would also
    # silently destroy the surrounding work in the test session, which runs everything
    # inside one outer transaction.
    #
    # Losing this race is a SUCCESS: both callers return the same message, and the broker
    # gets one email.
    try:
        with db.begin_nested():
            db.add(message)
            db.flush()
    except IntegrityError:
        winner = existing_by_dedupe_key(db, dedupe_key) if dedupe_key else None
        if winner is None:
            raise
        return winner
    return message


def queued_notifications(db: Session, limit: int = 100) -> list[Notification]:
    """Pushes the product has committed to and not yet handed to a push service."""
    return list(
        db.scalars(
            select(Notification)
            .where(Notification.status == NotificationStatus.queued)
            .order_by(Notification.created_at)
            .limit(limit)
        )
    )


def deliver_queued_notifications(
    db: Session, gateway_factory=None, now: datetime | None = None, limit: int = 100
) -> dict:
    """Hand queued pushes to the push service. The `push_delivery` sweep's whole job.

    AI-CONTEXT: the gateway is built PER ACCOUNT, which is why this takes a factory
    rather than a gateway. `gateway_for(db, account_id)` reads that driver's own
    subscriptions — a push is addressed to browsers, not to an address — so one shared
    instance would send every driver's notification to whoever the first one belonged to.

    A FAILURE LEAVES IT QUEUED. `WebPushNotificationGateway` never raises: it drops a
    subscription the push service has permanently rejected (410/404) and swallows the
    rest, because a service having a bad minute is not a reason to lose a P0. So a
    notification that reaches no browser stays `queued` and the next sweep tries again —
    the same rule the mail sweep follows, and the reason `status` is the queue rather
    than a separate table.

    THE DECISION IS NOT RE-EVALUATED. Quiet hours, the interruption budget and the
    DRIVING/RESTING channel were all settled when the notification was created; they are
    facts about the moment a driver would have been interrupted. Re-asking them here
    would let a notification decided at 21:59 be silently dropped at 22:01.
    """
    now = now or datetime.now(UTC)
    factory = gateway_factory or (lambda account_id: gateway_for(db, account_id))
    delivered = failed = 0
    for notification in queued_notifications(db, limit):
        gateway = factory(notification.account_id)
        try:
            gateway.send_push(
                str(notification.account_id),
                notification.title,
                notification.body,
                notification.deep_link,
                notification.actions,
            )
        except Exception:
            # a gateway that raises is a defect in the gateway, not a reason to lose the
            # row. It stays queued and the next sweep tries again.
            failed += 1
            continue
        notification.status = NotificationStatus.sent
        notification.dispatched_at = now
        delivered += 1
    db.flush()
    return {"delivered": delivered, "failed": failed}


def _attachments_for(message) -> list:
    """Resolve the message's attachment to bytes, at SEND time.

    AI-CONTEXT: here rather than at the request, because delivery is asynchronous — the
    row carries a storage key and the sweep is what turns it into a document. Storing the
    bytes on the row would put a multi-megabyte PDF in Postgres for every send.

    THREE WAYS IT DECLINES, and all of them leave the mail going out. The link is in the
    body regardless, so a missing attachment costs a broker one click and never a delivery:

      · no key — most counterparty mail has no pack
      · too large — a whole-load record with two dozen photographs lands near the size
        many corporate filters reject outright, and a bounced notice is worse than a
        linked one. Measured: 96 KB median today, 2.2 MB for a pack with four real photos
      · unreadable — the object is gone, or storage is briefly unwell. Attaching nothing
        is right; failing the send over it would lose the notice as well as the document
    """
    if not message.attachment_key:
        return []
    cap = get_settings().max_email_attachment_mb * 1024 * 1024
    try:
        from app.foundation.f06_documents import public as documents

        data = documents.default_storage().get(message.attachment_key)
    except Exception:
        return []
    if len(data) > cap:
        return []
    return [(message.attachment_name or "record.pdf", data)]


def release_dedupe_key(db: Session, message: OutboundMessage) -> None:
    """Give up a message's claim on its purpose, so a fresh one may take it.

    AI-CONTEXT: the key answers "has this purpose been served?", and there is a case where
    the honest answer is no even though a row exists — a notice that failed PERMANENTLY,
    or one addressed to an email the driver has since corrected. The broker never received
    it, so a replacement is not a duplicate; it is the first delivery.

    Only a caller that owns the purpose can know this. M3's `_existing_start_notice`
    already encodes the rule in five cases and is the authority; this is how it hands the
    key over. The ROW IS NOT TOUCHED otherwise — it keeps its body, its recipient and its
    `smtp-failed-…` ref, because "we tried and it bounced" is history a dispute may need,
    and the address-aware rule exists precisely so that history is not rewritten.
    """
    message.dedupe_key = None
    db.flush()


def existing_by_dedupe_key(db: Session, dedupe_key: str) -> OutboundMessage | None:
    """The message already serving this purpose, if there is one."""
    return db.scalars(
        select(OutboundMessage).where(OutboundMessage.dedupe_key == dedupe_key)
    ).first()


MAX_SEND_ATTEMPTS = 5


def unsent_messages(db: Session, limit: int = 50) -> list[OutboundMessage]:
    """Outbound mail that has not gone out — the dead-letter queue, such as it is.

    AI-CONTEXT: F8 already had the rows; what it lacked was a reason to look at them.
    A failed send returned a string nobody read, `sent_at` was written anyway, and the
    notice was gone. With A12's "no monitoring" nothing would ever have surfaced it.
    """
    return list(
        db.scalars(
            select(OutboundMessage)
            .where(
                OutboundMessage.direction == MessageDirection.outbound,
                OutboundMessage.sent_at.is_(None),
                OutboundMessage.attempts < MAX_SEND_ATTEMPTS,
            )
            .order_by(OutboundMessage.created_at)
            .limit(limit)
        )
    )


def retry_unsent_messages(
    db: Session, gateway: NotificationGateway, now: datetime | None = None, limit: int = 50
) -> dict:
    """Re-send what did not go. Returns a summary for the worker log.

    AI-CONTEXT: one SMTP attempt with a ten-second timeout was the whole delivery
    strategy, so a transient blip or a Gmail rate limit permanently lost a detention
    notice — the document the entire detention wedge exists to deliver.

    Permanent failures are NOT retried (see `PERMANENT_FAILURES`): repeatedly presenting
    a bad App Password to Gmail is how an account gets locked, which would turn one
    broken notice into every broken notice. They stop here with `sent_at` still NULL, so
    they stay visible rather than being quietly abandoned.
    """
    now = now or datetime.now(UTC)
    sent = retried = abandoned = delivered_first_try = 0
    delivered: list[OutboundMessage] = []
    for message in unsent_messages(db, limit):
        # AI-CONTEXT: a NEVER-ATTEMPTED row is not a failed one, and this gate could not
        # tell them apart. `is_retryable(None)` is False — it asks "is this failure worth
        # another go?" of something that has not been tried — so the moment sends became
        # asynchronous, every first delivery would have been counted `abandoned` and
        # dropped on the very first sweep. The whole outbox would have looked like it was
        # working: rows in, rows out, a tidy summary, and no mail.
        first_attempt = message.provider_ref is None
        if not first_attempt and not is_retryable(message.provider_ref):
            abandoned += 1
            continue
        thread = db.get(OutboundThread, message.thread_id)
        if thread is None or not message.to_ref:
            # a row from before `to_ref` was recorded cannot be re-addressed. Left
            # unsent and counted rather than guessed at — sending a broker's detention
            # notice to an address we inferred is worse than not sending it.
            abandoned += 1
            continue
        if first_attempt:
            delivered_first_try += 1
        else:
            retried += 1
        message.attempts += 1
        message.provider_ref = gateway.send_email(
            message.to_ref, thread.subject, message.body, _attachments_for(message)
        )
        if not is_failure(message.provider_ref):
            message.sent_at = now
            sent += 1
            delivered.append(message)
    db.flush()
    # AI-CONTEXT: `delivered` is returned so a CALLER can reconcile. `notice_delivery`'s
    # docstring records an "ACCEPTED ASYMMETRY" — a message that succeeds on the sweep
    # gains no `notice_sent` evidence record, because nothing re-enters that code path —
    # and that was tolerable while the sweep only handled the rare failure. Now that it
    # handles EVERY send, the same asymmetry would strip the "we notified the broker at
    # 10:05" line out of every detention pack, which is the line a dispute turns on. F8
    # cannot fix that itself (it sits below the modules); it can hand back what went.
    return {
        "sent": sent,
        "first_delivery": delivered_first_try,
        "retried": retried,
        "abandoned": abandoned,
        "delivered": delivered,
    }


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

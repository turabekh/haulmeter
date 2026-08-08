"""AI-CONTEXT: M3's driver alerts — the P0 design-prd §13.2 names first (§23 106/107).

These tests exist because a green suite said nothing about the gap they cover. F8 had
decided tiers, budgets and quiet hours since it shipped and M3 had never called
`dispatch` at all: there was no failing assertion anywhere, because nothing was wrong
with the code that existed — the code that mattered had not been written.

So what is asserted here is mostly BOUNDARIES and ABSENCES: that nothing fires before
free time is used up, that nothing fires twice, that a P0 outlives a spent budget while
a P1 does not, and that the deep link is a claim and not a tab root.
"""

from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f05_load import public as loads
from app.foundation.f08_notifications import public as notify
from app.modules.m03_detention import public as m3

DALLAS = (32.7767, -96.7970)
FAR = (32.9000, -96.8000)
T0 = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)  # arrival; free time runs to 10:00
EXPIRY = T0 + timedelta(minutes=120)


def _claim(db, authority=identity.AuthorityType.own_mc, email="oo@example.com", rate=7500):
    account = identity.register_account(db, email, "pw-123456")
    identity.upsert_driver_profile(db, account, authority_type=authority)
    dock = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Dock", *DALLAS)
    broker = loads.create_counterparty(
        db, "Acme", loads.CounterpartyKind.broker, contact_email="ap@acme.com"
    )
    load = loads.create_load(
        db,
        account.id,
        counterparty_id=broker.id,
        detention_rate_cents_per_hour=rate,
        free_time_minutes=120,
    )
    stop = loads.add_stop(db, load, dock.id, loads.StopType.delivery, appointment_start=T0)
    claim = m3.start_claim(db, stop, started_at=T0)
    return account, stop, claim


def _arrive(db, account, at=T0):
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=at)


def _depart(db, account, at):
    location.evaluate_ping(db, account.id, *FAR, occurred_at=at)


# --- the boundary itself: nothing before free time is used up ---
def test_no_alert_while_free_time_remains(db):
    account, stop, claim = _claim(db)
    _arrive(db, account)
    gw = notify.RecordingNotificationGateway()

    assert m3.dispatch_detention_start(db, claim, gw, T0 + timedelta(minutes=60)) is None
    assert gw.sent == []
    assert claim.driver_start_alert_at is None


def test_p0_fires_at_free_time_expiry(db):
    account, stop, claim = _claim(db)
    _arrive(db, account)
    gw = notify.RecordingNotificationGateway()

    sent = m3.dispatch_detention_start(db, claim, gw, EXPIRY + timedelta(minutes=1))

    assert sent is not None
    assert sent.tier == notify.NotificationTier.P0
    assert sent.status == notify.NotificationStatus.sent
    # §12.6 verbatim: figure-first fact + single action
    assert sent.title == "Detention started · $75/h"
    assert sent.body == "Free time is used up at this stop. Notice ready to send."
    assert claim.driver_start_alert_at is not None


def test_p0_fires_once_and_only_once(db):
    account, stop, claim = _claim(db)
    _arrive(db, account)
    gw = notify.RecordingNotificationGateway()
    later = EXPIRY + timedelta(minutes=1)

    assert m3.dispatch_detention_start(db, claim, gw, later) is not None
    assert m3.dispatch_detention_start(db, claim, gw, later + timedelta(minutes=1)) is None
    assert m3.dispatch_detention_start(db, claim, gw, later + timedelta(hours=3)) is None
    assert len(gw.sent) == 1


def test_no_p0_once_the_driver_has_left(db):
    """A P0 is time-sensitive by §13.2's own definition; a finished visit is the Claim
    screen's business, not an interruption's."""
    account, stop, claim = _claim(db)
    _arrive(db, account)
    _depart(db, account, EXPIRY + timedelta(minutes=30))
    gw = notify.RecordingNotificationGateway()

    assert m3.dispatch_detention_start(db, claim, gw, EXPIRY + timedelta(hours=2)) is None
    assert gw.sent == []


def test_a_stale_boundary_is_not_news(db):
    """The defect the green suite could not see (§23 entry 107).

    The first real run of this job dispatched ELEVEN P0s at once, for claims whose free
    time had expired days earlier and whose drivers F3 still places on the dock. §13.2
    calls P0 time-sensitive; past the window there is no alert to send, not a late one.
    """
    account, stop, claim = _claim(db)
    _arrive(db, account)
    gw = notify.RecordingNotificationGateway()

    assert m3.dispatch_detention_start(db, claim, gw, EXPIRY + timedelta(days=3)) is None
    assert gw.sent == []
    # and it is NOT marked — it was never suppressed, it never had an alert to send
    assert claim.driver_start_alert_at is None


def test_the_freshness_window_forgives_worker_downtime(db):
    account, stop, claim = _claim(db)
    _arrive(db, account)
    gw = notify.RecordingNotificationGateway()

    sent = m3.dispatch_detention_start(db, claim, gw, EXPIRY + timedelta(minutes=29))

    assert sent is not None


def test_deploying_this_does_not_spray_the_backlog(db):
    """The consequence of the above, asserted as the property that matters: claims that
    predate the feature carry NULL alert timestamps and must still alert nobody."""
    account, stop, claim = _claim(db)
    _arrive(db, account)
    assert claim.driver_start_alert_at is None  # exactly what migration 0054 leaves
    gw = notify.RecordingNotificationGateway()

    summary = m3.dispatch_clock_alerts(db, gw, now=EXPIRY + timedelta(days=2))

    assert summary["started"] == 0
    assert gw.sent == []


def test_a_claim_with_no_arrival_never_fires(db):
    """§23 entry 106, caveat (b), made explicit rather than left to be discovered:
    `trigger_time` falls back to `now`, so the phase can never reach accruing."""
    account, stop, claim = _claim(db)  # no ping — F3 cannot place the visit
    gw = notify.RecordingNotificationGateway()

    assert m3.dispatch_detention_start(db, claim, gw, EXPIRY + timedelta(hours=6)) is None
    assert gw.sent == []


def test_a_claim_with_no_arrival_and_no_free_time_never_fires(db):
    """The live defect the previous test did NOT cover (§23 entry 107).

    With free time remaining, an unplaceable claim is harmless — the sliding trigger
    keeps it inside free time forever. With free time of 0 or None it reports
    "accruing, 0 seconds, $0.00" on EVERY tick, which reads to this job as a boundary
    crossed one second ago. Five live claims were in exactly that state and would each
    have pushed a P0 for a stop the driver never reached, for no money.
    """
    for label, free in (("zero", 0), ("unset", None)):
        account, stop, claim = _claim(db, email=f"nofree-{label}@example.com")
        claim.free_time_minutes = free
        gw = notify.RecordingNotificationGateway()

        state = m3.clock(db, claim, EXPIRY)
        assert state.phase == m3.DetentionPhase.accruing  # the trap: it looks fresh
        assert state.detention_seconds == 0
        assert m3.dispatch_detention_start(db, claim, gw, EXPIRY) is None
        assert gw.sent == []


def test_an_appointment_claim_is_anchored_without_any_arrival(db):
    """The other half: an appointment IS a real anchor, so it must still alert."""
    account, stop, claim = _claim(db)
    claim.trigger = m3.DetentionTrigger.appointment  # stop.appointment_start is T0
    gw = notify.RecordingNotificationGateway()

    sent = m3.dispatch_detention_start(db, claim, gw, EXPIRY + timedelta(minutes=1))

    assert sent is not None
    assert sent.tier == notify.NotificationTier.P0


# --- the P1 beside it, measured from the same boundary ---
def test_warning_is_silent_until_thirty_minutes_remain(db):
    account, stop, claim = _claim(db)
    _arrive(db, account)
    gw = notify.RecordingNotificationGateway()

    # 31 minutes left — one minute early is still early
    assert m3.dispatch_free_time_warning(db, claim, gw, EXPIRY - timedelta(minutes=31)) is None
    assert gw.sent == []


def test_warning_fires_at_thirty_minutes(db):
    account, stop, claim = _claim(db)
    _arrive(db, account)
    gw = notify.RecordingNotificationGateway()

    sent = m3.dispatch_free_time_warning(db, claim, gw, EXPIRY - timedelta(minutes=30))

    assert sent is not None
    assert sent.tier == notify.NotificationTier.P1
    assert sent.title == "30 min free time left"
    assert sent.body == "Detention starts after that at $75/h."


def test_warning_reports_the_minutes_actually_left(db):
    """A worker that was down for twenty minutes must not say "30 min left"."""
    account, stop, claim = _claim(db)
    _arrive(db, account)
    gw = notify.RecordingNotificationGateway()

    sent = m3.dispatch_free_time_warning(db, claim, gw, EXPIRY - timedelta(minutes=9))

    assert sent.title == "9 min free time left"


def test_warning_fires_once(db):
    account, stop, claim = _claim(db)
    _arrive(db, account)
    gw = notify.RecordingNotificationGateway()

    assert m3.dispatch_free_time_warning(db, claim, gw, EXPIRY - timedelta(minutes=20)) is not None
    assert m3.dispatch_free_time_warning(db, claim, gw, EXPIRY - timedelta(minutes=5)) is None
    assert len(gw.sent) == 1


# --- the tier laws, which are the reason P0 is P0 ---
def test_p0_outlives_a_spent_budget_that_suppresses_a_p1(db):
    """The paired assertion matters: without the P1 half this proves only that the
    budget was never reached."""
    account, stop, claim = _claim(db)
    _arrive(db, account)
    gw = notify.RecordingNotificationGateway()
    now = EXPIRY + timedelta(minutes=1)
    for i in range(notify.MAX_UNPROMPTED_P1_PER_DAY):
        notify.dispatch(
            db, account.id, notify.NotificationTier.P1, "document_expiry",
            f"filler {i}", "b", "/docs", gw, now=now,
        )

    p1 = m3.dispatch_free_time_warning(db, claim, gw, EXPIRY - timedelta(minutes=10))
    p0 = m3.dispatch_detention_start(db, claim, gw, now)

    assert p1 is None or p1.status == notify.NotificationStatus.suppressed
    assert p0.status == notify.NotificationStatus.sent


def test_p0_outlives_quiet_hours_that_suppress_a_p1(db):
    account, stop, claim = _claim(db)
    _arrive(db, account, at=datetime(2026, 7, 20, 1, 0, tzinfo=UTC))
    gw = notify.RecordingNotificationGateway()
    # 03:00 — inside F8's default 22:00–06:00 quiet window
    night = datetime(2026, 7, 20, 3, 5, tzinfo=UTC)
    control = notify.dispatch(
        db, account.id, notify.NotificationTier.P1, "document_expiry",
        "control", "b", "/docs", gw, now=night,
    )
    assert control.status == notify.NotificationStatus.suppressed  # the clock is right

    p0 = m3.dispatch_detention_start(db, claim, gw, night)

    assert p0.status == notify.NotificationStatus.sent


def test_detention_start_is_not_an_opt_in_class(db):
    """Owner decision (§23 entry 106): a class is an opt-in bundle, and a driver who
    never found the switch would be silently un-told about their own money."""
    assert notify.get_class(m3.DETENTION_START_CATEGORY) is None
    assert notify.get_class(m3.FREE_TIME_WARNING_CATEGORY) is None


# --- §13.5, and the wording a company driver gets ---
def test_deep_link_is_the_claim_screen_never_a_tab_root(db):
    account, stop, claim = _claim(db)
    _arrive(db, account)
    gw = notify.RecordingNotificationGateway()

    sent = m3.dispatch_detention_start(db, claim, gw, EXPIRY + timedelta(minutes=1))

    assert sent.deep_link == f"/claim/{stop.id}"
    assert sent.deep_link.count("/") == 2  # not "/money", not "/load"


def test_a_company_driver_is_not_promised_a_notice_they_cannot_send(db):
    account, stop, claim = _claim(db, authority=identity.AuthorityType.company)
    _arrive(db, account)
    gw = notify.RecordingNotificationGateway()

    sent = m3.dispatch_detention_start(db, claim, gw, EXPIRY + timedelta(minutes=1))

    assert claim.mode == m3.ClaimMode.evidence_only
    assert sent.body == "Free time is used up at this stop. Your evidence pack is recording."


def test_a_claim_with_no_rate_leads_with_no_figure(db):
    account, stop, claim = _claim(db, rate=None)
    _arrive(db, account)
    gw = notify.RecordingNotificationGateway()

    sent = m3.dispatch_detention_start(db, claim, gw, EXPIRY + timedelta(minutes=1))

    assert sent.title == "Detention started"


# --- the scan, which is the thing that was actually missing ---
def test_the_scan_finds_the_claim_and_reports_what_it_did(db):
    account, stop, claim = _claim(db)
    _arrive(db, account)
    gw = notify.RecordingNotificationGateway()

    summary = m3.dispatch_clock_alerts(db, gw, now=EXPIRY + timedelta(minutes=1))

    assert summary["scanned"] == 1
    assert summary["started"] == 1
    assert summary["warned"] == 0
    assert len(gw.sent) == 1


def test_the_scan_warns_when_the_warning_is_what_is_due(db):
    account, stop, claim = _claim(db)
    _arrive(db, account)
    gw = notify.RecordingNotificationGateway()

    summary = m3.dispatch_clock_alerts(db, gw, now=EXPIRY - timedelta(minutes=15))

    assert summary["warned"] == 1
    assert summary["started"] == 0


def test_a_fully_alerted_claim_leaves_the_scan_set(db):
    """The set bounds itself; nothing is capped, so this is what keeps it small."""
    account, stop, claim = _claim(db)
    _arrive(db, account)
    gw = notify.RecordingNotificationGateway()

    m3.dispatch_clock_alerts(db, gw, now=EXPIRY - timedelta(minutes=15))  # warned
    m3.dispatch_clock_alerts(db, gw, now=EXPIRY + timedelta(minutes=1))  # started
    remaining = m3.claims_awaiting_alerts(db)

    assert remaining == []
    assert m3.dispatch_clock_alerts(db, gw, now=EXPIRY + timedelta(hours=1))["scanned"] == 0


def test_the_alert_reaches_the_driver_inbox(db):
    """The whole point of entry 102's inbox: a decision nobody can read is not a
    notification."""
    account, stop, claim = _claim(db)
    _arrive(db, account)
    gw = notify.RecordingNotificationGateway()

    m3.dispatch_clock_alerts(db, gw, now=EXPIRY + timedelta(minutes=1))
    rows = notify.inbox(db, account.id)

    assert [r.title for r in rows] == ["Detention started · $75/h"]


def test_the_driver_alert_is_recorded_apart_from_the_broker_notice(db):
    """One column would have made "the driver knows" mean "the broker was told"."""
    account, stop, claim = _claim(db)
    _arrive(db, account)
    gw = notify.RecordingNotificationGateway()

    m3.dispatch_detention_start(db, claim, gw, EXPIRY + timedelta(minutes=1))

    assert claim.driver_start_alert_at is not None
    assert claim.start_notice_sent_at is None  # the counterparty has not been told


# --- N-02: the P0 in the driver's own language ---
def test_the_detention_p0_reaches_a_spanish_driver_in_spanish(db):
    # the product's most important driver-facing alert was an English literal
    from app.foundation.f15_localization import public as localization
    from app.modules.m03_detention.domain import messages as m03_messages

    account, stop, claim = _claim(db)
    m3.register_module(db)  # seeds the catalogue, as boot does
    localization.set_user_locale(db, account, "es")
    _arrive(db, account)
    gw = notify.RecordingNotificationGateway()

    sent = m3.dispatch_detention_start(db, claim, gw, EXPIRY + timedelta(minutes=1))

    assert sent.tier == notify.NotificationTier.P0
    assert sent.title == "Detention iniciada · $75/h"  # the RATE stays USD (F15)
    assert sent.body == m03_messages.ALERT_MESSAGES["detention_started.body"]["es"].format(
        action=m03_messages.ALERT_MESSAGES["detention_started.action_invoice"]["es"]
    )


def test_the_english_p0_is_byte_for_byte_unchanged(db):
    # localizing must not quietly reword the English a driver already receives
    account, stop, claim = _claim(db)
    m3.register_module(db)
    _arrive(db, account)
    gw = notify.RecordingNotificationGateway()

    sent = m3.dispatch_detention_start(db, claim, gw, EXPIRY + timedelta(minutes=1))

    assert sent.title == "Detention started · $75/h"
    assert sent.body == "Free time is used up at this stop. Notice ready to send."


def test_a_company_driver_is_not_promised_a_notice_in_any_language(db):
    # §12.6/M3-FR9: a company driver cannot bill anyone, so the invoice action would
    # name something their mode does not have. The branch must survive translation.
    from app.foundation.f15_localization import public as localization
    from app.modules.m03_detention.domain import messages as m03_messages

    account, stop, claim = _claim(db, authority=identity.AuthorityType.company)
    m3.register_module(db)
    localization.set_user_locale(db, account, "ru")
    _arrive(db, account)
    gw = notify.RecordingNotificationGateway()

    sent = m3.dispatch_detention_start(db, claim, gw, EXPIRY + timedelta(minutes=1))

    record = m03_messages.ALERT_MESSAGES["detention_started.action_record"]["ru"]
    invoice = m03_messages.ALERT_MESSAGES["detention_started.action_invoice"]["ru"]
    assert record in sent.body and invoice not in sent.body

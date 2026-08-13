"""AI-CONTEXT: the product's first question to a driver (§23 entry 112).

M1-FR7's chip has always been driver-INITIATED and §23 entry 104 made status arrive
live; neither is a prompt. Nothing here had ever ASKED anyone anything.

Almost every test below is a REFUSAL, and that is the shape of the feature: the danger
is not failing to ask, it is asking too often and losing the notification permission
that §13.1 calls a platform-critical asset — one-shot, and shared with the detention P0.
"""

from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f08_notifications import public as notify
from app.foundation.f10_crowd import public as crowd
from app.modules.m01_map import public as m1

DALLAS = (32.7767, -96.7970)
NOW = datetime(2026, 7, 20, 14, 0, tzinfo=UTC)  # mid-afternoon: outside quiet hours


def _driver(db, email="drv@example.com", opted_in=True):
    account = identity.register_account(db, email, "pw-123456")
    if opted_in:
        notify.set_class_opt_in(db, account.id, notify.LOT_STATUS_PROMPT_CLASS, True)
    return account


def _lot(db, kind=None, name="Riverside Truck Stop"):
    kind = kind or facility.FacilityType.truck_stop
    return facility.create_facility(db, kind, name, *DALLAS)


def test_a_driver_who_stopped_is_asked(db):
    account = _driver(db)
    lot = _lot(db)
    gw = notify.RecordingNotificationGateway()

    sent = m1.prompt_for_lot_status(db, account.id, lot.id, gw, NOW)

    assert sent is not None
    assert sent.status == notify.NotificationStatus.queued
    assert sent.tier == notify.NotificationTier.P1
    assert sent.title == "How's the lot at Riverside Truck Stop?"


def test_the_answer_is_three_tray_buttons_the_map_already_speaks(db):
    """No new vocabulary anywhere: these are PARKING_STATUS's own three values."""
    account = _driver(db)
    lot = _lot(db)
    gw = notify.RecordingNotificationGateway()

    m1.prompt_for_lot_status(db, account.id, lot.id, gw, NOW)

    # the push_delivery sweep is what hands a queued notification to the
    # push service; the request only decides (§13.1 laws included)
    notify.deliver_queued_notifications(db, lambda _a: gw)
    assert [a["action"] for a in gw.sent[0].actions] == ["lot:empty", "lot:some", "lot:full"]
    assert [a["title"] for a in gw.sent[0].actions] == ["Empty", "Some", "Full"]


def test_the_deep_link_is_the_facility_not_a_tab_root(db):
    account = _driver(db)
    lot = _lot(db)
    gw = notify.RecordingNotificationGateway()

    sent = m1.prompt_for_lot_status(db, account.id, lot.id, gw, NOW)

    assert sent.deep_link == f"/facility/{lot.id}"


# --- the refusals, which are the design ---
def test_a_working_driver_at_a_dock_is_not_surveyed(db):
    """"How full is the lot?" at a grocery warehouse is a question about nothing, and a
    driver dwelling at a shipper_receiver is WORKING — that dwell is M3's business."""
    account = _driver(db)
    dock = _lot(db, kind=facility.FacilityType.shipper_receiver, name="Metro Market DC")
    gw = notify.RecordingNotificationGateway()

    assert m1.prompt_for_lot_status(db, account.id, dock.id, gw, NOW) is None
    assert gw.sent == []


def test_every_promptable_kind_is_a_place_you_park(db):
    assert m1.PROMPTABLE_KINDS == {"truck_stop", "rest_area", "parking_property"}


def test_a_driver_who_already_reported_is_not_asked(db):
    """The specific insult the class cap does not prevent: being asked for something you
    volunteered ten minutes ago."""
    account = _driver(db)
    lot = _lot(db)
    crowd.submit(
        db, account.id, lot.id, crowd.SignalType.parking_fullness,
        {"status": "some"}, submitted_at=NOW - timedelta(minutes=10),
    )
    gw = notify.RecordingNotificationGateway()

    assert m1.prompt_for_lot_status(db, account.id, lot.id, gw, NOW) is None


def test_another_driver_having_reported_does_not_silence_the_ask(db):
    """Two independent reports are what consensus is built from, so the check is scoped
    to the ACCOUNT rather than the facility."""
    mine = _driver(db, "mine@example.com")
    theirs = _driver(db, "theirs@example.com")
    lot = _lot(db)
    crowd.submit(
        db, theirs.id, lot.id, crowd.SignalType.parking_fullness,
        {"status": "full"}, submitted_at=NOW - timedelta(minutes=5),
    )
    gw = notify.RecordingNotificationGateway()

    assert m1.prompt_for_lot_status(db, mine.id, lot.id, gw, NOW) is not None


def test_a_driver_who_never_opted_in_is_never_asked(db):
    """§21.8: this asks the driver for LABOUR, so it is off until they say otherwise."""
    account = _driver(db, "quiet@example.com", opted_in=False)
    lot = _lot(db)
    gw = notify.RecordingNotificationGateway()

    sent = m1.prompt_for_lot_status(db, account.id, lot.id, gw, NOW)

    assert sent.status == notify.NotificationStatus.suppressed
    assert sent.suppress_reason == notify.SuppressReason.not_opted_in
    assert gw.sent == []


def test_the_class_is_off_by_default(db):
    assert notify.get_class(notify.LOT_STATUS_PROMPT_CLASS).opt_in_default is False


def test_a_driver_who_stops_three_times_is_asked_once(db):
    account = _driver(db)
    gw = notify.RecordingNotificationGateway()

    for i in range(3):
        lot = _lot(db, name=f"Stop {i}")
        m1.prompt_for_lot_status(db, account.id, lot.id, gw, NOW + timedelta(hours=i))

    # the push_delivery sweep is what hands a queued notification to the
    # push service; the request only decides (§13.1 laws included)
    notify.deliver_queued_notifications(db, lambda _a: gw)
    assert len(gw.sent) == 1


def test_it_loses_to_real_news_rather_than_crowding_it_out(db):
    """NOT budget-exempt, deliberately: `protection_gap` earned its exemption by being a
    deadline, and a survey is the opposite."""
    account = _driver(db)
    lot = _lot(db)
    gw = notify.RecordingNotificationGateway()
    for i in range(notify.MAX_UNPROMPTED_P1_PER_DAY):
        notify.dispatch(
            db, account.id, notify.NotificationTier.P1, "document_expiry",
            f"filler {i}", "b", "/docs", gw, now=NOW,
        )

    sent = m1.prompt_for_lot_status(db, account.id, lot.id, gw, NOW)

    assert sent.status == notify.NotificationStatus.suppressed
    assert sent.suppress_reason == notify.SuppressReason.budget


def test_a_sleeping_driver_is_not_woken_to_be_surveyed(db):
    """§13.3 — and this is the case quiet hours were written for: a driver dwelling at a
    truck stop at 23:00 is asleep in the bunk, which is exactly why they are dwelling."""
    account = _driver(db)
    lot = _lot(db)
    gw = notify.RecordingNotificationGateway()

    sent = m1.prompt_for_lot_status(
        db, account.id, lot.id, gw, datetime(2026, 7, 20, 23, 30, tzinfo=UTC)
    )

    assert sent.status == notify.NotificationStatus.suppressed
    assert sent.suppress_reason == notify.SuppressReason.quiet_hours


def test_an_unknown_facility_is_not_asked_about(db):
    import uuid

    account = _driver(db)
    gw = notify.RecordingNotificationGateway()

    assert m1.prompt_for_lot_status(db, account.id, uuid.uuid4(), gw, NOW) is None


# --- the TRIGGER, which is what the rules above were useless without (§23 entry 112) ---
#
# The first build of this feature hung the prompt off DWELL_TICK and shipped thirteen
# green tests that all called `prompt_for_lot_status` directly. The geofence only emits
# events for ARMED facilities and nothing arms a truck stop, so it could never have
# fired. These tests drive PINGS, which is the only way to catch that.
from app.foundation.f03_location import public as location  # noqa: E402


def _ping(db, account, at, lat=DALLAS[0], lon=DALLAS[1]):
    return location.evaluate_ping(db, account.id, lat, lon, occurred_at=at)


def test_a_driver_parked_at_an_unarmed_truck_stop_is_asked(db):
    """The case the geofence cannot see: no load, no stop, no arming — just a driver
    who pulled in for the night."""
    account = _driver(db)
    _lot(db)
    gw = notify.RecordingNotificationGateway()
    _ping(db, account, NOW - timedelta(minutes=40))
    _ping(db, account, NOW - timedelta(minutes=20))
    _ping(db, account, NOW)

    sent = m1.lot_status_prompt_due(db, account.id, *DALLAS, gw, NOW)

    assert sent is not None
    # the push_delivery sweep is what hands a queued notification to the
    # push service; the request only decides (§13.1 laws included)
    notify.deliver_queued_notifications(db, lambda _a: gw)
    assert len(gw.sent) == 1


def test_a_driver_still_rolling_is_not_asked(db):
    """One ping is not a stay, and a truck that moved is not parked."""
    account = _driver(db)
    _lot(db)
    gw = notify.RecordingNotificationGateway()
    _ping(db, account, NOW - timedelta(minutes=40), lat=33.5, lon=-97.5)  # far away
    _ping(db, account, NOW)

    assert m1.lot_status_prompt_due(db, account.id, *DALLAS, gw, NOW) is None


def test_five_minutes_parked_is_not_yet_a_stay(db):
    account = _driver(db)
    _lot(db)
    gw = notify.RecordingNotificationGateway()
    _ping(db, account, NOW - timedelta(minutes=5))
    _ping(db, account, NOW)

    assert m1.lot_status_prompt_due(db, account.id, *DALLAS, gw, NOW) is None


def test_a_driver_parked_nowhere_near_a_lot_is_not_asked(db):
    """Stationary at a rest stop that is not in the registry, or on a shoulder."""
    account = _driver(db)
    gw = notify.RecordingNotificationGateway()
    _ping(db, account, NOW - timedelta(minutes=40))
    _ping(db, account, NOW)

    assert m1.lot_status_prompt_due(db, account.id, *DALLAS, gw, NOW) is None


def test_the_ping_path_writes_nothing_to_the_location_tables(db):
    """The whole reason shape (c) was chosen over auto-arming: this must not be able to
    touch the machinery M3's money reads, even if it is completely wrong."""
    account = _driver(db)
    lot = _lot(db)
    gw = notify.RecordingNotificationGateway()
    _ping(db, account, NOW - timedelta(minutes=40))
    _ping(db, account, NOW)
    before = len(location.list_events(db, account.id, lot.id))

    m1.lot_status_prompt_due(db, account.id, *DALLAS, gw, NOW)

    assert location.list_events(db, account.id, lot.id) == []
    assert before == 0
    assert location.is_present(db, account.id, lot.id) is False


def test_it_asks_once_and_then_stops_asking_on_every_ping(db):
    """A driver dwelling for eight hours pings ~96 times. Without an ATTEMPT guard each
    one writes a suppressed row, and §23 entry 102's inbox renders suppressed rows — so
    the driver would open it to ninety identical held prompts."""
    account = _driver(db)
    _lot(db)
    gw = notify.RecordingNotificationGateway()
    _ping(db, account, NOW - timedelta(minutes=40))
    _ping(db, account, NOW)

    for i in range(6):
        m1.lot_status_prompt_due(db, account.id, *DALLAS, gw, NOW + timedelta(minutes=5 * i))

    rows = db.query(notify.Notification).filter_by(account_id=account.id).all()
    assert len(rows) == 1
    # the push_delivery sweep is what hands a queued notification to the
    # push service; the request only decides (§13.1 laws included)
    notify.deliver_queued_notifications(db, lambda _a: gw)
    assert len(gw.sent) == 1


def test_a_stay_ends_when_the_driver_leaves(db):
    """The first ping outside the radius ends the stay — a driver who left and came back
    gets the second visit, not the union of both (§23 entry 73's scoping mistake)."""
    account = _driver(db)
    _ping(db, account, NOW - timedelta(minutes=60))
    _ping(db, account, NOW - timedelta(minutes=30), lat=33.5, lon=-97.5)  # left
    _ping(db, account, NOW - timedelta(minutes=4))  # came back
    _ping(db, account, NOW)

    since = location.stationary_since(db, account.id, NOW)

    assert since == NOW - timedelta(minutes=4)  # this visit, not the earlier one

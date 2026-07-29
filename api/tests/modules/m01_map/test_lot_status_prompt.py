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
    assert sent.status == notify.NotificationStatus.sent
    assert sent.tier == notify.NotificationTier.P1
    assert sent.title == "How's the lot at Riverside Truck Stop?"


def test_the_answer_is_three_tray_buttons_the_map_already_speaks(db):
    """No new vocabulary anywhere: these are PARKING_STATUS's own three values."""
    account = _driver(db)
    lot = _lot(db)
    gw = notify.RecordingNotificationGateway()

    m1.prompt_for_lot_status(db, account.id, lot.id, gw, NOW)

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

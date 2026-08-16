"""AI-CONTEXT: J1-D1's arrival reminder — the clock, the armed stop, and the silence.

The class spec is entry 169 and every field of it is a claim. These tests hold the ones
that would be invisible if they were wrong:

  · it fires from THE CLOCK, not from location. The background sensor is the one mechanism
    v2.0 DoD #8 records as UNPROVEN, and §15.5's rule is build for auto, degrade to
    one-tap, never to nothing — so the fallback path is the one that has to work.
  · PRESENCE SUPPRESSES IT. A driver already at the dock needs no reminder to arrive. The
    sensor, where it works, makes the nudge unnecessary rather than redundant.
  · it fires only for the driver's OWN ARMED stop with an appointment THEY recorded. That
    is what earns `opt_in_default=True` where `lot_status_prompt` gets False: this asks
    nothing of the driver that they did not already ask for.

The failure this class is most likely to have is SILENCE, which from outside looks exactly
like the flag being off — so the flag is asserted in both directions rather than only in
the one that produces a visible push.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f05_load import public as loads
from app.foundation.f08_notifications import public as notify
from app.foundation.f13_flags import public as flags
from app.modules.m05_protection import public as m5

DALLAS = (32.7767, -96.7970)
NOW = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)


@pytest.fixture
def armed(db):
    def _make(email="nudge@example.com", minutes_out=10, arrive=False):
        account = identity.register_account(db, email, "pw-123456")
        fac = facility.create_facility(
            db, facility.FacilityType.shipper_receiver, "Harvest Foods DC", *DALLAS
        )
        load = loads.create_load(db, account.id, counterparty_id=None, reference_number="L-1")
        stop = loads.add_stop(db, load, fac.id, sequence=0, stop_type=loads.StopType.delivery)
        if minutes_out is not None:
            loads.set_stop_appointment(db, stop, NOW + timedelta(minutes=minutes_out))
        loads.arm_stop(db, stop)
        if arrive:
            location.evaluate_ping(db, account.id, *DALLAS, occurred_at=NOW)
        db.flush()
        return account, stop

    return _make


def _on(db):
    m5.register_module(db)
    flags.enable(db, m5.ARRIVAL_NUDGE_FLAG)
    db.flush()


def _send(db, now=NOW):
    return m5.dispatch_arrival_reminders(db, notify.RecordingNotificationGateway(), now=now)


# --- the trigger ---


def test_it_fires_for_an_armed_stop_inside_the_lead_window(db, armed):
    _on(db)
    armed(minutes_out=10)

    assert len(_send(db)) == 1


def test_it_does_not_fire_for_an_appointment_still_far_off(db, armed):
    """Lead is 15 minutes by default. An appointment four hours out is not news yet, and
    a reminder that arrives too early is a reminder the driver learns to ignore."""
    _on(db)
    armed(minutes_out=240)

    assert _send(db) == []


def test_it_does_not_fire_for_a_stop_with_no_appointment(db, armed):
    """The class fires for an appointment the DRIVER recorded. With none there is nothing
    to be near, and firing anyway would be the product inventing a deadline."""
    _on(db)
    armed(minutes_out=None)

    assert _send(db) == []


def test_it_needs_no_location_at_all_to_fire(db, armed):
    """THE point of the design. No ping is ever recorded in this test — the trigger is the
    clock and the armed stop, so it works on a handset that never granted background
    location (v2.0 DoD #8, §15.5)."""
    _on(db)
    account, _ = armed(minutes_out=5)
    assert location.is_present_anywhere(db, account.id) is False

    assert len(_send(db)) == 1


# --- the silence ---


def test_a_driver_already_at_the_dock_is_not_reminded_to_arrive(db, armed):
    """Presence suppression. The sensor, where it works, makes the nudge UNNECESSARY —
    they are not two competing answers, one removes the need for the other."""
    _on(db)
    armed(minutes_out=10, arrive=True)

    assert _send(db) == []


def test_a_departed_stop_produces_nothing(db, armed):
    """`depart_stop` moves the status off `armed`, so a stop the driver already finished
    cannot produce a reminder about reaching it."""
    _on(db)
    _, stop = armed(minutes_out=10)
    loads.depart_stop(db, stop, occurred_at=NOW)
    db.flush()

    assert _send(db) == []


def test_an_unarmed_stop_produces_nothing(db):
    """Arming is the driver's statement that this is the stop they are running. A pending
    stop on a multi-stop load has not been chosen and its driver has asked for nothing."""
    _on(db)
    account = identity.register_account(db, "unarmed@example.com", "pw-123456")
    fac = facility.create_facility(db, facility.FacilityType.shipper_receiver, "D", *DALLAS)
    load = loads.create_load(db, account.id, counterparty_id=None, reference_number="L-9")
    stop = loads.add_stop(db, load, fac.id, sequence=0, stop_type=loads.StopType.delivery)
    loads.set_stop_appointment(db, stop, NOW + timedelta(minutes=10))
    db.flush()  # never armed

    assert _send(db) == []


# --- the flag, both directions ---


def test_nothing_fires_while_the_flag_is_off(db, armed):
    m5.register_module(db)
    db.flush()
    armed(minutes_out=10)

    assert _send(db) == []


def test_and_the_same_stop_fires_once_it_is_on(db, armed):
    """The other direction, which is the one that matters: silence is this class's most
    likely failure and from outside it looks exactly like the flag being off."""
    m5.register_module(db)
    db.flush()
    armed(minutes_out=10)
    assert _send(db) == []

    flags.enable(db, m5.ARRIVAL_NUDGE_FLAG)
    db.flush()

    assert len(_send(db)) == 1


# --- the spec's own fields ---


def test_the_class_is_registered_exactly_as_J1_D1_specifies(db):
    """Entry 169 is owner-signed and each field is a claim; a drift here changes an
    interruption law without anyone deciding to."""
    spec = notify.NOTIFICATION_CLASSES[notify.ARRIVAL_REMINDER_CLASS]

    assert spec.tier is notify.NotificationTier.P1
    assert spec.max_per_day == 2
    assert spec.opt_in_default is True
    assert spec.route_relevant_only is False
    assert spec.budget_exempt is False


def test_it_is_not_budget_exempt_unlike_the_deadline_class(db):
    """`protection_gap` earned its exemption by being a DEADLINE — that trailer cannot be
    photographed at that dock ever again. A reminder about something still ahead of you
    must LOSE to real news rather than crowd it out."""
    assert notify.ARRIVAL_REMINDER_CLASS not in notify.BUDGET_EXEMPT_CLASSES
    assert notify.PROTECTION_GAP_CLASS in notify.BUDGET_EXEMPT_CLASSES


def test_the_lead_is_tunable_without_a_deploy(db, armed):
    """An F13 config key, so the number can be changed on a live box. Widened, a stop
    four hours out becomes due."""
    _on(db)
    armed(minutes_out=240)
    assert _send(db) == []

    flags.set_config(db, m5.CONFIG_ARRIVAL_LEAD_MINUTES, 300)
    db.flush()

    assert len(_send(db)) == 1


def test_it_deep_links_to_the_load_not_a_tab_root(db, armed):
    """§13.5. A notification that lands on a tab root makes the driver hunt for the thing
    it just told them about."""
    _on(db)
    armed(minutes_out=10)

    assert _send(db)[0].deep_link == "/load"

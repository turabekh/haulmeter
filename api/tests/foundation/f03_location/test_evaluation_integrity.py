"""F3-3 and F3-4 — time only moves forward, and the machine tolerates a real phone.

The offline outbox exists precisely to deliver pings LATE, and the state machine applied
every ping to CURRENT state at the ping's own timestamp. That is the whole of F3-3: a late
inside-ping arriving after its visit's EXIT re-opened a presence that never closes, and a
late outside-ping after an ENTER closed the visit at a moment before it began. Both put a
wrong arrival or departure under a detention claim.
"""

from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f03_location.domain.models import EvaluationCursor, GeofencePresence
from app.foundation.f13_flags import public as flags

DALLAS = (32.7767, -96.7970)
FAR = (32.9000, -96.8000)
T0 = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
LATER = T0 + timedelta(days=400)  # far past any real "now" the suite runs at


def _armed(db, email="oo@example.com"):
    account = identity.register_account(db, email, "pw-123456")
    dock = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Dock", *DALLAS)
    location.arm_geofence(db, account.id, dock.id)
    return account, dock


def _presence(db, account, dock):
    return (
        db.query(GeofencePresence)
        .filter_by(account_id=account.id, facility_id=dock.id)
        .order_by(GeofencePresence.entered_at)
        .all()
    )


def _cursor(db, account):
    return db.get(EvaluationCursor, account.id)


# --- ordering ---
def test_a_ping_at_or_before_the_cursor_is_recorded_but_not_evaluated(db):
    account, dock = _armed(db)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0, now=T0)

    stale = location.evaluate_ping(
        db, account.id, *FAR, occurred_at=T0 - timedelta(minutes=5), now=T0
    )

    assert stale.evaluated is False
    assert stale.skipped_reason == "stale_order"
    assert stale.events == []
    # the visit is untouched — an outside ping from before the arrival must not close it
    assert _presence(db, account, dock)[0].active is True


def test_the_exact_F3_3_sequence_cannot_reopen_a_closed_visit(db):
    """Arrive, leave, then a late INSIDE ping from during the visit turns up.

    Before the cursor this re-opened a presence that nothing would ever close — and
    `visit_window` hands an open session to the next load as its arrival.
    """
    account, dock = _armed(db)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0, now=T0)
    exit_at = T0 + timedelta(hours=4)
    location.evaluate_ping(db, account.id, *FAR, occurred_at=exit_at, now=exit_at)
    assert _presence(db, account, dock)[0].active is False

    late = location.evaluate_ping(
        db, account.id, *DALLAS, occurred_at=T0 + timedelta(hours=1), now=exit_at
    )

    assert late.skipped_reason == "stale_order"
    sessions = _presence(db, account, dock)
    assert len(sessions) == 1
    assert sessions[0].active is False
    assert sessions[0].exited_at is not None


def test_an_exit_can_never_precede_its_own_entry(db):
    """The other half of F3-3: a late OUTSIDE ping arriving after the ENTER."""
    account, dock = _armed(db)
    enter_at = T0 + timedelta(hours=2)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=enter_at, now=enter_at)

    location.evaluate_ping(db, account.id, *FAR, occurred_at=T0, now=enter_at)

    session = _presence(db, account, dock)[0]
    assert session.exited_at is None or session.exited_at >= session.entered_at


def test_the_cursor_advances_only_on_evaluated_pings(db):
    account, _ = _armed(db)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0, now=T0)
    assert _cursor(db, account).last_evaluated_at == T0

    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0 - timedelta(hours=1), now=T0)

    assert _cursor(db, account).last_evaluated_at == T0


# --- the future ---
def test_a_ping_from_the_future_is_recorded_but_not_evaluated(db):
    account, dock = _armed(db)

    result = location.evaluate_ping(
        db, account.id, *DALLAS, occurred_at=T0 + timedelta(hours=1), now=T0
    )

    assert result.evaluated is False
    assert result.skipped_reason == "future"
    assert _presence(db, account, dock) == []


def test_a_future_ping_does_not_poison_the_pings_after_it(db):
    """The reason the future guard does not advance the cursor.

    A handset with a broken clock would otherwise set the mark years ahead, and every real
    ping that followed would be refused as `stale_order` — one bad device silently ending
    a driver's tracking.
    """
    account, dock = _armed(db)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=LATER, now=T0)
    assert _cursor(db, account) is None or _cursor(db, account).last_evaluated_at < T0

    good = location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0, now=T0)

    assert good.evaluated is True
    assert len(_presence(db, account, dock)) == 1


def test_ordinary_clock_skew_is_forgiven(db):
    """FUTURE_TOLERANCE is the width of handset drift, not a policy about money."""
    account, dock = _armed(db)

    result = location.evaluate_ping(
        db, account.id, *DALLAS, occurred_at=T0 + timedelta(minutes=2), now=T0
    )

    assert result.evaluated is True
    assert len(_presence(db, account, dock)) == 1


# --- the trail is kept either way ---
def test_a_skipped_ping_is_still_recorded(db):
    """Refusing to reason about a ping is not a reason to forget where the driver was."""
    from app.foundation.f03_location.domain.models import LocationPing

    account, _ = _armed(db)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0, now=T0)

    location.evaluate_ping(db, account.id, *FAR, occurred_at=T0 - timedelta(hours=1), now=T0)
    location.evaluate_ping(db, account.id, *FAR, occurred_at=LATER, now=T0)

    assert db.query(LocationPing).filter_by(account_id=account.id).count() == 3


# --- F3-2's recovery path ---
def test_a_second_open_session_is_impossible_even_below_the_service_layer(db):
    """The index is the backstop; `_open_presence` turns it into a recovery, not a 500."""
    from app.foundation.f03_location.domain.service import _open_presence

    account, dock = _armed(db)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0, now=T0)

    lost = _open_presence(db, account.id, dock.id, T0 + timedelta(minutes=1))

    assert lost is None  # the race loser yields to the session that exists
    assert len(_presence(db, account, dock)) == 1


# --- F3-4: the knobs, and the fact that they are OFF ---
def test_the_defaults_reproduce_todays_behaviour_exactly(db):
    """The identity that makes this session safe to ship.

    Both knobs ship inert — one confirming ping, no accuracy gate — so the state machine
    behaves precisely as it did. The whole pre-existing `evaluate_ping` suite passing
    beside this is the rest of the proof.
    """
    from app.foundation.f03_location.domain import service

    assert service.DEFAULT_EXIT_CONFIRM_PINGS == 1
    assert service.DEFAULT_ACCURACY_GATE_M == 0
    assert service._exit_confirm_pings(db) == 1
    assert service._accuracy_gate_m(db) == 0


def test_one_outside_ping_still_exits_by_default(db):
    account, dock = _armed(db)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0, now=T0)

    out = T0 + timedelta(hours=1)
    events = location.evaluate_ping(db, account.id, *FAR, occurred_at=out, now=out)

    assert [e.event_type for e in events] == [location.GeofenceEventType.EXIT]
    assert _presence(db, account, dock)[0].active is False


def test_with_the_knob_at_two_one_outside_ping_does_not_exit(db):
    account, dock = _armed(db)
    flags.set_config(db, location.CONFIG_EXIT_CONFIRM_PINGS, 2)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0, now=T0)
    entered = _presence(db, account, dock)[0].last_tick_at

    first_out = T0 + timedelta(hours=1)
    events = location.evaluate_ping(db, account.id, *FAR, occurred_at=first_out, now=first_out)

    assert events.events == []
    session = _presence(db, account, dock)[0]
    assert session.active is True
    assert session.outside_streak == 1
    # a bad fix must not masquerade as a dwell tick
    assert session.last_tick_at == entered


def test_with_the_knob_at_two_the_second_outside_ping_exits(db):
    account, dock = _armed(db)
    flags.set_config(db, location.CONFIG_EXIT_CONFIRM_PINGS, 2)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0, now=T0)
    one = T0 + timedelta(hours=1)
    location.evaluate_ping(db, account.id, *FAR, occurred_at=one, now=one)

    two = T0 + timedelta(hours=2)
    events = location.evaluate_ping(db, account.id, *FAR, occurred_at=two, now=two)

    assert [e.event_type for e in events] == [location.GeofenceEventType.EXIT]
    assert _presence(db, account, dock)[0].exited_at == two


def test_a_ping_back_inside_resets_the_streak(db):
    """The point of the debounce: one bad fix in the middle of a visit costs nothing."""
    account, dock = _armed(db)
    flags.set_config(db, location.CONFIG_EXIT_CONFIRM_PINGS, 3)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0, now=T0)
    one = T0 + timedelta(hours=1)
    location.evaluate_ping(db, account.id, *FAR, occurred_at=one, now=one)
    assert _presence(db, account, dock)[0].outside_streak == 1

    back = T0 + timedelta(hours=2)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=back, now=back)

    session = _presence(db, account, dock)[0]
    assert session.outside_streak == 0
    assert session.active is True


def test_a_zero_or_negative_confirm_count_is_read_as_one(db):
    """0 must not mean "a visit that never ends" — the operator-typo safety."""
    from app.foundation.f03_location.domain import service

    flags.set_config(db, location.CONFIG_EXIT_CONFIRM_PINGS, 0)

    assert service._exit_confirm_pings(db) == 1


def test_with_the_gate_on_a_vague_ping_is_not_evaluated(db):
    account, dock = _armed(db)
    flags.set_config(db, location.CONFIG_ACCURACY_GATE_M, 50)

    result = location.evaluate_ping(
        db, account.id, *DALLAS, occurred_at=T0, now=T0, accuracy_m=400.0
    )

    assert result.evaluated is False
    assert result.skipped_reason == "low_accuracy"
    assert _presence(db, account, dock) == []
    assert _cursor(db, account) is None  # the cursor did not move for a ping we ignored


def test_with_the_gate_off_the_same_vague_ping_is_evaluated(db):
    account, dock = _armed(db)

    result = location.evaluate_ping(
        db, account.id, *DALLAS, occurred_at=T0, now=T0, accuracy_m=400.0
    )

    assert result.evaluated is True
    assert len(_presence(db, account, dock)) == 1


def test_a_ping_with_no_accuracy_is_never_gated(db):
    """A phone that does not report accuracy is not a phone reporting bad accuracy."""
    account, dock = _armed(db)
    flags.set_config(db, location.CONFIG_ACCURACY_GATE_M, 50)

    result = location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0, now=T0)

    assert result.evaluated is True
    assert len(_presence(db, account, dock)) == 1

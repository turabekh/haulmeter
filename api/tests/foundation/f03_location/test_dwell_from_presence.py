"""AI-CONTEXT: a visit is a ROW, not a pair of edges (§23 entry 73, applied to dwell).

`disarm_geofence` closes a visit — `active=False`, `exited_at=when` — and emits no EXIT
EVENT. `dwell_samples` used to reconstruct visits by replaying ENTER/EXIT events, so
every driver who departed through the app's own flow ("Leave this stop" ->
`depart_stop` -> `disarm_stop` -> `disarm_geofence`) had their stop DISCARDED from the
dwell history. Measured on production: 58 closed visits, 35 of them with no EXIT event,
22 usable samples where there should have been 58.

The same defect was already found and fixed once, for M3's detention clock: `visit_window`
reads `GeofencePresence` and its docstring records why. It was never applied here, and
M2's dwell stats, M8's risk pair and M8's appointment-hour read all sit on this function.

The distinction these tests protect: a driver who taps "Leave this stop" HAS LEFT. That
statement is at least as authoritative as a GPS fix outside the radius — M3 already bills
detention from it — so a visit it closes is a visit that happened.
"""

from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location

DALLAS = (32.7767, -96.7970)
FAR = (32.9000, -96.7970)
T0 = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _account(db, email="dwell@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _facility(db, name="Dock 7"):
    return facility.create_facility(db, facility.FacilityType.shipper_receiver, name, *DALLAS)


def _arrive(db, account, fac, at):
    location.arm_geofence(db, account.id, fac.id)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=at)


# --- the defect ---


def test_a_stop_the_driver_ended_in_the_app_is_a_dwell_sample(db):
    """THE regression. `disarm_geofence` writes no EXIT event, so replaying edges lost
    this stop entirely — on production that was 35 of 58 closed visits."""
    account, fac = _account(db), _facility(db)
    _arrive(db, account, fac, T0)

    # the driver taps "Leave this stop" two hours later
    location.disarm_geofence(db, account.id, fac.id, occurred_at=T0 + timedelta(hours=2))

    samples = location.dwell_samples(db, fac.id)
    assert len(samples) == 1
    assert samples[0]["seconds"] == 7200
    assert samples[0]["enter_at"] == T0
    assert samples[0]["exit_at"] == T0 + timedelta(hours=2)
    assert samples[0]["arrival_hour"] == 12


def test_no_EXIT_event_is_invented_to_make_that_work(db):
    """The fix is in the READER. Synthesising an EXIT event would write fabricated
    history into the stream a claim's evidence log is built from."""
    account, fac = _account(db), _facility(db)
    _arrive(db, account, fac, T0)
    location.disarm_geofence(db, account.id, fac.id, occurred_at=T0 + timedelta(hours=2))

    kinds = [e.event_type.value for e in location.list_events(db, account.id, fac.id)]
    assert "EXIT" not in kinds
    assert location.dwell_samples(db, fac.id) != []  # and it still counts


# --- what must not change ---


def test_a_ping_driven_departure_still_yields_exactly_one_sample(db):
    """The path that already worked must not start double-counting: the same visit is
    both a closed presence row AND an ENTER/EXIT pair."""
    account, fac = _account(db), _facility(db)
    _arrive(db, account, fac, T0)
    location.evaluate_ping(db, account.id, *FAR, occurred_at=T0 + timedelta(hours=3))

    samples = location.dwell_samples(db, fac.id)
    assert len(samples) == 1
    assert samples[0]["seconds"] == 10800


def test_a_driver_still_at_the_dock_is_not_a_sample(db):
    """An open visit has no duration yet. Counting it would invent a departure."""
    account, fac = _account(db), _facility(db)
    _arrive(db, account, fac, T0)

    assert location.dwell_samples(db, fac.id) == []


def test_a_facility_nobody_has_visited_has_no_samples(db):
    assert location.dwell_samples(db, _facility(db).id) == []


def test_two_drivers_at_one_dock_are_two_samples(db):
    a = _account(db, "a@example.com")
    b = _account(db, "b@example.com")
    fac = _facility(db)
    _arrive(db, a, fac, T0)
    location.disarm_geofence(db, a.id, fac.id, occurred_at=T0 + timedelta(hours=1))
    _arrive(db, b, fac, T0 + timedelta(hours=4))
    location.disarm_geofence(db, b.id, fac.id, occurred_at=T0 + timedelta(hours=7))

    assert sorted(s["seconds"] for s in location.dwell_samples(db, fac.id)) == [3600, 10800]


def test_one_driver_returning_to_the_same_dock_is_two_samples(db):
    """Entry 73's own case, from the dwell side: a second load to the same dock is a
    second visit, not an extension of the first."""
    account, fac = _account(db), _facility(db)
    _arrive(db, account, fac, T0)
    location.disarm_geofence(db, account.id, fac.id, occurred_at=T0 + timedelta(hours=1))
    _arrive(db, account, fac, T0 + timedelta(days=2))
    location.disarm_geofence(db, account.id, fac.id, occurred_at=T0 + timedelta(days=2, hours=2))

    assert sorted(s["seconds"] for s in location.dwell_samples(db, fac.id)) == [3600, 7200]


def test_samples_belong_to_their_own_facility(db):
    account = _account(db)
    here, there = _facility(db, "Here"), _facility(db, "There")
    _arrive(db, account, here, T0)
    location.disarm_geofence(db, account.id, here.id, occurred_at=T0 + timedelta(hours=1))

    assert len(location.dwell_samples(db, here.id)) == 1
    assert location.dwell_samples(db, there.id) == []


def test_the_arrival_hour_is_the_arrival_hour_in_utc(db):
    """M2 buckets by this. Taking it off the EXIT would bucket a night arrival as a
    morning one on any stop that runs past midnight."""
    account, fac = _account(db), _facility(db)
    late = datetime(2026, 7, 20, 23, 30, tzinfo=UTC)
    _arrive(db, account, fac, late)
    location.disarm_geofence(db, account.id, fac.id, occurred_at=late + timedelta(hours=2))

    assert location.dwell_samples(db, fac.id)[0]["arrival_hour"] == 23

"""D6 — what the GPS data IS, so the pack can stop implying what it is not.

The chain proves a reading has not been altered since it was recorded. It proves nothing
about how the reading was produced — which is what made "GPS-verified" an overclaim. This
states the shape of the trail and lets the reader judge.

Read-only, shape (c): it writes nothing and cannot affect a claim even if every number is
wrong, which is why it is allowed to run at pack time.
"""

from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f03_location import public as location
from app.foundation.f03_location.domain.models import GeofenceEvent, GeofencePresence

DALLAS = (32.7767, -96.7970)
T0 = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
WINDOW = (T0 - timedelta(hours=1), T0 + timedelta(hours=6))


def _account(db, email="basis@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _ping(db, account, minutes, lat=DALLAS[0], lon=DALLAS[1], **kw):
    return location.record_ping(
        db, account.id, lat, lon, occurred_at=T0 + timedelta(minutes=minutes), **kw
    )


def test_a_window_with_no_pings_asserts_nothing(db):
    """HONEST ABSENCE. A purged trail must not render as "0 problems"."""
    account = _account(db)

    basis = location.location_basis(db, account.id, *WINDOW)

    assert basis["pings"] == 0
    assert basis["accuracy_min_m"] is None
    assert basis["accuracy_median_m"] is None
    assert basis["accuracy_max_m"] is None


def test_it_counts_the_fixes_and_reports_the_accuracy_spread(db):
    account = _account(db)
    for i, acc in enumerate([5.0, 12.0, 40.0]):
        _ping(db, account, i * 10, accuracy_m=acc)

    basis = location.location_basis(db, account.id, *WINDOW)

    assert basis["pings"] == 3
    assert basis["accuracy_reported"] == 3
    assert basis["accuracy_min_m"] == 5.0
    assert basis["accuracy_median_m"] == 12.0
    assert basis["accuracy_max_m"] == 40.0


def test_pings_without_accuracy_are_counted_but_not_averaged(db):
    """A device that does not report accuracy is not a device reporting bad accuracy."""
    account = _account(db)
    _ping(db, account, 0, accuracy_m=10.0)
    _ping(db, account, 10)  # silent

    basis = location.location_basis(db, account.id, *WINDOW)

    assert basis["pings"] == 2
    assert basis["accuracy_reported"] == 1
    assert basis["accuracy_median_m"] == 10.0


def test_a_device_clock_that_disagreed_is_surfaced(db):
    """`gps_time_divergent` has been recorded on every ping and read by nothing."""
    account = _account(db)
    _ping(db, account, 0)
    _ping(db, account, 10, gps_time=T0 + timedelta(minutes=30))  # >30s from occurred_at

    basis = location.location_basis(db, account.id, *WINDOW)

    assert basis["divergent_clock_pings"] == 1


def test_an_implausible_jump_is_counted(db):
    """~250 km in ten minutes — no truck, and worth a clerk knowing about."""
    account = _account(db)
    _ping(db, account, 0)
    _ping(db, account, 10, lat=35.0, lon=-99.0)

    basis = location.location_basis(db, account.id, *WINDOW)

    assert basis["implausible_moves"] == 1


def test_ordinary_highway_movement_is_not_implausible(db):
    """The threshold flags teleports, not lead feet — ~60 miles in an hour here."""
    account = _account(db)
    _ping(db, account, 0)
    _ping(db, account, 60, lat=33.6, lon=-96.7970)

    basis = location.location_basis(db, account.id, *WINDOW)

    assert basis["implausible_moves"] == 0


def test_two_fixes_a_moment_apart_are_not_a_teleport(db):
    """The dt floor: 30 m of jitter over 200 ms implies 150 m/s and means nothing."""
    account = _account(db)
    _ping(db, account, 0)
    location.record_ping(
        db, account.id, DALLAS[0] + 0.0003, DALLAS[1], occurred_at=T0 + timedelta(seconds=1)
    )

    basis = location.location_basis(db, account.id, *WINDOW)

    assert basis["implausible_moves"] == 0


def test_the_window_bounds_what_is_counted(db):
    account = _account(db)
    _ping(db, account, 0)
    _ping(db, account, 60 * 24)  # a day later, outside the window

    basis = location.location_basis(db, account.id, *WINDOW)

    assert basis["pings"] == 1


def test_it_writes_nothing(db):
    """Shape (c). It cannot affect a claim even if every number in it is wrong."""
    account = _account(db)
    _ping(db, account, 0)
    _ping(db, account, 10, lat=35.0, lon=-99.0)
    presences = db.query(GeofencePresence).count()
    events = db.query(GeofenceEvent).count()

    location.location_basis(db, account.id, *WINDOW)

    assert db.query(GeofencePresence).count() == presences
    assert db.query(GeofenceEvent).count() == events


def test_the_constants_are_annotate_only_and_say_so():
    """They label a report; they do not gate a clock — which is why they are not knobs."""
    import inspect

    from app.foundation.f03_location.domain import service

    assert service.IMPLAUSIBLE_SPEED_MPS == 60.0
    source = inspect.getsource(service)
    assert "ANNOTATE-ONLY" in source

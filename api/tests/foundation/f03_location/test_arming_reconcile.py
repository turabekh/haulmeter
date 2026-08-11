"""F3-1 — armings are mortal now: get-or-create, and a janitor that disarms the dead.

An arming that outlives its stop keeps minting real presence and event rows, and a
drive-by within 150 m of a dock the driver delivered to last month creates an ENTER that
`visit_window` can hand to the NEXT load as the moment its detention clock started.
"""

from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f03_location.domain.models import GeofenceArming
from app.foundation.f05_load import public as loads

DALLAS = (32.7767, -96.7970)
T0 = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)


def _setup(db, email="oo@example.com"):
    account = identity.register_account(db, email, "pw-123456")
    dock = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Dock", *DALLAS)
    load = loads.create_load(db, account.id)
    return account, dock, load


def _active(db, account):
    return (
        db.query(GeofenceArming)
        .filter(GeofenceArming.account_id == account.id, GeofenceArming.disarmed_at.is_(None))
        .count()
    )


# --- get-or-create ---
def test_arming_twice_yields_one_active_row(db):
    account, dock, _ = _setup(db)

    first = location.arm_geofence(db, account.id, dock.id)
    second = location.arm_geofence(db, account.id, dock.id)

    assert first.id == second.id
    assert _active(db, account) == 1


def test_re_arming_with_a_radius_applies_it_to_the_row_that_exists(db):
    account, dock, _ = _setup(db)
    location.arm_geofence(db, account.id, dock.id, radius_m=150.0)

    again = location.arm_geofence(db, account.id, dock.id, radius_m=400.0)

    assert again.radius_m == 400.0
    assert _active(db, account) == 1


def test_re_arming_without_a_radius_leaves_the_one_on_file(db):
    """Silence is not an instruction to widen the fence back to the default."""
    account, dock, _ = _setup(db)
    location.arm_geofence(db, account.id, dock.id, radius_m=400.0)

    again = location.arm_geofence(db, account.id, dock.id)

    assert again.radius_m == 400.0


def test_a_disarmed_arming_does_not_block_a_new_one(db):
    """The driver comes back to the dock on another load."""
    account, dock, _ = _setup(db)
    first = location.arm_geofence(db, account.id, dock.id)
    location.disarm_geofence(db, account.id, dock.id, T0)

    second = location.arm_geofence(db, account.id, dock.id)

    assert second.id != first.id
    assert _active(db, account) == 1


# --- the janitor ---
def test_an_arming_with_no_live_stop_is_disarmed(db):
    account, dock, _ = _setup(db)
    location.arm_geofence(db, account.id, dock.id)  # no stop at all

    summary = location.reconcile_armings(db, loads.has_live_stop_at, account_id=account.id)

    assert summary["orphaned"] == 1
    assert _active(db, account) == 0


def test_a_live_stop_keeps_its_fence_armed(db):
    account, dock, load = _setup(db)
    loads.add_stop(db, load, dock.id, loads.StopType.delivery)
    location.arm_geofence(db, account.id, dock.id)

    summary = location.reconcile_armings(db, loads.has_live_stop_at, account_id=account.id)

    assert summary["orphaned"] == 0
    assert _active(db, account) == 1


def test_a_SECOND_live_stop_at_the_same_dock_keeps_the_fence_armed(db):
    """The rule is per-FACILITY, not per-stop — departing one stop must not blind the other.

    Two loads to the same dock is ordinary work, and disarming on the first departure would
    take the geofence down under a driver who is still standing there on the second.
    """
    account, dock, load = _setup(db)
    first = loads.add_stop(db, load, dock.id, loads.StopType.delivery)
    second_load = loads.create_load(db, account.id)
    loads.add_stop(db, second_load, dock.id, loads.StopType.pickup)
    loads.arm_stop(db, first)

    loads.depart_stop(db, first, occurred_at=T0)

    # the fence went down with the departure, but the live second stop re-earns it
    location.arm_geofence(db, account.id, dock.id)
    summary = location.reconcile_armings(db, loads.has_live_stop_at, account_id=account.id)
    assert summary["orphaned"] == 0
    assert _active(db, account) == 1


def test_a_departed_stops_fence_is_disarmed_by_the_flow(db):
    account, dock, load = _setup(db)
    stop = loads.add_stop(db, load, dock.id, loads.StopType.delivery)
    loads.arm_stop(db, stop)
    assert _active(db, account) == 1

    loads.depart_stop(db, stop, occurred_at=T0)

    assert _active(db, account) == 0


def test_departing_one_stop_sweeps_the_fences_of_stops_never_departed(db):
    """The half `disarm_stop` never covered: a load the driver simply abandoned."""
    account, dock, load = _setup(db)
    abandoned_dock = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "Old Dock", 32.80, -96.81
    )
    location.arm_geofence(db, account.id, abandoned_dock.id)  # no stop backs it
    stop = loads.add_stop(db, load, dock.id, loads.StopType.delivery)
    loads.arm_stop(db, stop)
    assert _active(db, account) == 2

    loads.depart_stop(db, stop, occurred_at=T0)

    assert _active(db, account) == 0


def test_a_departed_stop_no_longer_earns_its_fence(db):
    """Isolates the STATUS half of the predicate.

    Every other departure test passes through `disarm_stop`, which disarms that facility
    directly — so they stay green even if the reconcile stops reading status at all. Here
    the status is moved underneath the reconcile with nothing else touching the fence, so
    only the predicate can produce the result.
    """
    account, dock, load = _setup(db)
    stop = loads.add_stop(db, load, dock.id, loads.StopType.delivery)
    location.arm_geofence(db, account.id, dock.id)
    stop.status = loads.StopStatus.departed
    db.flush()

    summary = location.reconcile_armings(db, loads.has_live_stop_at, account_id=account.id)

    assert summary["orphaned"] == 1
    assert _active(db, account) == 0


def test_an_arrived_stop_still_earns_its_fence(db):
    """The other side of the boundary: `arrived` is live — the driver is ON the dock.

    Disarming here would take the geofence down under a truck that is still sitting in it,
    and the EXIT that ends the detention clock would never fire.
    """
    account, dock, load = _setup(db)
    stop = loads.add_stop(db, load, dock.id, loads.StopType.delivery)
    location.arm_geofence(db, account.id, dock.id)
    stop.status = loads.StopStatus.arrived
    db.flush()

    summary = location.reconcile_armings(db, loads.has_live_stop_at, account_id=account.id)

    assert summary["orphaned"] == 0
    assert _active(db, account) == 1


def test_a_cancelled_loads_fences_are_disarmed(db):
    account, dock, load = _setup(db)
    loads.add_stop(db, load, dock.id, loads.StopType.delivery)
    location.arm_geofence(db, account.id, dock.id)
    loads.set_load_status(db, load, loads.LoadStatus.canceled)

    location.reconcile_armings(db, loads.has_live_stop_at, account_id=account.id)

    assert _active(db, account) == 0


def test_duplicates_collapse_to_the_earliest(db):
    """Constructed directly: `arm_geofence` no longer makes these, but every box has them.

    There is no unique index to prevent them (migration 0068 explains why), so the janitor
    is what closes the accepted arm-time race.
    """
    account, dock, load = _setup(db)
    loads.add_stop(db, load, dock.id, loads.StopType.delivery)
    earliest = GeofenceArming(account_id=account.id, facility_id=dock.id, armed_at=T0)
    later = GeofenceArming(
        account_id=account.id, facility_id=dock.id, armed_at=T0 + timedelta(hours=1)
    )
    db.add_all([earliest, later])
    db.flush()

    summary = location.reconcile_armings(db, loads.has_live_stop_at, account_id=account.id)

    assert summary["collapsed"] == 1
    assert earliest.disarmed_at is None
    assert later.disarmed_at is not None


def test_the_reconcile_never_deletes(db):
    account, dock, _ = _setup(db)
    location.arm_geofence(db, account.id, dock.id)
    before = db.query(GeofenceArming).count()

    location.reconcile_armings(db, loads.has_live_stop_at, account_id=account.id)

    assert db.query(GeofenceArming).count() == before  # timestamped, not removed


def test_it_is_idempotent(db):
    account, dock, _ = _setup(db)
    location.arm_geofence(db, account.id, dock.id)

    first = location.reconcile_armings(db, loads.has_live_stop_at, account_id=account.id)
    second = location.reconcile_armings(db, loads.has_live_stop_at, account_id=account.id)

    assert first["orphaned"] == 1
    assert second == {"scanned": 0, "orphaned": 0, "collapsed": 0}


def test_without_a_predicate_nothing_is_orphaned(db):
    """A caller that cannot say what "live" means must not get to guess."""
    account, dock, _ = _setup(db)
    location.arm_geofence(db, account.id, dock.id)

    summary = location.reconcile_armings(db, account_id=account.id)

    assert summary["orphaned"] == 0
    assert _active(db, account) == 1


def test_the_nightly_runner_reports_what_it_reconciled(db):
    from app.ingest import runners

    account, dock, _ = _setup(db)
    location.arm_geofence(db, account.id, dock.id)

    summary = runners.run_location_retention(db, commit=False)

    assert summary["armings"]["orphaned"] == 1
    assert _active(db, account) == 0

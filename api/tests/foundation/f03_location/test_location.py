from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f13_flags import public as flags

DALLAS = (32.7767, -96.7970)
FAR = (32.9000, -96.7970)
T0 = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _account(db, email="driver@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _facility(db, name="Dock 7", coords=DALLAS):
    return facility.create_facility(db, facility.FacilityType.shipper_receiver, name, *coords)


def test_record_ping_captures_server_time_and_skew(db):
    account = _account(db)
    ping = location.record_ping(db, account.id, *DALLAS, occurred_at=T0, client_skew_ms=420)
    assert ping.received_at is not None
    assert ping.client_skew_ms == 420
    assert ping.gps_time_divergent is False


def test_gps_time_divergence_flagged(db):
    account = _account(db)
    diverged = location.record_ping(
        db, account.id, *DALLAS, occurred_at=T0, gps_time=T0 + timedelta(minutes=5)
    )
    assert diverged.gps_time_divergent is True
    aligned = location.record_ping(
        db, account.id, *DALLAS, occurred_at=T0, gps_time=T0 + timedelta(seconds=5)
    )
    assert aligned.gps_time_divergent is False


def test_enter_emitted_once_then_suppressed(db):
    account = _account(db)
    fac = _facility(db)
    location.arm_geofence(db, account.id, fac.id)

    first = location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0)
    assert [e.event_type for e in first] == [location.GeofenceEventType.ENTER]

    again = location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0 + timedelta(minutes=1))
    assert again.events == []


def test_dwell_tick_after_interval(db):
    account = _account(db)
    fac = _facility(db)
    location.arm_geofence(db, account.id, fac.id)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0)

    tick = location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0 + timedelta(minutes=16))
    assert [e.event_type for e in tick] == [location.GeofenceEventType.DWELL_TICK]


def test_exit_emitted_when_leaving(db):
    account = _account(db)
    fac = _facility(db)
    location.arm_geofence(db, account.id, fac.id)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0)

    out = location.evaluate_ping(db, account.id, *FAR, occurred_at=T0 + timedelta(minutes=20))
    assert [e.event_type for e in out] == [location.GeofenceEventType.EXIT]


def test_no_enter_when_outside_radius(db):
    account = _account(db)
    fac = _facility(db)
    location.arm_geofence(db, account.id, fac.id)
    events = location.evaluate_ping(db, account.id, *FAR, occurred_at=T0)
    assert events.events == []


def test_polygon_geofence_overrides_radius(db):
    account = _account(db)
    fac = facility.create_facility(
        db, facility.FacilityType.parking_property, "Polygon Lot", *DALLAS
    )
    facility.set_lot_polygon(
        db,
        fac,
        "POLYGON((-96.7990 32.7757, -96.7950 32.7757, "
        "-96.7950 32.7777, -96.7990 32.7777, -96.7990 32.7757))",
    )
    location.arm_geofence(db, account.id, fac.id, radius_m=1)
    events = location.evaluate_ping(db, account.id, 32.7770, -96.7965, occurred_at=T0)
    assert [e.event_type for e in events] == [location.GeofenceEventType.ENTER]


def test_disarm_stops_evaluation_and_closes_presence(db):
    account = _account(db)
    fac = _facility(db)
    location.arm_geofence(db, account.id, fac.id)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0)

    location.disarm_geofence(db, account.id, fac.id, occurred_at=T0 + timedelta(minutes=5))
    after = location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0 + timedelta(minutes=30))
    assert after.events == []


def test_confirmed_arrivals_feedback_increments(db):
    account = _account(db)
    fac = _facility(db)
    location.arm_geofence(db, account.id, fac.id)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0)
    config = db.get(location.FacilityGeofence, fac.id)
    assert config.confirmed_arrivals == 1


def test_build_trace_makes_linestring(db):
    account = _account(db)
    location.record_ping(db, account.id, 32.7000, -96.8000, occurred_at=T0)
    location.record_ping(db, account.id, 32.7100, -96.8100, occurred_at=T0 + timedelta(minutes=5))
    location.record_ping(db, account.id, 32.7200, -96.8200, occurred_at=T0 + timedelta(minutes=10))
    trace = location.build_trace(db, account.id, T0 - timedelta(hours=1), T0 + timedelta(hours=1))
    assert trace is not None
    assert trace.startswith("LINESTRING")


def test_build_trace_none_for_single_point(db):
    account = _account(db)
    location.record_ping(db, account.id, *DALLAS, occurred_at=T0)
    trace = location.build_trace(db, account.id, T0 - timedelta(hours=1), T0 + timedelta(hours=1))
    assert trace is None


def test_purge_pings_retention(db):
    account = _account(db)
    location.record_ping(db, account.id, *DALLAS, occurred_at=T0)
    location.record_ping(db, account.id, *DALLAS, occurred_at=T0 + timedelta(minutes=1))
    removed = location.purge_pings_older_than(db, datetime.now(UTC) + timedelta(days=1))
    assert removed == 2


def test_expired_pings_are_purged_on_the_configured_window(db):
    # audit F-09: the purge existed, was exported, and its only caller was one test —
    # so `location_ping` grew without bound and PRD §7.3's "configurable retention"
    # was enforced nowhere.
    account = _account(db)
    now = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    old = location.record_ping(db, account.id, *DALLAS, occurred_at=T0)
    recent = location.record_ping(db, account.id, *DALLAS, occurred_at=T0)
    old.received_at = now - timedelta(days=400)
    recent.received_at = now - timedelta(days=10)
    db.flush()

    summary = location.purge_expired_pings(db, now=now)
    assert summary == {"deleted": 1, "retention_days": 365, "purged": True}
    assert db.get(location.LocationPing, recent.id) is not None
    assert db.get(location.LocationPing, old.id) is None


def test_a_retention_of_zero_never_purges_rather_than_purging_everything(db):
    # the one job in the worker that DESTROYS data, and the plausible operator accident
    # is typing 0 meaning "off". Read as a cutoff, 0 deletes the entire table.
    flags.set_config(db, location.CONFIG_PING_RETENTION_DAYS, 0)
    account = _account(db)
    now = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    ping = location.record_ping(db, account.id, *DALLAS, occurred_at=T0)
    ping.received_at = now - timedelta(days=4000)
    db.flush()

    summary = location.purge_expired_pings(db, now=now)
    assert summary == {"deleted": 0, "retention_days": 0, "purged": False}
    assert db.get(location.LocationPing, ping.id) is not None


def test_the_purge_is_wired_to_the_worker(db):
    # F-09 WAS a purge nothing called. Without this assertion the fix is one refactor
    # away from being the same finding again, and the tests above would all still pass.
    from app.worker import _jobs

    job = next(j for j in _jobs() if j.name == "location_retention")
    assert job.flag_key is None  # a foundation retention job gated on an unregistered
    assert job.interval_seconds == 86400  # flag is a policy that silently does not run


def test_the_retention_window_is_declared_so_an_operator_can_find_it(db):
    # session 112's finding: /admin/config listed only keys somebody had already set
    from app import module_registry

    module_registry.register_all(db)
    declared = flags.declared_configs(db, scope="location")
    assert location.CONFIG_PING_RETENTION_DAYS in declared


def test_is_present_tracks_geofence_presence(db):
    account = _account(db)
    fac = _facility(db)
    location.arm_geofence(db, account.id, fac.id)
    assert location.is_present(db, account.id, fac.id) is False
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0)
    assert location.is_present(db, account.id, fac.id) is True
    location.evaluate_ping(db, account.id, *FAR, occurred_at=T0 + timedelta(minutes=20))
    assert location.is_present(db, account.id, fac.id) is False


def test_arm_unknown_facility_raises(db):
    import uuid

    account = _account(db)
    try:
        location.arm_geofence(db, account.id, uuid.uuid4())
        raised = False
    except location.FacilityNotFound:
        raised = True
    assert raised is True


# --- last known position: only when it is still worth believing ---
def test_last_known_position_returns_the_most_recent_ping(db):
    account = _account(db, "lastpos@example.com")
    location.record_ping(db, account.id, *DALLAS, occurred_at=T0 - timedelta(hours=2))
    location.record_ping(db, account.id, 40.7128, -74.0060, occurred_at=T0 - timedelta(minutes=10))

    got = location.last_known_position(db, account.id, timedelta(hours=6), now=T0)

    assert got is not None
    lat, lon = got
    assert round(lat, 3) == 40.713
    assert round(lon, 3) == -74.006


def test_a_stale_ping_is_not_a_position(db):
    """A ping from days ago is a place the driver has long left. Returning it would
    let a caller target an interruption on a guess, so the bound returns nothing and
    the caller is expected to stay quiet."""
    account = _account(db, "stalepos@example.com")
    location.record_ping(db, account.id, *DALLAS, occurred_at=T0 - timedelta(days=3))

    assert location.last_known_position(db, account.id, timedelta(hours=6), now=T0) is None
    # the same ping inside a wider bound is fine — the caller chooses the bound
    assert location.last_known_position(db, account.id, timedelta(days=7), now=T0) is not None


def test_a_driver_who_never_pinged_has_no_position(db):
    account = _account(db, "nopos@example.com")
    assert location.last_known_position(db, account.id, timedelta(hours=6), now=T0) is None


def test_one_drivers_position_is_never_anothers(db):
    a = _account(db, "pos-a@example.com")
    b = _account(db, "pos-b@example.com")
    location.record_ping(db, a.id, *DALLAS, occurred_at=T0 - timedelta(minutes=5))

    assert location.last_known_position(db, a.id, timedelta(hours=6), now=T0) is not None
    assert location.last_known_position(db, b.id, timedelta(hours=6), now=T0) is None


def test_visit_window_does_not_walk_every_visit_ever_made(db):
    # audit F-15: this loaded every GeofencePresence row for the driver/facility pair
    # and skipped the closed ones in Python. The skip is a WHERE clause now.
    account = _account(db)
    fac = _facility(db)
    for day in range(10):
        location.arm_geofence(db, account.id, fac.id)
        location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0 + timedelta(days=day))
        location.evaluate_ping(
            db, account.id, *FAR, occurred_at=T0 + timedelta(days=day, hours=3)
        )
        location.disarm_geofence(
            db, account.id, fac.id, occurred_at=T0 + timedelta(days=day, hours=3)
        )

    statements = []
    from sqlalchemy import event

    def record(conn, cursor, statement, params, context, executemany):
        if "geofence_presence" in statement.lower():
            statements.append(statement.lower())

    event.listen(db.get_bind(), "before_cursor_execute", record)
    try:
        entered, exited = location.visit_window(db, account.id, fac.id, T0 + timedelta(days=9))
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", record)

    # the LAST visit, and the query asked for one row rather than all ten
    assert entered == T0 + timedelta(days=9)
    assert exited == T0 + timedelta(days=9, hours=3)
    assert any("limit" in s for s in statements)


def test_visit_window_still_picks_the_visit_belonging_to_the_load(db):
    # §23 entry 73 is what this function exists for; the narrowing must not undo it
    account = _account(db)
    fac = _facility(db)
    for day in (0, 5):
        location.arm_geofence(db, account.id, fac.id)
        location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0 + timedelta(days=day))
        location.evaluate_ping(
            db, account.id, *FAR, occurred_at=T0 + timedelta(days=day, hours=2)
        )
        location.disarm_geofence(
            db, account.id, fac.id, occurred_at=T0 + timedelta(days=day, hours=2)
        )

    # a load whose appointment is on day 5 must not bill from the day-0 visit
    entered, _ = location.visit_window(db, account.id, fac.id, T0 + timedelta(days=4))
    assert entered == T0 + timedelta(days=5)
    # and a load on day 0 still gets day 0
    entered_first, _ = location.visit_window(db, account.id, fac.id, T0 - timedelta(hours=1))
    assert entered_first == T0

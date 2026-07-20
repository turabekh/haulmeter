from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location

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

    again = location.evaluate_ping(
        db, account.id, *DALLAS, occurred_at=T0 + timedelta(minutes=1)
    )
    assert again == []


def test_dwell_tick_after_interval(db):
    account = _account(db)
    fac = _facility(db)
    location.arm_geofence(db, account.id, fac.id)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0)

    tick = location.evaluate_ping(
        db, account.id, *DALLAS, occurred_at=T0 + timedelta(minutes=16)
    )
    assert [e.event_type for e in tick] == [location.GeofenceEventType.DWELL_TICK]


def test_exit_emitted_when_leaving(db):
    account = _account(db)
    fac = _facility(db)
    location.arm_geofence(db, account.id, fac.id)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0)

    out = location.evaluate_ping(
        db, account.id, *FAR, occurred_at=T0 + timedelta(minutes=20)
    )
    assert [e.event_type for e in out] == [location.GeofenceEventType.EXIT]


def test_no_enter_when_outside_radius(db):
    account = _account(db)
    fac = _facility(db)
    location.arm_geofence(db, account.id, fac.id)
    events = location.evaluate_ping(db, account.id, *FAR, occurred_at=T0)
    assert events == []


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
    after = location.evaluate_ping(
        db, account.id, *DALLAS, occurred_at=T0 + timedelta(minutes=30)
    )
    assert after == []


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

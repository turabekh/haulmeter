from datetime import UTC, datetime

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f10_crowd import public as crowd
from app.foundation.f11_map import public as mapsvc

ORIGIN = (32.7767, -96.7970)
NORTH = (32.9000, -96.7970)
SOUTH = (32.6500, -96.7970)
T0 = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _account(db, email="driver@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _facility(db, ftype, name, coords):
    return facility.create_facility(db, ftype, name, *coords)


def _set_belief(db, account, fac, signal, value):
    crowd.submit(db, account.id, fac.id, signal, value, submitted_at=T0, award=False)
    crowd.update_belief(db, fac.id, signal, as_of=T0)


def test_overlay_pin_shape_from_facility_type(db):
    _facility(db, facility.FacilityType.truck_stop, "Stop", ORIGIN)
    _facility(db, facility.FacilityType.parking_property, "Lot", (32.7770, -96.7972))
    _facility(db, facility.FacilityType.shipper_receiver, "Dock", (32.7772, -96.7974))
    pins = mapsvc.overlay_pins(db, *ORIGIN, radius_m=5000)
    shapes = {p.facility_type: p.shape for p in pins}
    assert shapes["truck_stop"] == "circle"
    assert shapes["parking_property"] == "square"
    assert shapes["shipper_receiver"] == "diamond"


def test_overlay_pin_carries_status_and_freshness_from_belief(db):
    account = _account(db)
    stop = _facility(db, facility.FacilityType.truck_stop, "Stop", ORIGIN)
    _set_belief(db, account, stop, crowd.SignalType.parking_fullness, {"status": "full"})
    pins = mapsvc.overlay_pins(db, *ORIGIN, radius_m=2000)
    pin = next(p for p in pins if p.facility_id == stop.id)
    assert pin.status == "full"
    assert pin.freshness is not None
    assert pin.freshness.sample_size == 1


def test_overlay_fuel_price_badge(db):
    account = _account(db)
    fuel = _facility(db, facility.FacilityType.fuel_station, "Fuel", ORIGIN)
    _set_belief(db, account, fuel, crowd.SignalType.fuel_price, {"price_cents": 459})
    pins = mapsvc.overlay_pins(db, *ORIGIN, radius_m=2000)
    pin = next(p for p in pins if p.facility_id == fuel.id)
    badges = {b.kind: b.value for b in pin.badges}
    assert badges["fuel_price"] == 459


def test_no_badge_or_status_without_belief(db):
    fac = _facility(db, facility.FacilityType.truck_stop, "Quiet Stop", ORIGIN)
    pins = mapsvc.overlay_pins(db, *ORIGIN, radius_m=2000)
    pin = next(p for p in pins if p.facility_id == fac.id)
    assert pin.status is None
    assert pin.badges == []
    assert pin.freshness is None


def test_clustering_groups_and_reports_dominant_status(db):
    account = _account(db)
    a = _facility(db, facility.FacilityType.truck_stop, "A", (32.7767, -96.7970))
    b = _facility(db, facility.FacilityType.truck_stop, "B", (32.7768, -96.7971))
    _set_belief(db, account, a, crowd.SignalType.parking_fullness, {"status": "full"})
    _set_belief(db, account, b, crowd.SignalType.parking_fullness, {"status": "full"})
    pins = mapsvc.overlay_pins(db, *ORIGIN, radius_m=2000)
    clusters = mapsvc.cluster_pins(pins, precision_deg=0.1)
    assert len(clusters) == 1
    assert clusters[0].count == 2
    assert clusters[0].dominant_status == "full"


def test_corridor_returns_only_facilities_ahead_sorted(db):
    _facility(db, facility.FacilityType.truck_stop, "Ahead-near", (32.8200, -96.7970))
    _facility(db, facility.FacilityType.truck_stop, "Ahead-far", NORTH)
    _facility(db, facility.FacilityType.truck_stop, "Behind", SOUTH)
    entries = mapsvc.corridor(
        db, *ORIGIN, heading_deg=0.0, max_distance_m=40000, half_angle_deg=45
    )
    names = [e.name for e in entries]
    assert "Behind" not in names
    assert names == ["Ahead-near", "Ahead-far"]
    assert entries[0].distance_m < entries[1].distance_m


def test_corridor_excludes_off_heading(db):
    _facility(db, facility.FacilityType.truck_stop, "East", (32.7767, -96.6500))
    entries = mapsvc.corridor(
        db, *ORIGIN, heading_deg=0.0, max_distance_m=40000, half_angle_deg=45
    )
    assert [e.name for e in entries] == []

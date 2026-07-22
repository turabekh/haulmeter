from datetime import UTC, datetime

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f07_ledger import public as ledger
from app.foundation.f10_crowd import public as crowd
from app.foundation.f13_flags import public as flags
from app.modules.m01_map import public as m1

DALLAS = (32.7767, -96.7970)
NORTH = (32.9000, -96.7970)
SOUTH = (32.6500, -96.7970)
T0 = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _account(db, email="driver@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _belief(db, account, fac, signal, value):
    crowd.submit(db, account.id, fac.id, signal, value, submitted_at=T0, award=False)
    crowd.update_belief(db, fac.id, signal, as_of=T0)


def test_register_module_creates_flag_and_admin_view(db):
    m1.register_module(db)
    assert flags.is_enabled(db, "m01_map") is False  # registered, off until activated
    flags.enable(db, "m01_map")
    assert flags.is_enabled(db, "m01_map") is True


def test_drive_preset_shows_only_its_layers(db):
    account = _account(db)
    facility.create_facility(db, facility.FacilityType.truck_stop, "Stop", DALLAS[0], DALLAS[1])
    facility.create_facility(db, facility.FacilityType.fuel_station, "Fuel", 32.7770, -96.7972)
    facility.create_facility(db, facility.FacilityType.shipper_receiver, "Dock", 32.7772, -96.7974)
    pins = m1.map_overlay(db, account.id, *DALLAS, radius_m=3000, preset=m1.Preset.drive)
    types = {p.facility_type for p in pins}
    assert "shipper_receiver" not in types  # not a Drive-preset layer
    assert "truck_stop" in types and "fuel_station" in types


def test_overlay_clusters_at_density_bounding_the_payload(db):
    # design-prd §11.5 / §20: above the pin cap the server returns clusters, so the
    # payload stays bounded at real national density (here forced with a low cap).
    account = _account(db)
    for i in range(12):
        facility.create_facility(
            db, facility.FacilityType.truck_stop, f"Stop {i}", 32.77 + i * 0.001, -96.80 + i * 0.001
        )
    sparse = m1.map_overlay_view(db, account.id, 32.78, -96.79, 20000, cap=100)
    assert sparse["clustered"] is False and len(sparse["pins"]) == 12

    dense = m1.map_overlay_view(db, account.id, 32.78, -96.79, 20000, cap=3)
    assert dense["clustered"] is True
    assert dense["pins"] == []  # no per-pin payload
    assert dense["total"] == 12
    assert 0 < len(dense["clusters"]) < 12  # bounded: fewer cluster cells than pins
    assert sum(c.count for c in dense["clusters"]) == 12  # every facility accounted for


def test_tonight_preset_sorts_by_availability(db):
    account = _account(db)
    full = facility.create_facility(db, facility.FacilityType.truck_stop, "Full", *DALLAS)
    empty = facility.create_facility(
        db, facility.FacilityType.truck_stop, "Empty", 32.7770, -96.7972
    )
    _belief(db, account, full, crowd.SignalType.parking_fullness, {"status": "full"})
    _belief(db, account, empty, crowd.SignalType.parking_fullness, {"status": "empty"})
    pins = m1.map_overlay(db, account.id, *DALLAS, radius_m=3000, preset=m1.Preset.tonight)
    assert pins[0].facility_id == empty.id  # best availability first


def test_amenity_filter(db):
    account = _account(db)
    facility.create_facility(
        db,
        facility.FacilityType.truck_stop,
        "With showers",
        *DALLAS,
        attributes={"amenities": ["showers", "scale"]},
    )
    facility.create_facility(
        db,
        facility.FacilityType.truck_stop,
        "No showers",
        32.7770,
        -96.7972,
        attributes={"amenities": ["scale"]},
    )
    pins = m1.map_overlay(
        db,
        account.id,
        *DALLAS,
        radius_m=3000,
        preset=m1.Preset.drive,
        required_amenities=["showers"],
    )
    assert [p.name for p in pins] == ["With showers"]


def test_corridor_view_ahead_only(db):
    facility.create_facility(db, facility.FacilityType.truck_stop, "Ahead", NORTH[0], NORTH[1])
    facility.create_facility(db, facility.FacilityType.truck_stop, "Behind", SOUTH[0], SOUTH[1])
    entries = m1.corridor_view(
        db, None, *DALLAS, heading_deg=0.0, max_distance_m=40000, preset=m1.Preset.drive
    )
    assert [e.name for e in entries] == ["Ahead"]


def test_prediction_is_heuristic_with_basis(db):
    evening = m1.predict_parking_fill(db, None, hour_of_day=19)
    assert evening.status == "full"
    assert evening.basis == "heuristic"
    morning = m1.predict_parking_fill(db, None, hour_of_day=9)
    assert morning.status == "empty"


def test_status_contribution_awards_points_when_present(db):
    account = _account(db)
    fac = facility.create_facility(db, facility.FacilityType.truck_stop, "Stop", *DALLAS)
    location.arm_geofence(db, account.id, fac.id)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0)
    m1.submit_status(
        db, account.id, fac.id, crowd.SignalType.parking_fullness, {"status": "full"}, T0
    )
    points_acct = ledger.get_or_create_account(
        db,
        ledger.LedgerAccountKind.points_balance,
        f"points:{account.id}",
        currency=ledger.Currency.points,
        owner_ref=account.id,
    )
    assert ledger.balance(db, points_acct) > 0


def test_offline_contribution_syncs_once(db):
    account = _account(db)
    fac = facility.create_facility(db, facility.FacilityType.truck_stop, "Stop", *DALLAS)
    key = "report-1"
    first = m1.queue_status_offline(
        db, account.id, key, fac.id, crowd.SignalType.parking_fullness, {"status": "some"}, T0
    )
    retry = m1.queue_status_offline(
        db, account.id, key, fac.id, crowd.SignalType.parking_fullness, {"status": "some"}, T0
    )
    assert first.applied is True
    assert retry.applied is False


def test_nav_deeplink_handoff(db):
    url = m1.nav_deeplink(32.7767, -96.7970, provider=m1.NavProvider.google)
    assert url == "https://www.google.com/maps/dir/?api=1&destination=32.7767,-96.797"
    assert m1.nav_deeplink(32.7767, -96.797, provider=m1.NavProvider.apple).startswith(
        "https://maps.apple.com/?daddr="
    )

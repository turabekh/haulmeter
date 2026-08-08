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
    """AI-CONTEXT: this asserted `is_enabled(...) is False` after registration, and that
    was never what production looked like (audit F-02, §23 entry 133). `register_all`
    force-assigned `enabled = True`, so on every real box M1 came up ON while the test
    environment had it off — the suite was measuring a state the product never had.

    M1 DECLARES `default_on=True` now, so the test and the box agree, and the assertion
    became the sharper one: the capability is on because the code ships it on, and NO
    operator has decided anything. Those were indistinguishable before."""
    m1.register_module(db)
    row = db.get(flags.FeatureFlag, "m01_map")
    assert row is not None  # registered — switchable in the console
    assert row.default_on is True  # ships on: the 29 July decision, declared
    assert row.enabled is None  # and nobody has overruled it
    assert flags.is_enabled(db, "m01_map") is True

    # an operator's decision beats the declaration, in both directions
    flags.disable(db, "m01_map")
    assert flags.is_enabled(db, "m01_map") is False
    flags.clear_decision(db, "m01_map")
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


def test_overlay_bbox_returns_only_facilities_in_view(db):
    # the viewport-driven overlay (primary map mode): a bbox query returns exactly
    # what falls inside the rectangle, nothing outside it (fixes the empty map).
    account = _account(db)
    facility.create_facility(db, facility.FacilityType.truck_stop, "InView", 32.78, -96.79)
    facility.create_facility(db, facility.FacilityType.truck_stop, "FarAway", 41.88, -87.63)  # IL
    view = m1.map_overlay_view_bbox(db, account.id, 32.70, -96.90, 32.90, -96.70)
    assert view["clustered"] is False
    names = {p.name for p in view["pins"]}
    assert names == {"InView"}  # the Illinois stop is outside the Texas viewport


def test_overlay_bbox_clusters_when_dense(db):
    # a small viewport over many facilities clusters (payload bounded, §11.5)
    account = _account(db)
    for i in range(12):
        facility.create_facility(
            db, facility.FacilityType.truck_stop, f"Stop {i}", 32.77 + i * 0.001, -96.80 + i * 0.001
        )
    sparse = m1.map_overlay_view_bbox(db, account.id, 32.70, -96.90, 32.90, -96.70, cap=100)
    assert sparse["clustered"] is False and len(sparse["pins"]) == 12

    dense = m1.map_overlay_view_bbox(db, account.id, 32.70, -96.90, 32.90, -96.70, cap=3)
    assert dense["clustered"] is True and dense["pins"] == []
    assert sum(c.count for c in dense["clusters"]) == 12  # every facility accounted for


def test_overlay_bbox_area_cap_forces_clusters(db):
    # a continental-span viewport always clusters, even when sparse — so a national
    # pan never returns thousands of individual pins (MAX_BBOX_DEG2 guard).
    account = _account(db)
    facility.create_facility(db, facility.FacilityType.truck_stop, "TX", 32.78, -96.79)
    facility.create_facility(db, facility.FacilityType.truck_stop, "IL", 41.88, -87.63)
    view = m1.map_overlay_view_bbox(db, account.id, 24.0, -125.0, 50.0, -66.0)  # continental US
    assert view["clustered"] is True  # area > MAX_BBOX_DEG2, though only 2 facilities
    assert view["pins"] == [] and sum(c.count for c in view["clusters"]) == 2


def test_overlay_bbox_filters_by_preset(db):
    # bbox mode honors the preset layer filter (Work = shipper/receiver only)
    account = _account(db)
    facility.create_facility(db, facility.FacilityType.truck_stop, "Stop", 32.78, -96.79)
    facility.create_facility(db, facility.FacilityType.shipper_receiver, "Dock", 32.781, -96.791)
    view = m1.map_overlay_view_bbox(
        db, account.id, 32.70, -96.90, 32.90, -96.70, preset=m1.Preset.work
    )
    assert {p.name for p in view["pins"]} == {"Dock"}  # truck stop excluded by preset


def test_cluster_precision_is_zoom_adaptive():
    from app.modules.m01_map.domain.service import _cluster_precision_deg

    # a continental view uses much coarser cells than a metro view, so a zoomed-out
    # map doesn't over-cluster into thousands of cells
    assert _cluster_precision_deg(3_000_000) > _cluster_precision_deg(20_000)
    assert _cluster_precision_deg(1_000) == 0.02  # floored for tight views


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


def test_corridor_ahead_carries_the_status_the_pin_would_show(db):
    # §23 entry 81: the stack rendered a FIXTURE because `corridor_view` returns
    # geometry alone. Run against the old implementation this fails on the missing
    # key, which is the whole point of the new reader existing.
    account = _account(db)
    fac = facility.create_facility(db, facility.FacilityType.truck_stop, "Ahead", *NORTH)
    _belief(db, account, fac, crowd.SignalType.parking_fullness, {"status": "full"})
    rows = m1.corridor_ahead(db, account.id, *DALLAS, heading_deg=0.0, max_distance_m=40000)
    assert [r["name"] for r in rows] == ["Ahead"]
    assert rows[0]["status"] == "full"
    assert rows[0]["sample_size"] == 1
    assert rows[0]["reported_at"] is not None


def test_corridor_ahead_says_nothing_rather_than_guessing_a_status(db):
    # §11.7: an unreported facility reports NO status. A default of "empty" here
    # would send a driver past a full lot on our word.
    account = _account(db)
    facility.create_facility(db, facility.FacilityType.truck_stop, "Unreported", *NORTH)
    rows = m1.corridor_ahead(db, account.id, *DALLAS, heading_deg=0.0, max_distance_m=40000)
    assert rows[0]["status"] is None
    assert rows[0]["sample_size"] == 0


def test_corridor_ahead_asks_a_scale_whether_it_is_open_not_how_full(db):
    # the signal follows the facility KIND. Reading parking fullness off a weigh
    # station would render a status that means nothing about it.
    account = _account(db)
    m1.register_module(db)
    flags.enable(db, m1.WEIGH_STATION_FLAG)
    scale = facility.create_facility(db, facility.FacilityType.weigh_station, "Scale", *NORTH)
    _belief(db, account, scale, crowd.SignalType.weigh_station_status, {"status": "closed"})
    _belief(db, account, scale, crowd.SignalType.parking_fullness, {"status": "full"})
    rows = m1.corridor_ahead(db, account.id, *DALLAS, heading_deg=0.0, max_distance_m=40000)
    assert rows[0]["status"] == "closed"  # never "full"


def test_corridor_ahead_caps_at_three(db):
    # §11.4 names the size. A stack a driver has to scroll at speed is a list.
    account = _account(db)
    for i in range(6):
        facility.create_facility(
            db, facility.FacilityType.truck_stop, f"Stop {i}", NORTH[0] + i * 0.01, NORTH[1]
        )
    rows = m1.corridor_ahead(db, account.id, *DALLAS, heading_deg=0.0, max_distance_m=60000)
    assert len(rows) == m1.MAX_CORRIDOR_ENTRIES == 3


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

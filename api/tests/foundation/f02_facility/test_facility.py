from app.foundation.f02_facility import public as facility

DALLAS = (32.7767, -96.7970)


def test_create_and_read_facility(db):
    fac = facility.create_facility(
        db, facility.FacilityType.truck_stop, "Dallas Travel Center", *DALLAS
    )
    assert fac.status == facility.FacilityStatus.confirmed
    got = facility.get_facility(db, fac.id)
    assert got is not None
    lat, lon = facility.coordinates(db, got)
    assert round(lat, 3) == round(DALLAS[0], 3)
    assert round(lon, 3) == round(DALLAS[1], 3)


def test_polygon_and_point_round_trip_via_radius(db):
    facility.create_facility(db, facility.FacilityType.parking_property, "Lot A", *DALLAS)
    near = facility.nearest(db, DALLAS[0], DALLAS[1], radius_m=1000)
    assert len(near) == 1
    far = facility.nearest(db, 40.7128, -74.0060, radius_m=1000)
    assert far == []


def test_radius_query_filters_by_type(db):
    facility.create_facility(db, facility.FacilityType.fuel_station, "Fuel 1", *DALLAS)
    facility.create_facility(db, facility.FacilityType.truck_stop, "Stop 1", 32.7770, -96.7975)
    fuel_only = facility.nearest(
        db, DALLAS[0], DALLAS[1], radius_m=2000, facility_type=facility.FacilityType.fuel_station
    )
    assert len(fuel_only) == 1
    assert fuel_only[0].facility_type == facility.FacilityType.fuel_station


def test_checkin_creates_candidate_that_stays_candidate(db):
    cand = facility.create_candidate_from_checkin(
        db, facility.FacilityType.shipper_receiver, "Unconfirmed Dock", *DALLAS
    )
    assert cand.status == facility.FacilityStatus.candidate
    reloaded = facility.get_facility(db, cand.id)
    assert reloaded.status == facility.FacilityStatus.candidate


def test_second_independent_signal_confirms_candidate(db):
    cand = facility.create_candidate_from_checkin(
        db, facility.FacilityType.shipper_receiver, "Pending Dock", *DALLAS
    )
    facility.confirm_with_second_signal(db, cand, facility.SourceKind.osm)
    assert cand.status == facility.FacilityStatus.confirmed


def test_dedup_blocks_near_duplicate_by_geohash_and_name(db):
    facility.create_facility(db, facility.FacilityType.truck_stop, "Loves Travel Stop", *DALLAS)
    dupes = facility.find_duplicate_candidates(db, "Loves Travel Stop", 32.7768, -96.7971)
    assert len(dupes) >= 1


def test_dedup_ignores_far_or_dissimilar(db):
    facility.create_facility(db, facility.FacilityType.truck_stop, "Loves Travel Stop", *DALLAS)
    far = facility.find_duplicate_candidates(db, "Loves Travel Stop", 40.7128, -74.0060)
    assert far == []


def test_contains_point_by_radius(db):
    fac = facility.create_facility(db, facility.FacilityType.truck_stop, "Radius Stop", *DALLAS)
    assert facility.contains_point(db, fac, DALLAS[0], DALLAS[1], radius_m=150) is True
    assert facility.contains_point(db, fac, 32.7900, -96.7970, radius_m=150) is False


def test_lot_polygon_overrides_radius_for_containment(db):
    fac = facility.create_facility(
        db, facility.FacilityType.parking_property, "Polygon Lot", *DALLAS
    )
    facility.set_lot_polygon(
        db,
        fac,
        "POLYGON((-96.7990 32.7757, -96.7950 32.7757, "
        "-96.7950 32.7777, -96.7990 32.7777, -96.7990 32.7757))",
    )
    inside = facility.contains_point(db, fac, 32.7767, -96.7970, radius_m=1)
    assert inside is True
    outside = facility.contains_point(db, fac, 32.7767, -96.7900, radius_m=1)
    assert outside is False


def test_merge_preserves_canonical_id_and_reassigns_sources(db):
    canonical = facility.create_facility(
        db, facility.FacilityType.truck_stop, "Canonical Stop", *DALLAS
    )
    duplicate = facility.create_candidate_from_checkin(
        db, facility.FacilityType.truck_stop, "Canonical Stop (dup)", 32.7768, -96.7971
    )
    facility.merge_facilities(db, canonical, duplicate)

    assert duplicate.status == facility.FacilityStatus.merged
    assert duplicate.merged_into_id == canonical.id
    resolved = facility.resolve_canonical(db, duplicate.id)
    assert resolved.id == canonical.id
    db.refresh(canonical)
    assert len(canonical.sources) == 2


def _with_services(db, name, services, lat=32.7767, lon=-96.7970):
    return facility.create_facility(
        db,
        facility.FacilityType.truck_stop,
        name,
        lat,
        lon,
        attributes={"services": services} if services else {},
    )


def test_service_search_finds_by_partial_name_any_case(db):
    _with_services(db, "Gateway Truck Wash", [facility.SERVICE_WASH])
    assert [f.name for f in facility.search_service_facilities(db, "gateway")] == [
        "Gateway Truck Wash"
    ]
    assert [f.name for f in facility.search_service_facilities(db, "TRUCK WASH")] == [
        "Gateway Truck Wash"
    ]


def test_service_search_never_returns_a_facility_with_nothing_to_claim(db):
    # E3.2: the `services` list is the one source of truth for "is there a service
    # business here". A facility without one is not claimable, so it is not a result.
    _with_services(db, "Gateway Truck Wash", [facility.SERVICE_WASH])
    _with_services(db, "Gateway Rest Area", [])
    found = facility.search_service_facilities(db, "gateway")
    assert [f.name for f in found] == ["Gateway Truck Wash"]


def test_service_search_ignores_a_merged_away_facility(db):
    canonical = _with_services(db, "Gateway Tire", [facility.SERVICE_TIRE])
    duplicate = _with_services(db, "Gateway Tire Co", [facility.SERVICE_TIRE], 32.7768, -96.7971)
    facility.merge_facilities(db, canonical, duplicate)
    found = facility.search_service_facilities(db, "gateway tire")
    assert [f.id for f in found] == [canonical.id]


def test_service_search_needs_two_characters_and_honours_its_limit(db):
    for n in range(4):
        _with_services(db, f"Gateway Repair {n}", [facility.SERVICE_REPAIR])
    assert facility.search_service_facilities(db, "g") == []
    assert facility.search_service_facilities(db, "  ") == []
    assert len(facility.search_service_facilities(db, "gateway", limit=2)) == 2


def test_distances_are_measured_from_the_origin_in_one_call(db):
    here = facility.create_facility(db, facility.FacilityType.truck_stop, "Here", *DALLAS)
    # ~1.1 km north of DALLAS, and a second point far away
    near = facility.create_facility(db, facility.FacilityType.truck_stop, "Near", 32.7867, -96.7970)
    far = facility.create_facility(db, facility.FacilityType.truck_stop, "Far", 40.7128, -74.0060)

    got = facility.facility_distances(db, [here.id, near.id, far.id], *DALLAS)

    assert round(got[here.id]) == 0
    assert 1000 < got[near.id] < 1300
    assert got[far.id] > 2_000_000
    assert set(got) == {here.id, near.id, far.id}


def test_distances_of_nothing_is_no_query_and_no_rows(db):
    assert facility.facility_distances(db, [], *DALLAS) == {}

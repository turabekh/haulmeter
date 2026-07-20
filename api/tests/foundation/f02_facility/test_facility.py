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
    facility.create_facility(
        db, facility.FacilityType.parking_property, "Lot A", *DALLAS
    )
    near = facility.nearest(db, DALLAS[0], DALLAS[1], radius_m=1000)
    assert len(near) == 1
    far = facility.nearest(db, 40.7128, -74.0060, radius_m=1000)
    assert far == []


def test_radius_query_filters_by_type(db):
    facility.create_facility(db, facility.FacilityType.fuel_station, "Fuel 1", *DALLAS)
    facility.create_facility(
        db, facility.FacilityType.truck_stop, "Stop 1", 32.7770, -96.7975
    )
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
    facility.create_facility(
        db, facility.FacilityType.truck_stop, "Loves Travel Stop", *DALLAS
    )
    dupes = facility.find_duplicate_candidates(db, "Loves Travel Stop", 32.7768, -96.7971)
    assert len(dupes) >= 1


def test_dedup_ignores_far_or_dissimilar(db):
    facility.create_facility(
        db, facility.FacilityType.truck_stop, "Loves Travel Stop", *DALLAS
    )
    far = facility.find_duplicate_candidates(db, "Loves Travel Stop", 40.7128, -74.0060)
    assert far == []


def test_contains_point_by_radius(db):
    fac = facility.create_facility(
        db, facility.FacilityType.truck_stop, "Radius Stop", *DALLAS
    )
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

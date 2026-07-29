"""AI-CONTEXT: E3.3 — branded service areas, and fuel islands that drew a second pin
on their own truck stop. Both were found by reading the deployed map, not by a test.

`highway=services` is how every US chain is tagged and it sat ABOVE the truck-stop
rule, so 309 Pilots, Flying Js, Love's and TAs filed themselves as rest areas — and
NOT ONE facility in the first pull was typed truck_stop from that tag. Because the
Fuel preset is `[fuel_station]`, a Flying J carrying `fuel:diesel=yes` in its own tags
was absent from the one preset built to find it.

The discriminator here is the BRAND, and the negative below is why. `hgv` alone looks
like the obvious test and fails: 135 of the matching rows in the real pull are public
rest areas that admit trucks. Requiring a brand as well leaves 347, every one a chain.
Reordering the rules alone would have fixed nothing — `amenity=truck_stop` appears on
ZERO of the misfiled rows.

The second half reuses E3.2's composite rule exactly as the weighbridge does: 474 of
546 fuel stations stood within 150 m of a destination that already had a pin, so the
map drew one truck stop as two places ~30 m apart, with the PRICE on the island —
which carries the pump's name ("Pilot") rather than the site's ("Flying J Travel
Center"). design-prd §11.1: extra signals render as badges on existing pins, never as
more pins.
"""

from app.foundation.f02_facility import public as facility


def _parse(**tags):
    gj = {
        "type": "FeatureCollection",
        "features": [
            {
                "geometry": {"type": "Point", "coordinates": [-86.47, 40.03]},
                "properties": {"@id": "node/1", **tags},
            }
        ],
    }
    records = facility.parse_osm(gj)
    return records[0] if records else None


# --- the type rule ---
def test_a_branded_service_area_is_a_truck_stop():
    # the real Lebanon, Indiana Flying J, tag for tag
    rec = _parse(
        highway="services",
        brand="Flying J",
        name="Flying J Travel Center",
        hgv="yes",
        **{"fuel:diesel": "yes"},
    )
    assert rec.facility_type == facility.FacilityType.truck_stop


def test_an_unbranded_rest_area_that_admits_trucks_stays_a_rest_area():
    """The negative the whole rule turns on. 135 rows in the real pull look like this
    — "Rest Area", "I-80 EB (trucks Only)" — and hgv alone would have re-typed every
    one of them into a truck stop a driver cannot buy anything at."""
    rec = _parse(highway="rest_area", name="Rest Area", hgv="yes")
    assert rec.facility_type == facility.FacilityType.rest_area


def test_a_branded_service_area_that_does_not_admit_trucks_stays_a_rest_area():
    rec = _parse(highway="services", brand="Costa", name="Costa Coffee Services")
    assert rec.facility_type == facility.FacilityType.rest_area


def test_an_empty_brand_tag_does_not_count_as_branded():
    rec = _parse(highway="services", brand="   ", name="Services", hgv="yes")
    assert rec.facility_type == facility.FacilityType.rest_area


# --- fuel as a service, not only a kind ---
def test_a_site_that_sells_diesel_carries_the_fuel_service():
    rec = _parse(
        highway="services", brand="Love's", name="Love's Travel Stop", hgv="yes",
        **{"fuel:diesel": "yes"},
    )
    assert facility.SERVICE_FUEL in rec.attributes["services"]


def test_a_truck_fuel_island_carries_the_fuel_service():
    rec = _parse(amenity="fuel", name="Fuel Station", hgv="yes")
    assert rec.facility_type == facility.FacilityType.fuel_station
    assert facility.SERVICE_FUEL in rec.attributes["services"]


def test_a_car_only_fuel_station_is_not_ingested_at_all():
    # the hgv gate that keeps every neighbourhood gas station out of the registry
    assert _parse(amenity="fuel", name="Shell") is None


# --- the composite rule (E3.2 reused) ---
def _truck_stop(db, name="Flying J Travel Center", lat=40.0330, lon=-86.4736):
    return facility.ingest_records(
        db,
        [
            facility.StagedRecord(
                source_kind=facility.SourceKind.osm,
                external_ref=f"node/{abs(hash(name)) % 10000}",
                name=name,
                lat=lat,
                lon=lon,
                facility_type=facility.FacilityType.truck_stop,
                attributes={"amenities": ["truck_parking"]},
            )
        ],
        batch_id="host",
    )


def _island(name="Pilot", lat=40.0332, lon=-86.4738):
    gj = {
        "type": "FeatureCollection",
        "features": [
            {
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "@id": f"node/{abs(hash(name)) % 10000 + 5000}",
                    "amenity": "fuel",
                    "name": name,
                    "hgv": "yes",
                    "brand": name,
                    "website": "https://pilotflyingj.com",
                },
            }
        ],
    }
    return facility.parse_osm(gj)


def test_a_fuel_island_inside_a_truck_stop_enriches_it(db):
    """One physical site, one pin. This is the 474-of-546 case."""
    _truck_stop(db)
    stats = facility.ingest_records(db, _island(), batch_id="island")

    assert stats.created == 0
    assert stats.matched == 1
    merged = facility.resolve_canonical(db, next(iter(stats.facility_ids)))
    assert merged.facility_type == facility.FacilityType.truck_stop
    assert facility.SERVICE_FUEL in merged.attributes["services"]


def test_the_island_does_not_rename_the_site_it_stands_in(db):
    """The pump is branded "Pilot" and the site "Flying J Travel Center". Letting the
    tenant's identity through is how 203 truck stops once advertised catscale.com."""
    _truck_stop(db)
    stats = facility.ingest_records(db, _island(), batch_id="island")

    merged = facility.resolve_canonical(db, next(iter(stats.facility_ids)))
    assert merged.name == "Flying J Travel Center"
    assert "pilotflyingj.com" not in str(merged.attributes)


def test_a_standalone_fuel_station_keeps_its_own_pin(db):
    """A fuel station IS a destination when it stands alone — unlike a scale. No
    special case is needed: nothing hosts it, so it earns a pin."""
    stats = facility.ingest_records(db, _island(lat=41.9, lon=-87.9), batch_id="lone")

    assert stats.created == 1
    created = facility.resolve_canonical(db, next(iter(stats.facility_ids)))
    assert created.facility_type == facility.FacilityType.fuel_station


def test_one_fuel_island_cannot_absorb_another(db):
    """`fuel_station` was removed from COLOCATED_HOST_TYPES when it became an amenity
    in its own right. Without that, two unrelated pumps within 150 m — opposite sides
    of an interchange — would collapse into one and the second would stop existing.

    The names are deliberately unalike: similar ones merge through the FUZZY-NAME
    dedupe instead, which is a different rule doing its job, and would let this test
    pass while proving nothing about co-location.
    """
    first = facility.ingest_records(db, _island(name="Marathon Diesel", lat=41.9, lon=-87.9), "a")
    second = facility.ingest_records(
        db, _island(name="Sinclair Truck Pumps", lat=41.9009, lon=-87.9), "b"
    )

    assert first.created == 1
    assert second.created == 1


def test_a_branded_pump_is_not_merged_into_an_unnamed_host(db):
    """Found by dry-running the repair over the real 4,568-row dataset, not by
    reasoning: 35 of the 474 merges were "Flying J #695" and "TA" disappearing into
    "Parking Property" — the placeholder name this code writes for an unnamed OSM
    feature. One pin is the goal, but not at the price of the only real name on the
    site, and adopting the tenant's name is the very thing `_contribution` forbids."""
    facility.ingest_records(
        db,
        [
            facility.StagedRecord(
                source_kind=facility.SourceKind.osm,
                external_ref="node/7001",
                name="Parking Property",
                lat=40.0330,
                lon=-86.4736,
                facility_type=facility.FacilityType.parking_property,
                attributes={},
            )
        ],
        batch_id="unnamed-host",
    )
    stats = facility.ingest_records(db, _island(name="Flying J #695"), batch_id="pump")

    assert stats.created == 1
    kept = facility.resolve_canonical(db, next(iter(stats.facility_ids)))
    assert kept.name == "Flying J #695"


def test_an_unnamed_pump_still_merges_into_an_unnamed_host(db):
    """The guard is about losing a NAME, not about placeholders in general — two
    unnamed features on one site are still one site."""
    facility.ingest_records(
        db,
        [
            facility.StagedRecord(
                source_kind=facility.SourceKind.osm,
                external_ref="node/7002",
                name="Parking Property",
                lat=40.0330,
                lon=-86.4736,
                facility_type=facility.FacilityType.parking_property,
                attributes={},
            )
        ],
        batch_id="unnamed-host",
    )
    stats = facility.ingest_records(db, _island(name="Fuel Station"), batch_id="pump")

    assert stats.created == 0
    assert stats.matched == 1


def test_re_ingesting_the_same_island_is_idempotent(db):
    _truck_stop(db)
    facility.ingest_records(db, _island(), batch_id="one")
    second = facility.ingest_records(db, _island(), batch_id="two")

    assert second.created == 0

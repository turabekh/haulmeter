"""AI-CONTEXT: E3.2 service-center granularity (PRD extension §E3, owner decision
Q12 = ATTRIBUTES, not new facility kinds).

The rule these tests defend: a wash / tire bay / repair yard rides as a `services`
attribute, so a facility can be several things at once. A truck stop with a tire
bay keeps kind=truck_stop AND gains "tire" — expressing that with kinds would force
a lossy choice, and design-prd §11.1 says extra signals become badges on existing
pins, never more pins. Fixtures drive this; live pulls stay in make targets.
"""

import json
from pathlib import Path

from app.foundation.f02_facility import public as facility

FIX = Path(__file__).parents[2] / "fixtures" / "ingest"


def _load(name: str):
    return json.loads((FIX / name).read_text())


def _records():
    return {r.external_ref: r for r in facility.parse_osm(_load("osm_services.geojson"))}


def test_tyre_shop_maps_to_repair_with_a_tire_service():
    rec = _records()["node/901"]
    assert rec.facility_type == facility.FacilityType.repair
    assert rec.attributes["services"] == [facility.SERVICE_TIRE]


def test_car_wash_maps_to_repair_with_a_wash_service():
    rec = _records()["node/902"]
    assert rec.facility_type == facility.FacilityType.repair
    assert rec.attributes["services"] == [facility.SERVICE_WASH]


def test_a_site_carries_every_service_it_offers_not_the_first():
    # a repair yard that also does tires and mobile callouts is all three
    rec = _records()["node/903"]
    assert rec.facility_type == facility.FacilityType.repair
    assert set(rec.attributes["services"]) == {
        facility.SERVICE_TIRE,
        facility.SERVICE_REPAIR,
        facility.SERVICE_MOBILE_REPAIR,
    }


def test_a_truck_stop_with_a_tire_bay_keeps_both_facts():
    # THE case for attributes over kinds: the kind stays truck_stop (it is one),
    # and the tire service is still discoverable. A `tire_shop` kind would erase one.
    rec = _records()["node/904"]
    assert rec.facility_type == facility.FacilityType.truck_stop
    assert rec.attributes["services"] == [facility.SERVICE_TIRE]


def test_non_truck_service_poi_is_not_ingested():
    # a neighbourhood car wash with no HGV access is not a truck facility — without
    # this gate the registry floods with every car wash in the state
    assert "node/905" not in _records()
    assert "node/909" not in _records()  # and every car garage: 1,347 of them in WI alone


# --- A5: does this shop serve TRUCKS? (measured on the full Wisconsin extract) ---
def test_a_truck_shop_is_ingested_without_any_access_tag():
    """The measurement that rewrote this rule: of 2,638 Wisconsin features carrying a
    service tag, ZERO carry `hgv`/`access=hgv`/`truck=yes`. Nobody tags access on a
    repair shop. Gating on `_osm_hgv` — as the type rule did — admitted none of them,
    so the registry held 12 repair facilities across nine states.

    "Diesel Doctors" is a real Wisconsin row, and like two thirds of the genuine finds
    it is a plain `shop=car_repair` whose only truck signal is its name."""
    rec = _records()["node/906"]
    assert rec.facility_type == facility.FacilityType.repair
    assert rec.attributes["services"] == [facility.SERVICE_REPAIR]


def test_an_explicit_truck_tag_needs_no_truck_in_the_name():
    # "Pomp's Tire Service" is a commercial truck tire chain whose name says nothing
    # about trucks. `service:vehicle:truck_repair` does.
    rec = _records()["node/908"]
    assert rec.facility_type == facility.FacilityType.repair
    assert set(rec.attributes["services"]) == {facility.SERVICE_TIRE, facility.SERVICE_REPAIR}


def test_a_truck_named_wash_is_a_truck_facility():
    rec = _records()["node/910"]
    assert rec.facility_type == facility.FacilityType.repair
    assert rec.attributes["services"] == [facility.SERVICE_WASH]


def test_fleet_in_a_name_does_not_make_a_truck_shop():
    """`fleet` reads like the strongest possible term and is the weakest one measured:
    13 of its 14 Wisconsin matches are "Fleet Farm", a regional retail chain. Its CAR
    WASH would have entered the registry as a truck repair facility. A term earns its
    place on the data or it does not ship."""
    assert "node/907" not in _records()


def test_a_repair_bay_inside_a_truck_stop_enriches_it_instead_of_pinning_itself(db):
    """A5 requirement 2 / design-prd §11.1: extra signals become badges on existing
    pins, never more pins. Measured on the Wisconsin extract — 10 of the 65 repair
    records stand inside a destination facility, and they are exactly the ones a
    driver already knows about: TA Truck Service, Love's Truck Care, Bosselman's Boss
    Shop. Three TA service bays as three separate pins beside three TA truck stops is
    the second-pin defect E3.1 and E3.3 each had to fix in their turn."""
    # the adapter is what has to know this — a hand-set flag here would test the
    # pipeline and leave the rule that sets it unexercised
    bay_rec = _records()["node/906"]
    assert bay_rec.colocated_amenity, "a repair shop must be able to merge into its host"

    host = facility.StagedRecord(
        source_kind=facility.SourceKind.osm,
        external_ref="node/800",
        name="Madison Travel Center",  # deliberately unlike the bay's name, so the
        lat=43.0700,  # fuzzy-name path cannot be what merges them
        lon=-89.4000,
        facility_type=facility.FacilityType.truck_stop,
    )
    bay = facility.StagedRecord(
        source_kind=facility.SourceKind.osm,
        external_ref="node/801",
        name="TA Truck Service",
        lat=43.0701,
        lon=-89.4001,
        facility_type=facility.FacilityType.repair,
        attributes={"services": [facility.SERVICE_REPAIR]},
        colocated_amenity=bay_rec.colocated_amenity,
    )
    facility.ingest_records(db, [host], batch_id="svc-host")
    fac, outcome = facility.upsert_record(db, bay, batch_id="svc-bay")

    assert outcome == "matched", "the bay must not become a second pin"
    assert fac.facility_type == facility.FacilityType.truck_stop
    assert fac.name == "Madison Travel Center", "a bay never renames the site it sits in"
    assert facility.SERVICE_REPAIR in fac.attributes["services"]


def test_a_standalone_repair_shop_keeps_its_own_pin(db):
    # the other half of the same rule: with no host within reach it IS the destination
    alone = facility.StagedRecord(
        source_kind=facility.SourceKind.osm,
        external_ref="node/802",
        name="Portage Diesel Repair",
        lat=44.5000,
        lon=-89.5000,
        facility_type=facility.FacilityType.repair,
        attributes={"services": [facility.SERVICE_REPAIR]},
        colocated_amenity=_records()["node/906"].colocated_amenity,
    )
    fac, outcome = facility.upsert_record(db, alone, batch_id="svc-alone")
    assert outcome == "created"
    assert fac.facility_type == facility.FacilityType.repair


def test_one_repair_shop_never_absorbs_another(db):
    """Measured: 4 of the 29 within-radius repair pairs in Wisconsin are DIFFERENT
    businesses — "TA Truck Service" and "Lakeside International Trucks" sit 80 m apart
    at one interchange. A repair that could host a repair would silently delete one of
    them. This is why `repair` leaves COLOCATED_HOST_TYPES in the same change that
    makes it a co-located amenity — the same exclusion `fuel_station` already carries
    so one pump cannot host another."""
    first = facility.StagedRecord(
        source_kind=facility.SourceKind.osm,
        external_ref="node/803",
        name="Lakeside International Trucks",
        lat=42.9000,
        lon=-87.9000,
        facility_type=facility.FacilityType.repair,
        attributes={"services": [facility.SERVICE_REPAIR]},
        colocated_amenity=True,
    )
    second = facility.StagedRecord(
        source_kind=facility.SourceKind.osm,
        external_ref="node/804",
        name="Kenworth of Milwaukee",
        lat=42.90072,  # ~80 m away, the measured real-world gap
        lon=-87.9000,
        facility_type=facility.FacilityType.repair,
        attributes={"services": [facility.SERVICE_REPAIR]},
        colocated_amenity=True,
    )
    facility.ingest_records(db, [first], batch_id="svc-a")
    fac, outcome = facility.upsert_record(db, second, batch_id="svc-b")
    assert outcome == "created", "two distinct shops 80 m apart are two places"
    assert fac.name == "Kenworth of Milwaukee"


def test_a_placeholder_name_is_never_adopted_whatever_kind_wrote_it(db):
    """Found by reading the ingested rows, not by reasoning about them: a nameless
    parking lot beside a nameless repair shop came out of the pull CALLED "Repair".

    The adoption guard excluded exactly one placeholder — `placeholder_name(
    fuel_station)` — because fuel was the only co-located kind when it was written.
    Every other kind's placeholder passed it, and this predates A5: 18 truck stops and
    a rest area in the live registry are named "Weigh Station" today, plus a
    weigh station named "Scale". The rule was always "do not adopt a name this code
    invented"; it just named one of them.

    A placeholder is not a name. Swapping "Parking Property" for "Repair" trades one
    invented label for a worse one — it tells a driver the lot IS a repair shop."""
    from app.foundation.f02_facility.domain import service as svc
    from app.foundation.f02_facility.domain.ingest.adapters import placeholder_name

    for ftype in facility.FacilityType:
        host = facility.Facility(
            name=placeholder_name(facility.FacilityType.parking_property),
            facility_type=facility.FacilityType.parking_property,
        )
        assert not svc.host_should_adopt_name(host, placeholder_name(ftype)), (
            f"adopted the placeholder this code writes for {ftype.value}"
        )
        assert svc.host_should_adopt_name(host, "Ottery Brothers Truck Wash")


def test_truck_relevance_is_one_definition():
    # the same question the type rule asks, asked directly — so a caller cannot invent
    # a second answer to it (the §23 entry 94 regression, one layer down)
    from app.foundation.f02_facility.domain.ingest import adapters

    assert adapters.osm_serves_trucks({"name": "Portage Diesel Repair"})
    assert adapters.osm_serves_trucks({"shop": "truck_repair"})
    assert adapters.osm_serves_trucks({"hgv": "designated"})
    assert not adapters.osm_serves_trucks({"name": "Mill's Fleet Farm"})
    assert not adapters.osm_serves_trucks({"shop": "car_repair", "name": "Sunshine Auto"})


def test_facilities_without_services_carry_no_services_key():
    # no empty-list noise on the 4000+ facilities that aren't service centers.
    #
    # E3.3 narrowed what this can assert. It once read "no record in this fixture has
    # a services key", which was true until a fuel island began carrying SERVICE_FUEL
    # — a deliberate change, not a regression, since that is what lets the price badge
    # survive the merge into its host. The INVARIANT it was written to protect is that
    # the key is absent rather than empty, so it now says that instead of restating a
    # fixture's contents.
    plain = facility.parse_osm(_load("osm_filtered.geojson"))
    assert plain
    assert all(r.attributes.get("services", ["x"]) != [] for r in plain)
    assert any("services" not in r.attributes for r in plain)


def test_services_merge_by_union_across_sources(db):
    # an OSM extract knowing "tire" and an admin edit knowing "towing" describe the
    # SAME yard. Overwrite-by-priority would let the higher-priority source erase the
    # other's knowledge, so `services` merges by union (a deliberate exception,
    # in the same spirit as the NTAD-wins-capacity rule).
    osm = facility.StagedRecord(
        source_kind=facility.SourceKind.osm,
        external_ref="node/700",
        name="Joplin Truck Service",
        lat=37.084,
        lon=-94.513,
        facility_type=facility.FacilityType.repair,
        attributes={"services": [facility.SERVICE_TIRE]},
    )
    admin = facility.StagedRecord(
        source_kind=facility.SourceKind.admin,
        external_ref="admin/700",
        name="Joplin Truck Service",
        lat=37.084,
        lon=-94.513,
        facility_type=facility.FacilityType.repair,
        attributes={"services": [facility.SERVICE_TOWING]},
    )
    facility.ingest_records(db, [osm], batch_id="osm-svc")
    fac, _ = facility.upsert_record(db, admin, batch_id="admin-svc")

    assert set(fac.attributes["services"]) == {facility.SERVICE_TIRE, facility.SERVICE_TOWING}


def test_non_list_attributes_still_overwrite_by_priority(db):
    # the union rule is scoped to `services` only — everything else keeps the
    # established highest-priority-wins behavior
    assert "services" in facility.UNION_KEYS
    assert "capacity" not in facility.UNION_KEYS
    assert "amenities" not in facility.UNION_KEYS

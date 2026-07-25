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


def test_facilities_without_services_carry_no_services_key():
    # no empty-list noise on the 4000+ facilities that aren't service centers
    plain = {r.external_ref: r for r in facility.parse_osm(_load("osm_filtered.geojson"))}
    assert all("services" not in r.attributes for r in plain.values())


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

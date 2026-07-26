"""AI-CONTEXT: E3.1 weigh-station ingestion (extension PRD §E3.1, trucker request #4).

The tag map is taken from REAL OSM usage rather than the documentation's
aspirations — checked against taginfo at plan time:

    amenity=weighbridge      12,178 uses   -> the tag that actually carries these
    amenity=weigh_station        38 uses   -> marginal but real
    highway=weigh_station         0 uses   -> DOES NOT EXIST; a rule would be dead code
    amenity=vehicle_inspection 13,344 uses -> deliberately NOT mapped

That last one is the important negative: `vehicle_inspection` is MOT/state safety
inspection and has nothing to do with weighing. It outnumbers real weighbridges, so
mapping it would have more than doubled the layer with pins a driver never stops at.

The composite rule from E3.2 does the other half of the work for free: a weighbridge
mapped inside an existing truck stop must ENRICH it, not plant a second pin on top.
"""

import json
from pathlib import Path

from app.foundation.f02_facility import public as facility

FIX = Path(__file__).parents[2] / "fixtures" / "ingest"


def _load(name: str):
    return json.loads((FIX / name).read_text())


def _records():
    return {r.external_ref: r for r in facility.parse_osm(_load("osm_weigh.geojson"))}


# --- the tag map ---
def test_a_weighbridge_becomes_a_public_weigh_station():
    rec = _records()["node/801"]
    assert rec.facility_type == facility.FacilityType.weigh_station
    assert rec.attributes["services"] == [facility.SERVICE_SCALE]


def test_the_marginal_weigh_station_tag_is_accepted_too():
    # 38 uses is small but real, and accepting it costs one tuple entry
    assert _records()["node/802"].facility_type == facility.FacilityType.weigh_station


def test_a_branded_commercial_scale_is_a_different_kind():
    # a CAT-scale is a service a driver PAYS for; an enforcement scale is a stop they
    # cannot skip. Rendering both as the same thing would mislead about both.
    rec = _records()["node/803"]
    assert rec.facility_type == facility.FacilityType.scale


def test_vehicle_inspection_is_never_mapped_as_a_weigh_station():
    # the negative that matters most: this tag outnumbers real weighbridges, and
    # mapping it would fill the layer with pins nobody stops at
    assert "node/804" not in _records()


def test_a_weighbridge_is_not_hgv_gated():
    # an enforcement scale exists FOR heavy vehicles whether or not a mapper tagged
    # access; gating on hgv would drop most of them
    gj = {
        "type": "FeatureCollection",
        "features": [
            {
                "geometry": {"type": "Point", "coordinates": [-89.0, 43.0]},
                "properties": {"@id": "n/1", "amenity": "weighbridge", "name": "Scale"},
            }
        ],
    }
    assert facility.parse_osm(gj)[0].facility_type == facility.FacilityType.weigh_station


# --- the composite rule (E3.2 reused) ---
def test_a_weighbridge_at_an_existing_truck_stop_enriches_it(db):
    """The rule that keeps the map honest: one physical site, one pin. A scale mapped
    inside a truck stop is a FACT ABOUT that truck stop, not a second facility."""
    stop = facility.StagedRecord(
        source_kind=facility.SourceKind.osm,
        external_ref="node/900",
        name="Rest Area I-94 EB",
        lat=43.0700,
        lon=-89.4000,
        facility_type=facility.FacilityType.rest_area,
        attributes={"amenities": ["truck_parking"]},
    )
    facility.ingest_records(db, [stop], batch_id="stop")

    weigh = [
        r for r in facility.parse_osm(_load("osm_weigh.geojson")) if r.external_ref == "node/805"
    ]
    stats = facility.ingest_records(db, weigh, batch_id="weigh")

    # matched into the existing facility rather than creating a new one
    assert stats.created == 0
    assert stats.matched == 1
    merged = facility.resolve_canonical(db, next(iter(stats.facility_ids)))
    assert merged.facility_type == facility.FacilityType.rest_area  # kind is unchanged
    assert facility.SERVICE_SCALE in merged.attributes["services"]  # the fact is kept


def test_a_standalone_weighbridge_creates_its_own_facility(db):
    weigh = [
        r for r in facility.parse_osm(_load("osm_weigh.geojson")) if r.external_ref == "node/801"
    ]
    stats = facility.ingest_records(db, weigh, batch_id="lone")

    assert stats.created == 1
    created = facility.resolve_canonical(db, next(iter(stats.facility_ids)))
    assert created.facility_type == facility.FacilityType.weigh_station


def test_re_ingesting_the_same_scale_is_idempotent(db):
    weigh = [
        r for r in facility.parse_osm(_load("osm_weigh.geojson")) if r.external_ref == "node/801"
    ]
    facility.ingest_records(db, weigh, batch_id="one")
    second = facility.ingest_records(db, weigh, batch_id="two")

    assert second.created == 0  # the same scale twice is still one scale


# --- co-located amenities (the case the first real pull exposed) ---
#
# The fuzzy-name dedupe above only works when the two records SAY the same thing. The
# first four-state pull produced 253 commercial scales, 239 of them within 150 m of a
# facility that already had a pin — and not one merged, because "Cat Scale" resembles
# "Pilot" not at all. These tests cover that case with the real tag shape.
def _one(records, ref):
    return [r for r in records if r.external_ref == ref]


def _pilot(db, lat=43.2003, lon=-89.6000, name="Pilot Travel Center"):
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
                attributes={"amenities": ["showers"], "osm_tags": {"name": name}},
            )
        ],
        batch_id="host",
    )


def test_a_branded_scale_is_marked_colocated_and_a_public_one_is_not():
    recs = {r.external_ref: r for r in facility.parse_osm(_load("osm_weigh.geojson"))}
    assert recs["node/806"].colocated_amenity is True  # CAT Scale — an amenity
    assert recs["node/801"].colocated_amenity is False  # enforcement — a destination


def test_a_weighbridge_outranks_the_generic_service_rule(db):
    """Found in the first real pull: making a weighbridge a SERVICE also made it match
    the catch-all "some service + hgv -> repair" rule that sat above it, so a CAT scale
    tagged hgv=designated filed itself as a REPAIR SHOP. A specific tag outranks a
    catch-all, and the co-located flag is derived from the resolved type so the two
    can never disagree."""
    gj = {
        "type": "FeatureCollection",
        "features": [
            {
                "geometry": {"type": "Point", "coordinates": [-88.4633, 43.7533]},
                "properties": {
                    "@id": "node/810",
                    "amenity": "weighbridge",
                    "brand": "CAT Scale",
                    "name": "CAT Scale",
                    "hgv": "designated",
                    "highway": "service",
                },
            }
        ],
    }
    rec = facility.parse_osm(gj)[0]
    assert rec.facility_type == facility.FacilityType.scale  # not repair
    assert rec.colocated_amenity is True


def test_a_cat_scale_merges_into_the_truck_stop_it_stands_in(db):
    """The case the fuzzy-name matcher cannot see: nothing about "CAT Scale" resembles
    "Pilot Travel Center", yet they are one place and must be one pin (§11.1)."""
    _pilot(db)
    scale = _one(facility.parse_osm(_load("osm_weigh.geojson")), "node/806")
    stats = facility.ingest_records(db, scale, batch_id="scale")

    assert stats.created == 0
    assert stats.matched == 1
    host = facility.resolve_canonical(db, next(iter(stats.facility_ids)))
    assert host.name == "Pilot Travel Center"
    assert host.facility_type == facility.FacilityType.truck_stop
    assert facility.SERVICE_SCALE in host.attributes["services"]


def test_the_scale_contributes_its_service_and_nothing_else(db):
    """A tenant must not overwrite its host's identity. The scale knows one thing
    about the site — that you can weigh there — and its own name, phone and website
    describe the scale, not the truck stop."""
    _pilot(db)
    scale = _one(facility.parse_osm(_load("osm_weigh.geojson")), "node/806")
    stats = facility.ingest_records(db, scale, batch_id="scale")

    host = facility.resolve_canonical(db, next(iter(stats.facility_ids)))
    assert host.attributes["osm_tags"]["name"] == "Pilot Travel Center"
    assert "catscale.com" not in str(host.attributes)
    assert host.attributes["amenities"] == ["showers"]


def test_a_standalone_cat_scale_still_earns_its_own_pin(db):
    # 14 of the 253 stood alone; an independent plaza we have not ingested is a real
    # place, and dropping its scale because no host was found would lose the fact
    scale = _one(facility.parse_osm(_load("osm_weigh.geojson")), "node/807")
    stats = facility.ingest_records(db, scale, batch_id="lone")

    assert stats.created == 1
    created = facility.resolve_canonical(db, next(iter(stats.facility_ids)))
    assert created.facility_type == facility.FacilityType.scale


def test_a_public_weigh_station_beside_a_rest_area_stays_its_own_place(db):
    """The asymmetry that makes this safe: an enforcement scale is a DESTINATION.
    Many sit next to a rest area, and folding one into the other would lose it."""
    _pilot(db, lat=43.1203, lon=-89.5010, name="Rest Area I-90")
    weigh = _one(facility.parse_osm(_load("osm_weigh.geojson")), "node/801")
    stats = facility.ingest_records(db, weigh, batch_id="weigh")

    assert stats.created == 1
    assert (
        facility.resolve_canonical(db, next(iter(stats.facility_ids))).facility_type
        == facility.FacilityType.weigh_station
    )


def test_proximity_alone_never_merges_an_ordinary_facility(db):
    """The rule that keeps this from becoming a general proximity merge: two truck
    stops across the road from each other are two businesses, and only a record the
    ADAPTER marked co-located may take the proximity path."""
    _pilot(db, name="Pilot Travel Center")
    stats = _pilot(db, lat=43.2004, lon=-89.6001, name="Loves Travel Stop")

    assert stats.created == 1  # ~15 m apart and still two places


def test_an_amenity_is_never_a_valid_host(db):
    """Only a DESTINATION may host a co-located amenity, so amenities cannot chain
    into one another — a scale is not somewhere another scale stands 'inside'."""
    lone = _one(facility.parse_osm(_load("osm_weigh.geojson")), "node/807")
    facility.ingest_records(db, lone, batch_id="one")

    assert facility.colocated_host(db, 44.5001, -90.5000) is None

    _pilot(db, lat=44.5002, lon=-90.5000, name="Independent Truck Plaza")
    host = facility.colocated_host(db, 44.5001, -90.5000)
    assert host is not None and host.name == "Independent Truck Plaza"


def test_a_host_must_be_within_the_measured_radius(db):
    _pilot(db, lat=43.2000, lon=-89.6000)
    assert facility.colocated_host(db, 43.2010, -89.6000) is not None  # ~111 m
    assert facility.colocated_host(db, 43.2030, -89.6000) is None  # ~333 m — next site


def test_merging_a_cat_scale_is_idempotent(db):
    _pilot(db)
    scale = _one(facility.parse_osm(_load("osm_weigh.geojson")), "node/806")
    facility.ingest_records(db, scale, batch_id="one")
    second = facility.ingest_records(db, scale, batch_id="two")

    assert second.created == 0
    assert second.matched == 1


def test_re_ingesting_never_dresses_the_host_in_its_tenants_identity(db):
    """The regression that got through the first time. The re-ingest path replaces a
    source's attributes WHOLESALE, so narrowing only at merge time was undone by the
    very next pull — and 203 truck stops briefly advertised catscale.com."""
    _pilot(db)
    scale = _one(facility.parse_osm(_load("osm_weigh.geojson")), "node/806")
    facility.ingest_records(db, scale, batch_id="one")
    stats = facility.ingest_records(db, scale, batch_id="two")  # the second pull

    host = facility.resolve_canonical(db, next(iter(stats.facility_ids)))
    assert host.name == "Pilot Travel Center"
    assert "catscale.com" not in str(host.attributes)
    assert host.attributes["osm_tags"]["name"] == "Pilot Travel Center"
    assert facility.SERVICE_SCALE in host.attributes["services"]  # the fact still lands


def test_a_standalone_scale_keeps_everything_it_knows_across_re_ingest(db):
    # narrowing applies to a TENANT, not to a scale that is a place in its own right
    scale = _one(facility.parse_osm(_load("osm_weigh.geojson")), "node/807")
    facility.ingest_records(db, scale, batch_id="one")
    stats = facility.ingest_records(db, scale, batch_id="two")

    lone = facility.resolve_canonical(db, next(iter(stats.facility_ids)))
    assert lone.attributes["osm_tags"]["brand"] == "CAT Scale"

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

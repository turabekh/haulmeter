"""AI-CONTEXT: F2 real-POI ingestion (PRD §12). Adapters parse committed fixtures
(no network in CI); the pipeline stages -> dedupes -> upserts canonically with
provenance + confidence. Proves cross-source dedupe (DoD d), idempotent re-runs,
NTAD pagination edge (condition B), and TPIMS Low/numeric handling (condition A).
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.foundation.f02_facility import public as facility

FIX = Path(__file__).parents[2] / "fixtures" / "ingest"


def _load(name: str):
    return json.loads((FIX / name).read_text())


# --- Name normalization (condition C — display trust) ---
def test_name_normalization_preserves_highways_directions_acronyms():
    from app.foundation.f02_facility.domain.ingest.normalize import normalize_name

    assert normalize_name("REST AREA I-94 EB") == "Rest Area I-94 EB"
    assert normalize_name("NHS WELCOME CENTER") == "NHS Welcome Center"  # acronym kept
    assert normalize_name("PILOT TRAVEL CENTER US41") == "Pilot Travel Center US-41"
    assert normalize_name("") == ""


# --- Adapters ---
def test_parse_ntad_normalizes_name_and_keeps_capacity():
    recs = facility.parse_ntad(_load("ntad_page.geojson"))
    by_ref = {r.external_ref: r for r in recs}
    rest = by_ref["5001"]
    assert rest.name == "Rest Area I-94 EB"  # ALLCAPS -> title-case, highway preserved
    assert rest.attributes["capacity"] == 60
    assert rest.facility_type == facility.FacilityType.rest_area
    assert by_ref["5002"].facility_type == facility.FacilityType.truck_stop


def test_ntad_pagination_stops_on_short_page():
    calls = []

    def get_page(base, offset, size):
        calls.append(offset)
        if offset == 0:
            return {"features": [{}, {}], "exceededTransferLimit": False}  # full
        return {"features": [{}], "exceededTransferLimit": False}  # short -> stop

    pages = list(facility.iter_ntad_pages("http://x", 2, get_page=get_page))
    assert len(pages) == 2 and calls == [0, 2]


def test_ntad_pagination_respects_exceeded_transfer_limit():
    def get_page(base, offset, size):
        if offset == 0:
            return {"features": [{}], "exceededTransferLimit": True}  # short but MORE
        return {"features": [], "exceededTransferLimit": False}

    pages = list(facility.iter_ntad_pages("http://x", 2, get_page=get_page))
    assert len(pages) == 2  # kept going despite the short first page


def test_tpims_dynamic_low_is_a_category_not_an_int():
    statuses = {s.site_id: s for s in facility.parse_tpims_dynamic(_load("tpims_dynamic.json"))}
    low = statuses["WI00041IS0031900ERSTARE02"]
    assert low.available == facility.LOW  # never int-parsed
    assert facility.derive_parking_status(low) == "some"
    numeric = statuses["WI00094IS0024700ERSTARE01"]
    assert numeric.available == 12
    assert facility.derive_parking_status(numeric) == "some"  # 12 of 55 -> low-ish


def test_tpims_unknown_and_trend_hardening_from_real_il_rows():
    # real IL feeds emit reportedAvailable/trend "Unknown" (not in the V2.2 spec)
    statuses = {s.site_id: s for s in facility.parse_tpims_dynamic(_load("tpims_il_dynamic.json"))}
    unknown = statuses["IL00074IE015600037"]
    assert unknown.available is None  # "Unknown" -> no reading, never int-parsed
    assert unknown.trend is None  # trend "Unknown" -> null
    assert facility.has_usable_reading(unknown) is False  # open + no reading -> no belief

    trusted_unknown = statuses["IL00074IE011400005"]  # Unknown but trustData=true
    assert facility.has_usable_reading(trusted_unknown) is False  # no belief, regardless of trust

    null_open = statuses["IL00055IS010400024"]
    assert null_open.open is True  # open=null tolerated (defaults open)

    low = statuses["IL00074IE006200001"]
    assert low.available == facility.LOW and facility.derive_parking_status(low) == "some"


def test_a_missing_feed_timestamp_is_not_a_fresh_reading():
    # audit F-32: `_parse_ts` returned `datetime.now(UTC)`, so a record with no
    # timeStamp reached the driver as `0m · IDOT` — a fabricated age on a reading
    # the A3 feed badge is about to make MORE trusted.
    statuses = facility.parse_tpims_dynamic(
        [
            {"siteId": "NO-TS", "reportedAvailable": "12", "capacity": 55, "open": True},
            {
                "siteId": "BAD-TS",
                "timeStamp": "not-a-timestamp",
                "reportedAvailable": "12",
                "capacity": 55,
                "open": True,
            },
            {
                "siteId": "GOOD-TS",
                "timeStamp": "2026-08-07T12:00:00Z",
                "reportedAvailable": "12",
                "capacity": 55,
                "open": True,
            },
        ]
    )
    by_id = {s.site_id: s for s in statuses}
    assert by_id["NO-TS"].reported_at is None
    assert by_id["BAD-TS"].reported_at is None
    assert by_id["GOOD-TS"].reported_at is not None

    # the availability is perfectly good on all three; it is the AGE that is unknown,
    # and a belief needs both
    assert facility.has_usable_reading(by_id["NO-TS"]) is False
    assert facility.has_usable_reading(by_id["BAD-TS"]) is False
    assert facility.has_usable_reading(by_id["GOOD-TS"]) is True


def test_an_unknown_age_closed_station_is_also_dropped():
    # "closed" is a usable reading only when its age is known — an unknown-age CLOSED
    # is what sends a driver past a lot that reopened hours ago
    (closed,) = facility.parse_tpims_dynamic(
        [{"siteId": "CLOSED-NO-TS", "reportedAvailable": "Unknown", "open": False}]
    )
    assert closed.reported_at is None
    assert facility.has_usable_reading(closed) is False


def test_deriving_a_status_without_a_reading_fails_loud():
    # audit F-33: this branch returned "some" and called it conservative. "some" is a
    # positive claim that spots exist, derived from no reading.
    bogus = facility.DynamicStatus(
        site_id="NO-READING",
        reported_at=datetime(2026, 8, 7, 12, 0, tzinfo=UTC),
        available="not-a-category",
        capacity=55,
        trend=None,
        open=True,
        trust_data=True,
    )
    assert facility.has_usable_reading(bogus) is True  # the gate cannot see this one
    with pytest.raises(ValueError, match="has_usable_reading"):
        facility.derive_parking_status(bogus)


def test_osm_polygon_uses_centroid():
    recs = {r.external_ref: r for r in facility.parse_osm(_load("osm_filtered.geojson"))}
    lot = recs["way/222"]
    assert lot.facility_type == facility.FacilityType.parking_property
    assert 43.79 < lot.lat < 43.81 and -91.242 < lot.lon < -91.240  # centroid of the ring


def test_osm_skips_non_truck_fuel_and_parking():
    # a plain gas station / car park is NOT ingested — only HGV-admitting POIs, else
    # the layer floods with every parking lot in the state (rest areas always qualify).
    gj = {
        "type": "FeatureCollection",
        "features": [
            {
                "geometry": {"type": "Point", "coordinates": [-89.0, 43.0]},
                "properties": {"@id": "n/1", "amenity": "fuel", "name": "Car Gas"},
            },
            {
                "geometry": {"type": "Point", "coordinates": [-89.1, 43.1]},
                "properties": {"@id": "n/2", "amenity": "parking", "name": "Mall Lot"},
            },
            {
                "geometry": {"type": "Point", "coordinates": [-89.2, 43.2]},
                "properties": {"@id": "n/3", "amenity": "fuel", "hgv": "yes", "name": "Truck Fuel"},
            },
            {
                "geometry": {"type": "Point", "coordinates": [-89.3, 43.3]},
                "properties": {"@id": "n/4", "highway": "rest_area", "name": "Rest Area"},
            },
        ],
    }
    refs = {r.external_ref for r in facility.parse_osm(gj)}
    assert refs == {"n/3", "n/4"}  # truck fuel + rest area kept; car gas + mall lot dropped


def test_chain_adapter_is_a_stub():
    import pytest

    with pytest.raises(NotImplementedError):
        facility.ChainLocatorAdapter().parse(_load("chain_sample.json"))


# --- Pipeline ---
def test_cross_source_dedupe_merges_the_same_physical_site(db):
    # DoD (d): the SAME Wisconsin rest area from NTAD + TPIMS + OSM must collapse to
    # ONE canonical facility with THREE provenance rows, NTAD winning capacity.
    ntad = [r for r in facility.parse_ntad(_load("ntad_page.geojson")) if r.external_ref == "5001"]
    tpims = facility.parse_tpims_static(_load("tpims_static.json"))
    osm = [
        r for r in facility.parse_osm(_load("osm_filtered.geojson")) if r.external_ref == "node/111"
    ]

    facility.ingest_records(db, ntad, batch_id="ntad-1")
    facility.ingest_records(db, tpims, batch_id="tpims-1")
    facility.ingest_records(db, osm, batch_id="osm-1")

    matches = facility.find_duplicate_candidates(db, "Rest Area I-94 EB", 43.0700, -89.4000)
    canonicals = [f for f in matches if f.status != facility.FacilityStatus.merged]
    assert len(canonicals) == 1  # one physical site
    fac = canonicals[0]
    kinds = {s.source_kind for s in fac.sources}
    assert kinds == {facility.SourceKind.ntad, facility.SourceKind.tpims, facility.SourceKind.osm}
    assert fac.attributes["capacity"] == 60  # NTAD (60) beats TPIMS (55)
    assert fac.confidence > 0.8  # three independent sources


def test_dev_seed_facilities_are_excluded_from_dedupe(db):
    # DEV_SEED field-test facilities show on the map but must never be a merge target
    # for real ingest — otherwise NTAD/OSM data would collapse into throwaway records.
    dev = facility.create_facility(
        db,
        facility.FacilityType.rest_area,
        "DEV — Rest Area I-94 EB",
        43.0700,
        -89.4000,
        is_dev=True,
    )
    real = facility.create_facility(
        db, facility.FacilityType.rest_area, "Rest Area I-94 EB", 43.0701, -89.4001
    )
    matches = facility.find_duplicate_candidates(db, "Rest Area I-94 EB", 43.0700, -89.4000)
    ids = {f.id for f in matches}
    assert real.id in ids  # the real neighbor is a candidate
    assert dev.id not in ids  # the DEV facility is never one


def test_ingest_is_idempotent(db):
    page = facility.parse_ntad(_load("ntad_page.geojson"))
    first = facility.ingest_records(db, page, batch_id="run-1")
    again = facility.ingest_records(db, page, batch_id="run-2")
    # same input twice -> same facilities, no new rows on the re-run
    assert first.created == 2
    assert again.created == 0
    assert len(first.facility_ids) == len(again.facility_ids) == 2

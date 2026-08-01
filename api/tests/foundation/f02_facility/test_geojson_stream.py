"""AI-CONTEXT: A9 §4's "handle volume before it arrives", found before it arrived.

`read_geojson_file` is `json.load` — the whole file into memory at once. That is fine
for a state (Texas's 200 MB geojson parsed on a laptop with 7.6 GB) and it is NOT fine
for a REGION, which is what A9 §2 says to batch by: us-midwest is a 2.4 GB pbf, and the
deployed box is an e2-medium with **3 GB total and about 2 GB available**. Python's json
holds roughly five to ten times the file size in objects, so the regional ingest would
have been killed on the box rather than failing with anything readable.

`osmium export` writes ONE FEATURE PER LINE, so the file streams. The committed fixtures
are pretty-printed, so both shapes have to work — and the fallback matters more than the
fast path: a reader that quietly returned nothing for a fixture would make every ingest
test vacuous at once.
"""

import json
from pathlib import Path

from app.foundation.f02_facility import public as facility

FIX = Path(__file__).parents[2] / "fixtures" / "ingest"


def test_it_streams_the_one_feature_per_line_form_osmium_writes(tmp_path):
    src = tmp_path / "region.geojson"
    src.write_text(
        '{"type":"FeatureCollection","features":[\n'
        '{"type":"Feature","geometry":{"type":"Point","coordinates":[-89.4,43.07]},'
        '"properties":{"@id":"node/1","shop":"truck_repair","name":"A Truck Repair"}},\n'
        '{"type":"Feature","geometry":{"type":"Point","coordinates":[-89.5,43.08]},'
        '"properties":{"@id":"node/2","shop":"tyres","name":"B Truck Tire"}}\n'
        "]}\n"
    )
    refs = [f["properties"]["@id"] for f in facility.iter_geojson_features(str(src))]
    assert refs == ["node/1", "node/2"]


def test_it_still_reads_a_pretty_printed_fixture(tmp_path):
    """Every committed fixture is indented. A streaming reader that silently returned
    nothing for them would make every ingest test in this package pass over an empty
    list — the vacuous-green failure this session kept finding, delivered wholesale."""
    features = list(facility.iter_geojson_features(str(FIX / "osm_services.geojson")))
    assert len(features) >= 6
    assert all("properties" in f for f in features)


def test_streaming_and_loading_agree_on_the_same_file():
    streamed = list(facility.iter_geojson_features(str(FIX / "osm_filtered.geojson")))
    loaded = json.loads((FIX / "osm_filtered.geojson").read_text())["features"]
    assert len(streamed) == len(loaded)


def test_the_parser_accepts_a_STREAM_and_produces_the_same_records():
    """`parse_osm` takes a whole dict. The streaming path has to reach the same rules,
    or the box would ingest through code the tests never exercise."""
    from_dict = facility.parse_osm(json.loads((FIX / "osm_services.geojson").read_text()))
    from_stream = facility.parse_osm_features(
        facility.iter_geojson_features(str(FIX / "osm_services.geojson"))
    )
    assert [r.external_ref for r in from_stream] == [r.external_ref for r in from_dict]
    assert [r.facility_type for r in from_stream] == [r.facility_type for r in from_dict]


def test_a_truncated_file_fails_loudly_rather_than_ingesting_half(tmp_path):
    """A download cut short must not look like a small region. This is the shape of the
    dump-size guard in backup_db.sh, for the same reason: a partial result that looks
    like a complete one is worse than an error."""
    src = tmp_path / "cut.geojson"
    src.write_text(
        '{"type":"FeatureCollection","features":[\n'
        '{"type":"Feature","geometry":{"type":"Point","coordinates":[-89.4,43.07]},'
        '"properties":{"@id":"node/1"}},\n'
        '{"type":"Feature","geometry":{"type":"Point","coord'
    )
    try:
        list(facility.iter_geojson_features(str(src)))
    except ValueError:
        return
    raise AssertionError("a truncated extract was read as if it were complete")

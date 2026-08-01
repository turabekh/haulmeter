"""AI-CONTEXT: A5 requirement 3 — a facility card that can be CALLED.

The validation for A5 is "a driver with a breakdown finds and calls a shop", and
before this the app could not have satisfied it under any circumstances: ZERO of the
4,869 facilities in the registry carried a phone number, and the OSM adapter never
read one.

The numbers were already there. 633 facilities carry `phone` inside the raw
`osm_tags` blob the adapter preserves, and 245 carry `opening_hours` — arrived,
stored, and read by nothing. That is this project's most frequent defect (a
capability nothing reaches) in its purest form: the data was never missing.
"""

import json
from pathlib import Path

from app.foundation.f02_facility import public as facility

FIX = Path(__file__).parents[2] / "fixtures" / "ingest"


def _records():
    return {
        r.external_ref: r
        for r in facility.parse_osm(json.loads((FIX / "osm_services.geojson").read_text()))
    }


def test_a_phone_number_is_promoted_out_of_the_raw_tag_blob():
    rec = _records()["node/906"]
    assert rec.attributes["phone"] == "+1-608-555-0134"


def test_opening_hours_are_promoted_too():
    # honest rendering is the card's problem; getting the string out of the blob is
    # this layer's. The `hours` COLUMN stays untouched — it is written as {} on every
    # facility in the registry and read by nothing, so putting the value there would
    # be one more field nothing reaches.
    assert _records()["node/906"].attributes["opening_hours"] == "Mo-Fr 07:00-18:00"


def test_a_facility_with_no_phone_carries_no_phone_key():
    # absent, never empty — the card decides whether to offer a call by asking
    # whether there IS one, and "" would answer yes
    assert "phone" not in _records()["node/908"].attributes


def test_the_pin_carries_the_phone_so_the_card_can_offer_a_call(db):
    """The map card renders from a pin, not from a facility row. A phone that stops at
    the database is a phone the driver cannot tap — the same one-layer-short gap that
    left `setToken` writing a value production never read."""
    from app.foundation.f11_map import public as mapsvc

    rec = facility.StagedRecord(
        source_kind=facility.SourceKind.osm,
        external_ref="node/950",
        name="Portage Diesel Repair",
        lat=43.5390,
        lon=-89.4626,
        facility_type=facility.FacilityType.repair,
        attributes={"services": [facility.SERVICE_REPAIR], "phone": "+1-608-555-0199"},
    )
    fac, _ = facility.upsert_record(db, rec, batch_id="contact")
    pin = mapsvc.pins_for(db, [fac])[0]
    assert pin.phone == "+1-608-555-0199"
    assert facility.SERVICE_REPAIR in pin.services

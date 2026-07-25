"""AI-CONTEXT: E3.1 weigh stations, end to end over HTTP.

The whole chain in one test file, because the parts are only worth anything joined:
OSM fixture → ingest → the scale is on the Drive preset → a driver reports it closed
→ the next overlay and the corridor both say so.

Everything is fixture-driven; no live pull runs in CI.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f02_facility import public as facility
from app.foundation.f13_flags import public as flags
from app.main import app
from app.modules.m01_map import public as m1

FIX = Path(__file__).parents[1] / "fixtures" / "ingest"
# a point south of the fixture scales, so "ahead" means due north
ORIGIN = (43.0000, -89.4000)


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _auth(client, email="driver@example.com"):
    resp = client.post("/auth/register", json={"email": email, "password": "pw-123456"})
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _activate(db):
    m1.register_module(db)
    flags.enable(db, m1.FLAG_KEY)
    flags.enable(db, m1.WEIGH_STATION_FLAG)


def _ingest_a_scale(db, lat=43.2000, lon=-89.4000):
    """The real fixture record, moved onto the test corridor."""
    gj = json.loads((FIX / "osm_weigh.geojson").read_text())
    records = [r for r in facility.parse_osm(gj) if r.external_ref == "node/801"]
    records[0].lat, records[0].lon = lat, lon
    facility.ingest_records(db, records, batch_id="e2e")
    return records[0].name


def _report(client, headers, facility_id, status):
    return client.post(
        "/map/report",
        json={
            "facility_id": facility_id,
            "signal_type": "weigh_station_status",
            "value": {"status": status},
        },
        headers=headers,
    )


def test_an_ingested_scale_reaches_the_drive_overlay(client, db):
    _activate(db)
    name = _ingest_a_scale(db)
    headers = _auth(client)

    resp = client.get(
        "/map/overlay",
        params={"lat": ORIGIN[0], "lon": ORIGIN[1], "radius_m": 50000, "preset": "drive"},
        headers=headers,
    )
    assert resp.status_code == 200
    pins = {p["name"]: p for p in resp.json()["pins"]}
    assert name in pins
    assert pins[name]["facility_type"] == "weigh_station"
    assert pins[name]["shape"] == "small_square"  # §11.2, unchanged by this layer
    assert pins[name]["status"] is None  # nobody has passed yet — honest, not a guess


def test_the_layer_is_absent_while_its_flag_is_off(client, db):
    m1.register_module(db)
    flags.enable(db, m1.FLAG_KEY)  # the map itself is on; the scale layer is not
    name = _ingest_a_scale(db)
    headers = _auth(client)

    resp = client.get(
        "/map/overlay",
        params={"lat": ORIGIN[0], "lon": ORIGIN[1], "radius_m": 50000, "preset": "drive"},
        headers=headers,
    )
    assert name not in [p["name"] for p in resp.json()["pins"]]


def test_a_driver_report_moves_the_pin_and_the_corridor(client, db):
    """The chain that matters: report closed once, and both the map and the corridor
    say closed on the very next read."""
    _activate(db)
    name = _ingest_a_scale(db)
    headers = _auth(client)

    overlay = client.get(
        "/map/overlay",
        params={"lat": ORIGIN[0], "lon": ORIGIN[1], "radius_m": 50000, "preset": "drive"},
        headers=headers,
    ).json()
    pin = next(p for p in overlay["pins"] if p["name"] == name)

    posted = _report(client, headers, pin["facility_id"], "closed")
    assert posted.status_code == 200

    after = client.get(
        "/map/overlay",
        params={"lat": ORIGIN[0], "lon": ORIGIN[1], "radius_m": 50000, "preset": "drive"},
        headers=headers,
    ).json()
    assert next(p for p in after["pins"] if p["name"] == name)["status"] == "closed"

    ahead = client.get(
        "/map/scales-ahead",
        params={"lat": ORIGIN[0], "lon": ORIGIN[1], "heading_deg": 0},
        headers=headers,
    )
    assert ahead.status_code == 200
    assert [(s["name"], s["status"]) for s in ahead.json()] == [(name, "closed")]


def test_scales_ahead_needs_a_session(client):
    resp = client.get("/map/scales-ahead", params={"lat": ORIGIN[0], "lon": ORIGIN[1]})
    assert resp.status_code == 401


def test_scales_ahead_is_empty_while_the_flag_is_off(client, db):
    m1.register_module(db)
    flags.enable(db, m1.FLAG_KEY)
    _ingest_a_scale(db)
    headers = _auth(client)

    resp = client.get(
        "/map/scales-ahead",
        params={"lat": ORIGIN[0], "lon": ORIGIN[1], "heading_deg": 0},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_a_parking_reading_is_never_filed_against_a_scale_pin(client, db):
    """A scale's pin reads the weigh-station signal, so a stray parking report cannot
    render as its status — which is what would happen if the pin read whatever belief
    happened to exist."""
    _activate(db)
    name = _ingest_a_scale(db)
    headers = _auth(client)

    overlay = client.get(
        "/map/overlay",
        params={"lat": ORIGIN[0], "lon": ORIGIN[1], "radius_m": 50000, "preset": "drive"},
        headers=headers,
    ).json()
    pin = next(p for p in overlay["pins"] if p["name"] == name)

    client.post(
        "/map/report",
        json={
            "facility_id": pin["facility_id"],
            "signal_type": "parking_fullness",
            "value": {"status": "full"},
        },
        headers=headers,
    )

    after = client.get(
        "/map/overlay",
        params={"lat": ORIGIN[0], "lon": ORIGIN[1], "radius_m": 50000, "preset": "drive"},
        headers=headers,
    ).json()
    assert next(p for p in after["pins"] if p["name"] == name)["status"] is None

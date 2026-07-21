"""AI-CONTEXT: HTTP API tests for M1 + auth. Uses FastAPI TestClient with the
get_db dependency overridden to the transactional test session (so requests
share the isolated test DB and roll back). Proves the live status pipeline over
HTTP: register → report → the next overlay reflects the new belief.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f02_facility import public as facility
from app.main import app

DALLAS = (32.7767, -96.7970)


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _auth(client):
    resp = client.post(
        "/auth/register", json={"email": "driver@example.com", "password": "pw-123456"}
    )
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def test_overlay_requires_auth(client):
    resp = client.get("/map/overlay", params={"lat": DALLAS[0], "lon": DALLAS[1]})
    assert resp.status_code == 401


def test_register_login_and_overlay(client, db):
    headers = _auth(client)
    facility.create_facility(db, facility.FacilityType.truck_stop, "Stop", *DALLAS)
    resp = client.get(
        "/map/overlay",
        params={"lat": DALLAS[0], "lon": DALLAS[1], "radius_m": 3000, "preset": "drive"},
        headers=headers,
    )
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()]
    assert "Stop" in names


def test_overlay_enriches_bookable_and_fuel_badges(client, db):
    # M1 can't import M6/M7, so the overlay endpoint attaches the marketplace
    # badges that drive the map's Book / Fuel-here actions (NAV-5)
    from app.foundation.f01_identity import public as identity
    from app.modules.m06_parking import public as m6
    from app.modules.m07_fuel import public as m7

    headers = _auth(client)
    owner = identity.register_account(db, "lotowner@example.com", "pw-123456")
    prop = m6.create_property(db, owner.id, "Yardline", *DALLAS, vetted=True)
    m6.add_spot(db, prop, "A1", price_cents_per_night=2400)
    station = facility.create_facility(db, facility.FacilityType.fuel_station, "QuikFuel", *DALLAS)
    m7.set_station_pricing(db, station.id, gross_cents_per_gal=419, discount_cents_per_gal=25)

    pins = client.get(
        "/map/overlay",
        params={"lat": DALLAS[0], "lon": DALLAS[1], "radius_m": 3000, "preset": "tonight"},
        headers=headers,
    ).json()
    yardline = next(p for p in pins if p["name"] == "Yardline")
    book = next(b for b in yardline["badges"] if b["kind"] == "bookable")
    assert book["value"] == 2400 and book["spot_id"]  # cheapest active spot + price

    fuel_pins = client.get(
        "/map/overlay",
        params={"lat": DALLAS[0], "lon": DALLAS[1], "radius_m": 3000, "preset": "fuel"},
        headers=headers,
    ).json()
    quik = next(p for p in fuel_pins if p["name"] == "QuikFuel")
    net = next(b for b in quik["badges"] if b["kind"] == "fuel_net")
    assert net["net"] == 394 and net["savings"] == 25  # $4.19 gross − 25¢ discount


def test_login_wrong_password(client):
    client.post("/auth/register", json={"email": "x@example.com", "password": "right-pw"})
    resp = client.post("/auth/login", json={"email": "x@example.com", "password": "wrong"})
    assert resp.status_code == 401


def test_report_updates_belief_reflected_in_overlay(client, db):
    headers = _auth(client)
    fac = facility.create_facility(db, facility.FacilityType.truck_stop, "Reported Stop", *DALLAS)

    report = client.post(
        "/map/report",
        json={
            "facility_id": str(fac.id),
            "signal_type": "parking_fullness",
            "value": {"status": "full"},
        },
        headers=headers,
    )
    assert report.status_code == 200
    assert report.json()["presence_proven"] is False  # not geofenced here

    overlay = client.get(
        "/map/overlay",
        params={"lat": DALLAS[0], "lon": DALLAS[1], "radius_m": 3000, "preset": "drive"},
        headers=headers,
    )
    pin = next(p for p in overlay.json() if p["facility_id"] == str(fac.id))
    assert pin["status"] == "full"  # report -> aggregate -> pin, live over HTTP


def test_corridor_endpoint(client, db):
    headers = _auth(client)
    facility.create_facility(db, facility.FacilityType.truck_stop, "Ahead", 32.90, -96.7970)
    resp = client.get(
        "/map/corridor",
        params={"lat": DALLAS[0], "lon": DALLAS[1], "heading_deg": 0, "max_distance_m": 40000},
        headers=headers,
    )
    assert resp.status_code == 200
    assert [e["name"] for e in resp.json()] == ["Ahead"]

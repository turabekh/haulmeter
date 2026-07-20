"""AI-CONTEXT: HTTP API tests for M7 Fuel. TestClient with get_db overridden to
the transactional test session. Proves the net-price corridor over HTTP and the
pump-code path: a network station issues a code; a non-network station 409s.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f02_facility import public as facility
from app.main import app
from app.modules.m07_fuel import public as m7

ORIGIN = (32.7767, -96.7970)
AHEAD = (32.82, -96.7970)


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


def _network_station(db):
    station = facility.create_facility(db, facility.FacilityType.fuel_station, "Pilot", *AHEAD)
    merchant = m7.register_merchant(db, "FuelCo")
    m7.set_station_pricing(
        db,
        station.id,
        419,
        discount_cents_per_gal=25,
        spread_cents_per_gal=4,
        merchant_id=merchant.id,
    )
    return station


def test_corridor_requires_auth(client):
    resp = client.get("/fuel/corridor", params={"lat": ORIGIN[0], "lon": ORIGIN[1]})
    assert resp.status_code == 401


def test_corridor_returns_net_price(client, db):
    headers = _auth(client)
    _network_station(db)
    resp = client.get(
        "/fuel/corridor",
        params={
            "lat": ORIGIN[0],
            "lon": ORIGIN[1],
            "heading_deg": 0,
            "max_distance_m": 40000,
            "gallons": 100,
        },
        headers=headers,
    )
    assert resp.status_code == 200
    stop = resp.json()[0]
    assert stop["net_cents_per_gal"] == 394
    assert stop["savings_cents_per_gal"] == 25
    assert stop["is_network"] is True


def test_pump_code_issued_for_network_station(client, db):
    headers = _auth(client)
    station = _network_station(db)
    resp = client.post(
        "/fuel/pump-code",
        json={"station_id": str(station.id), "gallons": 100},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["pump_code"]) == 8
    assert body["net_cents"] == 39400
    assert body["state"] == "code_issued"


def test_pump_code_conflicts_for_non_network(client, db):
    headers = _auth(client)
    station = facility.create_facility(db, facility.FacilityType.fuel_station, "Indie", *AHEAD)
    m7.set_station_pricing(db, station.id, 429, source=m7.PriceSource.crowd)
    resp = client.post(
        "/fuel/pump-code",
        json={"station_id": str(station.id), "gallons": 50},
        headers=headers,
    )
    assert resp.status_code == 409

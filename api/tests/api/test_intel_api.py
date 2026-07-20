"""AI-CONTEXT: HTTP API tests for M8 Decision Intelligence. TestClient with
get_db overridden to the transactional test session. Proves the true-profit
calculator and the detention-risk flag over HTTP, basis included.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.main import app

DALLAS = (32.7767, -96.7970)
FAR = (32.9000, -96.8000)
AHEAD = (32.82, -96.7970)
T6 = datetime(2026, 7, 20, 6, 0, tzinfo=UTC)


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


def _dwell(db, fac_id, enter, exit_at, email="hist@x.com"):
    # a tracked stop by some (any) driver — dwell distribution is per-facility
    driver = identity.register_account(db, email, "pw-123456")
    location.arm_geofence(db, driver.id, fac_id)
    location.evaluate_ping(db, driver.id, *DALLAS, occurred_at=enter)
    location.evaluate_ping(db, driver.id, *FAR, occurred_at=exit_at)
    location.disarm_geofence(db, driver.id, fac_id, occurred_at=exit_at)


def test_true_profit_requires_auth(client):
    resp = client.post("/intel/true-profit", json={})
    assert resp.status_code == 401


def test_true_profit_over_http(client, db):
    headers = _auth(client)
    receiver = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "Receiver", *DALLAS
    )
    _dwell(db, receiver.id, T6, T6 + timedelta(hours=3))  # 1h over free time

    resp = client.post(
        "/intel/true-profit",
        json={
            "revenue_cents": 200000,
            "loaded_miles": 500,
            "mpg": 6.0,
            "tolls_cents": 3000,
            "receiver_facility_id": str(receiver.id),
            "free_time_minutes": 120,
            "rate_cents_per_hour": 7500,
            "origin_lat": DALLAS[0],
            "origin_lon": DALLAS[1],
        },
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["expected_detention_cents"] == 7500
    assert body["net_cents"] == 200000 - body["fuel_cost_cents"] - 3000 - 7500
    assert body["basis"]["detention_sample_size"] == 1


def test_detention_risk_flag_over_http(client, db):
    headers = _auth(client)
    receiver = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "Receiver", *DALLAS
    )
    _dwell(db, receiver.id, T6, T6 + timedelta(hours=3))  # over free time

    resp = client.get(
        f"/intel/detention-risk/{receiver.id}",
        params={"free_time_minutes": 120},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["exceed_rate"] == 1.0
    assert body["sample_size"] == 1
    assert body["basis"] == "tracked_stops"

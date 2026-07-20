"""AI-CONTEXT: HTTP API tests for the active-load lifecycle behind The Meter.
TestClient with get_db overridden to the transactional test session. Proves
create -> arrive -> meter: before arrival the Meter is pre-arrival; after a
geofence ENTER the detention clock is live.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
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


def _create(client, headers):
    resp = client.post(
        "/load",
        json={
            "facility_name": "Dallas Receiver",
            "lat": DALLAS[0],
            "lon": DALLAS[1],
            "counterparty": "Acme Brokerage",
            "free_time_minutes": 120,
            "rate_cents_per_hour": 7500,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["stop_id"]


def test_create_requires_auth(client):
    assert client.post("/load", json={}).status_code == 401


def test_meter_pre_arrival_then_live_after_arrive(client, db):
    headers = _auth(client)
    stop_id = _create(client, headers)

    # before arrival: the Meter is pre-arrival, clock not running
    pre = client.get(f"/load/{stop_id}/meter", headers=headers)
    assert pre.status_code == 200
    body = pre.json()
    assert body["facility_name"] == "Dallas Receiver"
    assert body["counterparty"] == "Acme Brokerage"
    assert body["phase"] == "not_arrived"
    assert body["free_time_minutes"] == 120

    # arrive -> geofence ENTER starts the detention clock
    arrived = client.post(f"/load/{stop_id}/arrive", headers=headers)
    assert arrived.status_code == 201
    assert arrived.json()["arrived"] is True

    live = client.get(f"/load/{stop_id}/meter", headers=headers)
    assert live.status_code == 200
    lbody = live.json()
    assert lbody["arrived"] is True
    # just arrived -> within free time, clock live
    assert lbody["phase"] == "within_free_time"
    assert lbody["free_time_remaining_seconds"] is not None


def test_meter_404_for_unknown_stop(client):
    headers = _auth(client)
    resp = client.get("/load/00000000-0000-0000-0000-000000000000/meter", headers=headers)
    assert resp.status_code == 404

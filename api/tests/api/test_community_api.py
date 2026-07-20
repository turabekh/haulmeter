"""AI-CONTEXT: HTTP API tests for M10 Community & Points. TestClient with get_db
overridden to the transactional test session. Proves the points balance, the
facility Q&A presence gate, and the free-lot guard on the handoff relay.
"""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.main import app
from app.modules.m06_parking import public as m6

DALLAS = (32.7767, -96.7970)


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


def test_points_requires_auth(client):
    assert client.get("/community/points").status_code == 401


def test_points_start_at_zero_rookie(client):
    headers = _auth(client)
    resp = client.get("/community/points", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["balance"] == 0
    assert body["level"] == "rookie"


def test_facility_qa_over_http(client, db):
    headers = _auth(client)
    stop = facility.create_facility(db, facility.FacilityType.truck_stop, "Loves", *DALLAS)
    ask = client.post(
        "/community/questions",
        json={"facility_id": str(stop.id), "text": "North entrance open?"},
        headers=headers,
    )
    assert ask.status_code == 201
    qid = ask.json()["question_id"]

    ans = client.post(
        f"/community/questions/{qid}/answers",
        json={"text": "Yes, open."},
        headers=headers,
    )
    assert ans.status_code == 201
    assert ans.json()["presence_proven"] is False  # not geofenced in this request

    listed = client.get(f"/community/questions/{stop.id}", headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["answers"][0]["text"] == "Yes, open."


def test_handoff_broadcast_nearby_and_claim(client, db):
    # driver A, present at a free lot, broadcasts "leaving in 15"
    a = client.post("/auth/register", json={"email": "a@x.com", "password": "pw-123456"}).json()
    headers_a = {"Authorization": f"Bearer {a['token']}"}
    stop = facility.create_facility(db, facility.FacilityType.truck_stop, "Loves", *DALLAS)
    a_id = uuid.UUID(a["account_id"])
    location.arm_geofence(db, a_id, stop.id)
    location.evaluate_ping(db, a_id, *DALLAS, occurred_at=datetime.now(UTC))

    bc = client.post(
        "/community/handoff",
        json={"facility_id": str(stop.id), "leaving_in_minutes": 15},
        headers=headers_a,
    )
    assert bc.status_code == 201

    near = client.get(
        "/community/handoff/nearby",
        params={"lat": DALLAS[0], "lon": DALLAS[1], "radius_m": 3000},
        headers=headers_a,
    )
    assert near.status_code == 200
    assert len(near.json()) == 1
    assert near.json()[0]["facility_name"] == "Loves"
    assert near.json()[0]["mine"] is True
    handoff_id = near.json()[0]["handoff_id"]

    # driver B claims it
    b = client.post("/auth/register", json={"email": "b@x.com", "password": "pw-123456"}).json()
    headers_b = {"Authorization": f"Bearer {b['token']}"}
    claim = client.post(f"/community/handoff/{handoff_id}/claim", headers=headers_b)
    assert claim.status_code == 201
    assert claim.json()["state"] == "claimed"
    # claiming again conflicts
    assert (
        client.post(f"/community/handoff/{handoff_id}/claim", headers=headers_b).status_code == 409
    )


def test_handoff_rejects_bookable_lot(client, db):
    headers = _auth(client)
    # a bookable M6 property is not a free lot — the relay must refuse it
    owner = identity.register_account(db, "owner@x.com", "pw-123456")
    parking = m6.create_property(db, owner.id, "Yardline", *DALLAS)
    resp = client.post(
        "/community/handoff",
        json={"facility_id": str(parking.facility_ref), "leaving_in_minutes": 15},
        headers=headers,
    )
    assert resp.status_code == 409  # free-lot only

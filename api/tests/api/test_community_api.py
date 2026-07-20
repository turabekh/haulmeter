"""AI-CONTEXT: HTTP API tests for M10 Community & Points. TestClient with get_db
overridden to the transactional test session. Proves the points balance, the
facility Q&A presence gate, and the free-lot guard on the handoff relay.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
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

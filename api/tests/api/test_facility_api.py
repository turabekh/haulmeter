"""AI-CONTEXT: HTTP API tests for M2 facility intelligence, using the shared
TestClient/get_db-override pattern (isolated transactional session)."""

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
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def test_profile_endpoint_returns_dwell_and_ratings(client, db):
    headers = _auth(client)
    fac = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Dock", *DALLAS)
    resp = client.get(f"/facility/{fac.id}/profile", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["dwell"]["overall"]["sample_size"] == 0  # honest empty
    assert body["ratings"]["review_count"] == 0
    # §23 entry 87: this asserted `basis == "m3_pending"` — a test holding a STUB in
    # place. M2-FR3 is computed in M3 now and composed here; the response key is
    # unchanged, and an empty facility still says so rather than reporting 0% risk.
    assert body["detention_risk"]["basis"] == "tracked_stops"
    assert body["detention_risk"]["exceed_rate"] is None  # nobody has finished a stop
    assert body["detention_risk"]["sample_size"] == 0


def test_submit_review_endpoint(client, db):
    headers = _auth(client)
    fac = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Dock", *DALLAS)
    resp = client.post(
        f"/facility/{fac.id}/review",
        json={"ratings": {"safety": 5}, "text": "solid"},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"  # awaits moderation before it is visible

"""AI-CONTEXT: E2 equipment HTTP surface. A bad VIN is caught at the edge with a
422 and a specific message (§12.4 — what happened + what to do), and `GET /auth/me`
always carries the four equipment fields so the More screen renders one stable
section rather than a shifting shape.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app

VALID_VIN = "1FUJGLDR9CSBF4183"


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _headers(client, email="equip-api@example.com"):
    token = client.post("/auth/register", json={"email": email, "password": "pw-123456"}).json()[
        "token"
    ]
    return {"Authorization": f"Bearer {token}"}


def test_patch_equipment_saves_and_returns_the_fields(client):
    headers = _headers(client)
    resp = client.patch(
        "/auth/equipment",
        json={
            "plate_state": "tx",
            "plate_number": "4xn2291",
            "unit_number": "118",
            "vin": VALID_VIN,
        },
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    # plate + state normalize to the uppercase form a DOT officer reads off the truck
    assert body["plate_state"] == "TX"
    assert body["plate_number"] == "4XN2291"
    assert body["unit_number"] == "118"
    assert body["vin"] == VALID_VIN


def test_me_always_carries_the_equipment_shape(client):
    headers = _headers(client, "shape@example.com")
    body = client.get("/auth/me", headers=headers).json()
    assert body["plate_state"] is None
    assert body["plate_number"] is None
    assert body["unit_number"] is None
    assert body["vin"] is None


def test_equipment_persists_to_me(client):
    headers = _headers(client, "persist@example.com")
    client.patch("/auth/equipment", json={"unit_number": "77"}, headers=headers)
    assert client.get("/auth/me", headers=headers).json()["unit_number"] == "77"


def test_bad_vin_is_rejected_with_a_specific_reason(client):
    headers = _headers(client, "badvin@example.com")
    resp = client.patch("/auth/equipment", json={"vin": "NOTAVIN"}, headers=headers)
    assert resp.status_code == 422
    assert "17" in resp.json()["detail"]


def test_equipment_is_optional_everywhere(client):
    # a driver who only knows their unit number is not blocked on plate or VIN
    headers = _headers(client, "partial@example.com")
    resp = client.patch("/auth/equipment", json={"plate_state": "IL"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["vin"] is None


def test_equipment_requires_a_session(client):
    assert client.patch("/auth/equipment", json={"unit_number": "1"}).status_code == 401

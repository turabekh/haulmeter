"""AI-CONTEXT: HTTP tests for onboarding — the operating authority declared at
signup decides whether detention claims are invoiced to the broker (owner-op) or
exported to a carrier (company driver). TestClient with get_db overridden.
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


def _claim_mode(client, headers):
    stop_id = client.post(
        "/load",
        json={
            "facility_name": "Dock",
            "lat": DALLAS[0],
            "lon": DALLAS[1],
            "counterparty": "Acme",
            "free_time_minutes": 0,
        },
        headers=headers,
    ).json()["stop_id"]
    client.post(f"/load/{stop_id}/arrive", headers=headers)
    client.post(f"/load/{stop_id}/claim", headers=headers)
    return client.get(f"/load/{stop_id}/claim", headers=headers).json()["mode"]


def test_register_with_own_authority_invoices_claims(client, db):
    reg = client.post(
        "/auth/register",
        json={"email": "op@example.com", "password": "pw-123456", "authority": "own_mc"},
    )
    assert reg.status_code == 201
    headers = {"Authorization": f"Bearer {reg.json()['token']}"}
    assert _claim_mode(client, headers) == "invoice"  # owner-operator -> owed to them


def test_register_without_authority_defaults_to_evidence_only(client, db):
    reg = client.post("/auth/register", json={"email": "co@example.com", "password": "pw-123456"})
    assert reg.status_code == 201
    headers = {"Authorization": f"Bearer {reg.json()['token']}"}
    assert _claim_mode(client, headers) == "evidence_only"  # company driver -> to carrier


def test_register_rejects_unknown_authority(client):
    resp = client.post(
        "/auth/register",
        json={"email": "x@example.com", "password": "pw-123456", "authority": "bogus"},
    )
    assert resp.status_code == 422

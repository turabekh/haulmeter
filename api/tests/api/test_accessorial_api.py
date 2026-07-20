"""AI-CONTEXT: HTTP API tests for M4 accessorial (shared TestClient/get_db pattern)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f05_load import public as loads
from app.main import app


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _setup(client, db):
    reg = client.post("/auth/register", json={"email": "oo@example.com", "password": "pw-123456"})
    headers = {"Authorization": f"Bearer {reg.json()['token']}"}
    account = db.get(identity.Account, uuid.UUID(reg.json()["account_id"]))
    identity.upsert_driver_profile(db, account, authority_type=identity.AuthorityType.own_mc)
    broker = loads.create_counterparty(
        db, "Acme", loads.CounterpartyKind.broker, contact_email="ap@acme.com"
    )
    load = loads.create_load(db, account.id, counterparty_id=broker.id, rate_cents=250000)
    return headers, load


def test_tonu_and_owed_flow(client, db):
    headers, load = _setup(client, db)
    resp = client.post(
        "/accessorial/tonu", json={"load_id": str(load.id), "amount_cents": 30000}, headers=headers
    )
    assert resp.status_code == 201
    assert resp.json()["kind"] == "tonu"

    owed = client.get("/accessorial/owed", headers=headers)
    assert owed.status_code == 200
    assert any(row["kind"] == "tonu" and row["amount_cents"] == 30000 for row in owed.json())


def test_lumper_endpoint(client, db):
    headers, load = _setup(client, db)
    resp = client.post(
        "/accessorial/lumper",
        json={"load_id": str(load.id), "amount_cents": 12500},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["kind"] == "lumper"

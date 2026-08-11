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


# AI-CONTEXT: what a driver needs to ACT on money they are owed (§23 entry 142).
#
# The Money tab listed "Detention · Invoiced · $187.50 · 12d" and could not say who was
# sitting on it, where it came from, or whether anyone had chased it. So the one screen
# in this product about being paid named neither the person who had not paid nor what had
# already been tried — which is the whole difference between "wait" and "do something".
def test_owed_names_WHO_owes_the_money(client, db):
    headers, load = _setup(client, db)
    client.post(
        "/accessorial/tonu", json={"load_id": str(load.id), "amount_cents": 30000}, headers=headers
    )

    row = client.get("/accessorial/owed", headers=headers).json()[0]

    assert row["counterparty_name"] == "Acme", "the row cannot name who owes it"


def test_a_claim_nobody_chased_says_so_rather_than_inventing_a_step(client, db):
    """Absent columns mean absent chasers. A history that padded itself would tell a
    driver their claim was being worked when it was sitting still."""
    headers, load = _setup(client, db)
    client.post(
        "/accessorial/lumper",
        json={"load_id": str(load.id), "amount_cents": 12500},
        headers=headers,
    )

    row = client.get("/accessorial/owed", headers=headers).json()[0]

    assert [e["event"] for e in row["history"]] == ["invoiced"]


def test_the_history_is_oldest_first(client, db):
    """It reads as a story, and a story out of order is not one."""
    headers, load = _setup(client, db)
    client.post(
        "/accessorial/tonu", json={"load_id": str(load.id), "amount_cents": 30000}, headers=headers
    )

    row = client.get("/accessorial/owed", headers=headers).json()[0]
    stamps = [e["at"] for e in row["history"]]

    assert stamps == sorted(stamps)

"""AI-CONTEXT: HTTP API tests for M12 Fleet & B2B. TestClient with get_db
overridden to the transactional test session. Proves fleet creation + the
consent-gated report, and the data product's subscription + min-sample guards.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f02_facility import public as facility
from app.foundation.f07_ledger import public as ledger
from app.main import app
from app.modules.m12_fleet import public as m12

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
        "/auth/register", json={"email": "owner@example.com", "password": "pw-123456"}
    )
    assert resp.status_code == 201
    return resp.json()["account_id"], {"Authorization": f"Bearer {resp.json()['token']}"}


def test_create_fleet_requires_auth(client):
    assert client.post("/fleet", json={"name": "Acme"}).status_code == 401


def test_create_fleet_and_report(client, db):
    account_id, headers = _auth(client)
    ledger.create_receivable(db, uuid.UUID(account_id), ledger.ReceivableKind.detention, 15000)

    created = client.post("/fleet", json={"name": "Acme Fleet"}, headers=headers)
    assert created.status_code == 201
    assert created.json()["role"] == "owner"
    fleet_id = created.json()["fleet_id"]

    report = client.get(f"/fleet/{fleet_id}/report", headers=headers)
    assert report.status_code == 200
    body = report.json()
    assert body["driver_count"] == 1  # the owner, consented
    assert body["owed_cents"] == 15000


def test_benchmark_requires_subscription(client, db):
    _, headers = _auth(client)
    fac = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Receiver", *DALLAS)
    resp = client.get(
        f"/fleet/benchmark/{fac.id}",
        params={"subscriber_ref": "analyst-x"},
        headers=headers,
    )
    assert resp.status_code == 402  # payment / subscription required

    m12.subscribe_data(db, "analyst-x")
    resp2 = client.get(
        f"/fleet/benchmark/{fac.id}",
        params={"subscriber_ref": "analyst-x"},
        headers=headers,
    )
    assert resp2.status_code == 200
    assert resp2.json()["suppressed"] is True  # below min sample -> suppressed, not leaked

"""AI-CONTEXT: HTTP API tests for M3 detention (shared TestClient/get_db pattern).
Exercises the whole recovery flow over HTTP: register -> start -> pack -> invoiced."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f05_load import public as loads
from app.main import app
from app.modules.m03_detention import public as m3

DALLAS = (32.7767, -96.7970)
FAR = (32.9000, -96.8000)


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_detention_start_and_pack_flow(client, db):
    reg = client.post("/auth/register", json={"email": "oo@example.com", "password": "pw-123456"})
    account_id = reg.json()["account_id"]
    headers = {"Authorization": f"Bearer {reg.json()['token']}"}

    # own authority -> can invoice
    import uuid

    account = db.get(identity.Account, uuid.UUID(account_id))
    identity.upsert_driver_profile(db, account, authority_type=identity.AuthorityType.own_mc)

    receiver = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Dock", *DALLAS)
    broker = loads.create_counterparty(
        db, "Acme", loads.CounterpartyKind.broker, contact_email="ap@acme.com"
    )
    load = loads.create_load(
        db,
        account.id,
        counterparty_id=broker.id,
        detention_rate_cents_per_hour=7500,
        free_time_minutes=120,
    )
    t0 = datetime.now(UTC) - timedelta(hours=5)
    stop = loads.add_stop(db, load, receiver.id, loads.StopType.delivery, appointment_start=t0)

    start = client.post("/detention/start", json={"stop_id": str(stop.id)}, headers=headers)
    assert start.status_code == 201
    claim_id = start.json()["claim_id"]
    assert start.json()["mode"] == "invoice"

    # the claim's clock is scoped to the visit that belongs to it, and this one opened
    # before the driver got there — which is the real order, even though the request
    # above ran at wall-clock now while the pings below are dated five hours back
    m3.get_claim(db, uuid.UUID(claim_id)).clock_since = t0 - timedelta(minutes=1)
    db.flush()

    # arrival 5h ago, departure 1h ago -> 4h dwell, 2h free -> 2h detention accrued
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=t0)
    location.evaluate_ping(db, account.id, *FAR, occurred_at=t0 + timedelta(hours=4))

    pack = client.post(f"/detention/{claim_id}/pack", headers=headers)
    assert pack.status_code == 200
    body = pack.json()
    assert body["chain_valid"] is True
    assert body["state"] == "invoiced"
    assert body["amount_cents"] == 15000  # 2h * $75
    assert body["receivable_ref"] is not None

    # a detention claim is private to its driver: another account is refused
    other = client.post(
        "/auth/register", json={"email": "nosy@example.com", "password": "pw-123456"}
    )
    ho = {"Authorization": f"Bearer {other.json()['token']}"}
    assert client.get(f"/detention/{claim_id}/clock", headers=ho).status_code == 403
    assert client.post(f"/detention/{claim_id}/pack", headers=ho).status_code == 403
    # the owner still reads their own clock
    assert client.get(f"/detention/{claim_id}/clock", headers=headers).status_code == 200

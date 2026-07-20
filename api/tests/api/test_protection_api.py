"""AI-CONTEXT: HTTP API tests for M5 protection (shared TestClient/get_db pattern)."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f06_documents import public as documents
from app.main import app


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _auth(client):
    reg = client.post(
        "/auth/register", json={"email": "driver@example.com", "password": "pw-123456"}
    )
    return reg.json()["account_id"], {"Authorization": f"Bearer {reg.json()['token']}"}


def test_wallet_and_incident_endpoints(client, db):
    import uuid

    account_id, headers = _auth(client)
    storage = documents.InMemoryObjectStorage()
    documents.set_default_storage(storage)
    documents.store_document(
        db, uuid.UUID(account_id), documents.DocType.cdl, b"cdl", storage=storage
    )

    wallet = client.get("/protection/wallet", headers=headers)
    assert wallet.status_code == 200
    assert any(d["doc_type"] == "cdl" for d in wallet.json()["documents"])

    incident = client.post(
        "/protection/incident", json={"kind": "cargo_damage", "note": "corner"}, headers=headers
    )
    assert incident.status_code == 201
    assert incident.json()["evidence_log_ref"] is not None


def test_inspection_endpoint(client, db):
    import uuid

    account_id, headers = _auth(client)
    storage = documents.InMemoryObjectStorage()
    documents.store_document(
        db, uuid.UUID(account_id), documents.DocType.cdl, b"cdl", storage=storage
    )
    documents.store_document(
        db, uuid.UUID(account_id), documents.DocType.rate_con, b"rc", storage=storage
    )
    resp = client.get("/protection/inspection", headers=headers)
    assert resp.status_code == 200
    types = {d["doc_type"] for d in resp.json()}
    assert "cdl" in types and "rate_con" not in types


def test_on_time_endpoint(client, db):
    import uuid

    from app.foundation.f05_load import public as loads

    account_id, headers = _auth(client)
    from app.foundation.f02_facility import public as facility

    fac = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "Dock", 32.7767, -96.7970
    )
    load = loads.create_load(db, uuid.UUID(account_id))
    now = datetime.now(UTC)
    stop = loads.add_stop(db, load, fac.id, loads.StopType.delivery, appointment_start=now)
    resp = client.post(
        "/protection/on-time",
        json={"stop_id": str(stop.id), "checked_in_at": now.isoformat()},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["within_window"] is True

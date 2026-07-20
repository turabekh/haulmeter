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


def test_condition_capture_guided_sequence(client, db):
    from app.foundation.f02_facility import public as facility
    from app.foundation.f05_load import public as loads

    account_id, headers = _auth(client)
    fac = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "Receiver", 32.7767, -96.797
    )
    import uuid as _uuid

    load = loads.create_load(db, _uuid.UUID(account_id))
    stop = loads.add_stop(db, load, fac.id, loads.StopType.delivery)

    seq = client.get("/protection/condition/sequence", headers=headers)
    assert seq.status_code == 200
    assert seq.json() == ["trailer_exterior", "seals", "load_blocking", "reefer_setpoint"]

    started = client.post(
        "/protection/condition/start",
        json={"stop_id": str(stop.id), "phase": "delivery"},
        headers=headers,
    )
    assert started.status_code == 201
    capture_id = started.json()["capture_id"]

    # walk the guided sequence, one hash-chained photo per step
    for i, prompt in enumerate(started.json()["sequence"], start=1):
        photo = client.post(
            f"/protection/condition/{capture_id}/photo",
            json={"prompt": prompt},
            headers=headers,
        )
        assert photo.status_code == 201
        assert photo.json()["photo_count"] == i


def test_condition_photo_is_idempotent_on_replay(client, db):
    from app.foundation.f02_facility import public as facility
    from app.foundation.f05_load import public as loads

    account_id, headers = _auth(client)
    fac = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "R", 32.7767, -96.797
    )
    import uuid as _uuid

    load = loads.create_load(db, _uuid.UUID(account_id))
    stop = loads.add_stop(db, load, fac.id, loads.StopType.delivery)
    capture_id = client.post(
        "/protection/condition/start", json={"stop_id": str(stop.id)}, headers=headers
    ).json()["capture_id"]

    key = "op-abc-123"
    body = {"prompt": "seals"}
    keyed = {**headers, "Idempotency-Key": key}

    first = client.post(f"/protection/condition/{capture_id}/photo", json=body, headers=keyed)
    assert first.status_code == 201
    assert first.json()["applied"] is True
    assert first.json()["photo_count"] == 1

    # the offline client replays the SAME key -> deduped, no second photo in the chain
    replay = client.post(f"/protection/condition/{capture_id}/photo", json=body, headers=keyed)
    assert replay.status_code == 201
    assert replay.json()["applied"] is False
    assert replay.json()["photo_count"] == 1  # still one — exactly-once

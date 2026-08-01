"""AI-CONTEXT: A1 requirement 1 over HTTP — the Load tab is told what THIS stop needs.

Measured before it was built: `/load/meter` carried a single hardcoded `bol_captured`,
so a DELIVERY's POD and a PICKUP's seal had nowhere to appear. A checklist that exists
only in the domain layer is configuration nobody can act on — the same shape as M5-FR1's
on-time verdict, which was computed on every arrival for months and reached no screen.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f02_facility import public as facility
from app.foundation.f05_load import public as loads
from app.main import app
from app.modules.m05_protection import public as m5

DOCK = (32.7767, -96.7970)


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _armed_stop(client, db, stop_type):
    m5.register_module(db)
    reg = client.post("/auth/register", json={"email": "oo@example.com", "password": "pw-123456"})
    headers = {"Authorization": f"Bearer {reg.json()['token']}"}
    account_id = reg.json()["account_id"]
    fac = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Dock", *DOCK)
    broker = loads.create_counterparty(db, "Acme", loads.CounterpartyKind.broker)
    import uuid

    load = loads.create_load(db, uuid.UUID(account_id), counterparty_id=broker.id)
    stop = loads.add_stop(db, load, fac.id, stop_type)
    loads.arm_stop(db, stop)
    db.flush()
    return headers, stop


def test_a_delivery_is_asked_for_a_POD(client, db):
    headers, stop = _armed_stop(client, db, loads.StopType.delivery)
    body = client.get(f"/load/{stop.id}/meter", headers=headers).json()
    rows = {r["item"]: r for r in body["checklist"]}
    assert "pod" in rows, "a driver dropping a load was never asked for the POD"
    assert "seal" not in rows, "asked for a seal on a delivery"
    assert rows["pod"]["captured"] is False
    assert set(rows["pod"]) >= {"item", "kind", "captured", "required"}


def test_a_pickup_is_asked_for_the_SEAL_instead(client, db):
    headers, stop = _armed_stop(client, db, loads.StopType.pickup)
    rows = {
        r["item"] for r in client.get(f"/load/{stop.id}/meter", headers=headers).json()["checklist"]
    }
    assert "seal" in rows and "pod" not in rows

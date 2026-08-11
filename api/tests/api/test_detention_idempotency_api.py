"""Findings F1, F2, F3 over HTTP — what a driver's second tap actually gets back.

The status codes are the content here. A retry after a success is not an error the driver
caused, and answering one as though it were invites them to try again on a claim that is
already with the broker.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f05_load import public as loads
from app.foundation.f07_ledger import public as ledger
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


def _driver(client, db, email="oo@example.com"):
    reg = client.post("/auth/register", json={"email": email, "password": "pw-123456"})
    account = db.get(identity.Account, uuid.UUID(reg.json()["account_id"]))
    identity.upsert_driver_profile(db, account, authority_type=identity.AuthorityType.own_mc)
    return account, {"Authorization": f"Bearer {reg.json()['token']}"}


def _stop_for(db, account, t0):
    dock = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Dock", *DALLAS)
    broker = loads.create_counterparty(
        db, "Acme", loads.CounterpartyKind.broker, contact_email="ap@acme.com"
    )
    load = loads.create_load(
        db, account.id, counterparty_id=broker.id,
        detention_rate_cents_per_hour=7500, free_time_minutes=120,
    )
    return loads.add_stop(db, load, dock.id, loads.StopType.delivery, appointment_start=t0)


def _accrued(db, account, t0):
    """Four hours on the dock against two hours free — $150 owed."""
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=t0)
    location.evaluate_ping(db, account.id, *FAR, occurred_at=t0 + timedelta(hours=4))


# --- F1 / F3: /detention/start ---
def test_starting_twice_creates_one_claim_and_says_which_happened(client, db):
    account, headers = _driver(client, db)
    stop = _stop_for(db, account, datetime.now(UTC) - timedelta(hours=5))

    created = client.post("/detention/start", json={"stop_id": str(stop.id)}, headers=headers)
    again = client.post("/detention/start", json={"stop_id": str(stop.id)}, headers=headers)

    assert created.status_code == 201
    assert again.status_code == 200
    assert created.json()["claim_id"] == again.json()["claim_id"]


def test_starting_a_claim_on_another_drivers_stop_is_refused(client, db):
    """F3: it checked the stop EXISTED and never that it was the caller's."""
    owner, _ = _driver(client, db, email="owner@example.com")
    stop = _stop_for(db, owner, datetime.now(UTC) - timedelta(hours=5))
    _, intruder = _driver(client, db, email="intruder@example.com")

    resp = client.post("/detention/start", json={"stop_id": str(stop.id)}, headers=intruder)

    assert resp.status_code == 403
    assert m3.claim_for_stop(db, stop.id) is None


def test_starting_a_claim_on_a_stop_that_does_not_exist_is_404(client, db):
    _, headers = _driver(client, db)

    resp = client.post(
        "/detention/start",
        json={"stop_id": "11111111-1111-1111-1111-111111111111"},
        headers=headers,
    )

    assert resp.status_code == 404


# --- F2: filing twice ---
def test_filing_twice_answers_409_with_the_first_filings_receivable(client, db):
    account, headers = _driver(client, db)
    t0 = datetime.now(UTC) - timedelta(hours=5)
    stop = _stop_for(db, account, t0)
    claim_id = client.post(
        "/detention/start", json={"stop_id": str(stop.id)}, headers=headers
    ).json()["claim_id"]
    m3.get_claim(db, uuid.UUID(claim_id)).clock_since = t0 - timedelta(minutes=1)
    db.flush()
    _accrued(db, account, t0)

    first = client.post(f"/detention/{claim_id}/pack", headers=headers)
    second = client.post(f"/detention/{claim_id}/pack", headers=headers)

    assert first.status_code == 200
    assert first.json()["amount_cents"] == 15000
    assert second.status_code == 409
    detail = second.json()["detail"]
    assert detail["error"] == "already_filed"
    assert detail["receivable_ref"] == first.json()["receivable_ref"]
    assert detail["amount_cents"] == 15000
    assert len(ledger.list_receivables(db, account.id)) == 1


def test_filing_twice_through_the_load_tab_answers_the_same_way(client, db):
    """The route a driver actually taps — `POST /load/{stop_id}/claim`."""
    account, headers = _driver(client, db)
    t0 = datetime.now(UTC) - timedelta(hours=5)
    stop = _stop_for(db, account, t0)
    claim = m3.start_claim(db, stop, started_at=t0 - timedelta(minutes=1))
    db.flush()
    _accrued(db, account, t0)

    first = client.post(f"/load/{stop.id}/claim", headers=headers)
    second = client.post(f"/load/{stop.id}/claim", headers=headers)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["detail"]["receivable_ref"] == str(claim.receivable_ref)
    assert len(ledger.list_receivables(db, account.id)) == 1

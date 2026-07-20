"""AI-CONTEXT: HTTP API tests for the Property-Owner portal. TestClient with
get_db overridden. Proves the owner sees their listing, its bookings, and the
accrued payout (F7 owner_payable).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.modules.m06_parking import public as m6

DALLAS = (32.7767, -96.7970)
T0 = datetime(2026, 7, 21, 18, 0, tzinfo=UTC)


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _auth(client, email="owner@example.com"):
    resp = client.post("/auth/register", json={"email": email, "password": "pw-123456"})
    assert resp.status_code == 201
    return resp.json()["account_id"], {"Authorization": f"Bearer {resp.json()['token']}"}


def test_dashboard_requires_auth(client):
    assert client.get("/owner/dashboard").status_code == 401


def test_owner_sees_listing_bookings_and_payout(client, db):
    account_id, headers = _auth(client)
    owner_id = uuid.UUID(account_id)
    prop = m6.create_property(db, owner_id, "Yardline Lot", *DALLAS, vetted=True)
    spot = m6.add_spot(db, prop, "A1", price_cents_per_night=2400)
    # a driver books two nights on the owner's spot
    from app.foundation.f01_identity import public as identity

    driver = identity.register_account(db, "driver@example.com", "pw-123456")
    booking = m6.book(db, spot, driver.id, T0, T0 + timedelta(days=2))

    resp = client.get("/owner/dashboard", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["properties"]) == 1
    assert body["properties"][0]["name"] == "Yardline Lot"
    assert body["properties"][0]["spots"][0]["price_cents_per_night"] == 2400
    assert len(body["bookings"]) == 1
    assert body["bookings"][0]["nights"] == 2
    # the platform owes the owner their payout (the take is baked out)
    assert body["payout_cents"] == booking.owner_payout_cents
    assert body["payout_cents"] > 0


def test_empty_owner_dashboard(client):
    _, headers = _auth(client)
    body = client.get("/owner/dashboard", headers=headers).json()
    assert body["properties"] == []
    assert body["bookings"] == []
    assert body["payout_cents"] == 0

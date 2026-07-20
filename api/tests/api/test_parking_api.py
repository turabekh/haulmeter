"""AI-CONTEXT: HTTP API tests for M6 Parking. TestClient with get_db overridden
to the transactional test session. Proves the booking path over HTTP: an owner's
listing becomes bookable inventory, a driver books it at one transparent price,
and a double-book is rejected 409.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.main import app
from app.modules.m06_parking import public as m6

DALLAS = (32.7767, -96.7970)
T0 = datetime(2026, 7, 20, 18, 0, tzinfo=UTC)


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _auth(client):
    resp = client.post(
        "/auth/register", json={"email": "driver@example.com", "password": "pw-123456"}
    )
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _listing(db, price=2400):
    owner = identity.register_account(db, "owner@example.com", "pw-123456")
    prop = m6.create_property(db, owner.id, "Yardline Lot", *DALLAS, vetted=True)
    return m6.add_spot(db, prop, "A1", price_cents_per_night=price)


def test_bookable_requires_auth(client):
    resp = client.get("/parking/bookable", params={"lat": DALLAS[0], "lon": DALLAS[1]})
    assert resp.status_code == 401


def test_bookable_lists_inventory(client, db):
    headers = _auth(client)
    spot = _listing(db)
    resp = client.get(
        "/parking/bookable",
        params={"lat": DALLAS[0], "lon": DALLAS[1], "radius_m": 3000},
        headers=headers,
    )
    assert resp.status_code == 200
    ids = [b["spot_id"] for b in resp.json()]
    assert str(spot.id) in ids


def test_book_returns_one_transparent_price(client, db):
    headers = _auth(client)
    spot = _listing(db, price=2400)
    resp = client.post(
        "/parking/book",
        json={
            "spot_id": str(spot.id),
            "start_at": T0.isoformat(),
            "end_at": (T0 + timedelta(days=2)).isoformat(),
        },
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["nights"] == 2
    assert body["price_cents"] == 4800  # driver sees the take-inclusive price
    assert body["state"] == "booked"


def test_double_book_conflicts(client, db):
    headers = _auth(client)
    spot = _listing(db)
    payload = {
        "spot_id": str(spot.id),
        "start_at": T0.isoformat(),
        "end_at": (T0 + timedelta(days=1)).isoformat(),
    }
    first = client.post("/parking/book", json=payload, headers=headers)
    assert first.status_code == 201
    second = client.post("/parking/book", json=payload, headers=headers)
    assert second.status_code == 409

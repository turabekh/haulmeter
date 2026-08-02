"""AI-CONTEXT: A6 req 1 — M13's two halves, and the leak each gate exists to stop.

v2.0 §4 defers the food half indefinitely; §3's A6 says the service-center half is
exactly what drivers asked for. One flag could only turn both off together, so the
gate is per vendor TYPE.

The question every test here asks is the same one, from a different door: **with one
half switched off, can anything about that half still be reached?** A split that only
gates the endpoints whose NAME says "food" is not a split — the shared endpoints take
a `vendor_id`, and a `vendor_id` carries its half with it.
"""

import base64
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f02_facility import public as facility
from app.foundation.f13_flags import public as flags
from app.main import app
from app.modules.m13_vendor import public as m13

JOPLIN = (37.084, -94.513)
PDF = base64.b64encode(b"%PDF-1.4 business license").decode()


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def registered(db):
    m13.register_module(db)
    return True


def _headers(client, email):
    token = client.post("/auth/register", json={"email": email, "password": "pw-123456"}).json()[
        "token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _register_vendor(client, headers, name, vendor_type):
    return client.post(
        "/vendors/register",
        json={
            "name": name,
            "metro": "joplin-mo",
            "languages": ["en"],
            "halal_answered": True,
            "halal_disclosure": "No halal claim",
            "vendor_type": vendor_type,
        },
        headers=headers,
    )


def _service_facility(db, name):
    fac = facility.create_facility(db, facility.FacilityType.repair, name, *JOPLIN)
    fac.attributes = {"services": [facility.SERVICE_TIRE, facility.SERVICE_REPAIR]}
    db.flush()
    return fac


# --- the split itself ---
def test_both_halves_default_off_and_are_registered_separately(db, registered):
    """PRD §6: flags default OFF, and the new half is a flag of its own rather than a
    behaviour hidden inside the old one.

    The ROW is what is asserted, not `is_enabled` — that returns False for a flag
    nobody registered, so it would have said "off" about a flag that does not exist.
    An unregistered flag is invisible in the admin console and unswitchable by an
    operator, which is the state A6 req 1 exists to leave behind."""
    rows = {
        key: db.get(flags.FeatureFlag, key)
        for key in (m13.FLAG_KEY, m13.SERVICE_CENTER_FLAG_KEY)
    }
    assert all(row is not None for row in rows.values()), rows
    assert all(row.description for row in rows.values())  # switchable AND explicable
    assert all(row.enabled is False for row in rows.values())
    assert m13.is_active(db) is False


def test_every_vendor_type_is_gated_by_some_flag(db):
    """A type absent from the mapping is a type nothing gates. This is the check that
    a THIRD vendor type added later cannot arrive ungated by default."""
    for vendor_type in m13.VendorType:
        assert m13.flag_for_type(vendor_type)


def test_service_center_runs_while_food_is_deferred(client, db, registered):
    """v2.0 §4 and §3 held at once — the whole point of A6 req 1."""
    flags.enable(db, m13.SERVICE_CENTER_FLAG_KEY)
    assert m13.is_active(db) is True
    assert m13.is_active_for(db, m13.VendorType.service_center) is True
    assert m13.is_active_for(db, m13.VendorType.food_mobile) is False

    headers = _headers(client, "shop@example.com")
    resp = _register_vendor(client, headers, "Gateway Truck Service", "service_center")
    assert resp.status_code == 201, resp.text

    _service_facility(db, "Gateway Truck Service")
    rows = client.get("/vendor/claimable?q=gateway", headers=headers)
    assert rows.status_code == 200
    assert [r["name"] for r in rows.json()] == ["Gateway Truck Service"]


def test_a_cook_cannot_register_while_the_food_half_is_deferred(client, db, registered):
    flags.enable(db, m13.SERVICE_CENTER_FLAG_KEY)
    headers = _headers(client, "cook@example.com")
    resp = _register_vendor(client, headers, "Osh Express", "food_mobile")
    assert resp.status_code == 404, resp.text


def test_food_survives_with_the_service_half_off(client, db, registered):
    """The split cuts both ways, and this is the direction that proves the gate is
    about TYPE rather than a hardcoded preference for the new half."""
    flags.enable(db, m13.FLAG_KEY)
    headers = _headers(client, "cook2@example.com")
    assert _register_vendor(client, headers, "Osh Express", "food_mobile").status_code == 201
    assert _register_vendor(
        client, _headers(client, "shop2@example.com"), "Gateway Truck Service", "service_center"
    ).status_code == 404


# --- the leak the shared endpoints would have been ---
def test_a_deferred_cooks_sheet_is_not_readable_through_the_shared_endpoint(
    client, db, registered
):
    """THE test of this session. `/vendors/{id}` names no half, so with only the
    service half live it would happily serve a food vendor's whole sheet — menu,
    appearances, reviews — and the deferral would be a label on the map rather than a
    gate on the product."""
    flags.enable(db, m13.FLAG_KEY)
    headers = _headers(client, "cook3@example.com")
    vendor_id = _register_vendor(client, headers, "Osh Express", "food_mobile").json()["vendor_id"]
    assert client.get(f"/vendors/{vendor_id}", headers=headers).status_code == 200

    # food is deferred; the service half stays live
    flags.disable(db, m13.FLAG_KEY)
    flags.enable(db, m13.SERVICE_CENTER_FLAG_KEY)

    driver = _headers(client, "driver@example.com")
    assert client.get(f"/vendors/{vendor_id}", headers=driver).status_code == 404
    assert (
        client.post(
            f"/vendors/{vendor_id}/review", json={"rating": 5}, headers=driver
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/vendors/{vendor_id}/report", json={"reason": "spam"}, headers=driver
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/vendors/{vendor_id}/confirm",
            json={"facility_id": str(_service_facility(db, "Anywhere").id)},
            headers=driver,
        ).status_code
        == 404
    )


def test_a_deferred_cook_cannot_reach_their_own_portal(client, db, registered):
    flags.enable(db, m13.FLAG_KEY)
    headers = _headers(client, "cook4@example.com")
    _register_vendor(client, headers, "Osh Express", "food_mobile")
    assert client.get("/vendor/profile", headers=headers).status_code == 200

    flags.disable(db, m13.FLAG_KEY)
    flags.enable(db, m13.SERVICE_CENTER_FLAG_KEY)
    assert client.get("/vendor/profile", headers=headers).status_code == 404
    assert client.get("/vendor/appearances", headers=headers).status_code == 404
    assert client.get("/vendor/menu", headers=headers).status_code == 404


def test_a_service_centre_cannot_publish_a_food_appearance_into_a_dark_half(
    client, db, registered
):
    """`_my_vendor` passes a service centre through — its half is on. The food-SHAPED
    routes have to refuse on their own, or the deferred mechanism stays reachable by
    whoever happens to be allowed in the door."""
    flags.enable(db, m13.SERVICE_CENTER_FLAG_KEY)
    headers = _headers(client, "shop3@example.com")
    _register_vendor(client, headers, "Gateway Truck Service", "service_center")
    fac = _service_facility(db, "Gateway Truck Service")
    start = datetime.now(UTC) + timedelta(hours=1)

    resp = client.post(
        "/vendor/appearances",
        json={
            "facility_id": str(fac.id),
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(hours=3)).isoformat(),
            "offerings": [{"name": "Osh", "price_cents": 900}],
        },
        headers=headers,
    )
    assert resp.status_code == 404, resp.text


def test_switching_type_cannot_be_used_to_walk_into_a_dark_half(client, db, registered):
    """The one write that MOVES a vendor between halves. Gated on the destination, or
    a deferred cook re-enters by editing one field on their own profile."""
    flags.enable(db, m13.SERVICE_CENTER_FLAG_KEY)
    headers = _headers(client, "shop4@example.com")
    _register_vendor(client, headers, "Gateway Truck Service", "service_center")

    resp = client.patch("/vendor/profile", json={"vendor_type": "food_mobile"}, headers=headers)
    assert resp.status_code == 404, resp.text
    assert client.get("/vendor/profile", headers=headers).json()["vendor_type"] == "service_center"


def test_a_deferred_driver_can_still_unfollow(client, db, registered):
    """§21.8: off is exactly as easy as on. A driver who followed a cook before the
    deferral must not be locked into alerts by a flag they cannot see."""
    flags.enable(db, m13.FLAG_KEY)
    headers = _headers(client, "cook5@example.com")
    vendor_id = _register_vendor(client, headers, "Osh Express", "food_mobile").json()["vendor_id"]
    driver = _headers(client, "driver2@example.com")
    assert client.post(f"/vendors/{vendor_id}/follow", headers=driver).status_code == 200

    flags.disable(db, m13.FLAG_KEY)
    flags.enable(db, m13.SERVICE_CENTER_FLAG_KEY)
    resp = client.delete(f"/vendors/{vendor_id}/follow", headers=driver)
    assert resp.status_code == 200
    assert resp.json()["following"] is False


def test_the_router_is_still_gone_when_both_halves_are_off(client, db, registered):
    """The router-level gate got weaker by construction (it admits on EITHER half), so
    the case it still has to cover is asserted rather than assumed."""
    driver = _headers(client, "driver3@example.com")
    resp = client.get("/vendors/appearances?min_lat=36&min_lon=-95&max_lat=38&max_lon=-93",
                      headers=driver)
    assert resp.status_code == 404

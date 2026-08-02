"""AI-CONTEXT: the vendor's standing menu, and the guarantee that makes it safe.

A menu item is what the vendor SELLS. An offering is what was ADVERTISED for one
window. Publishing copies the first into the second, and the tests that matter most
here are the ones proving the copy is a SNAPSHOT: raising a price today must change
what is advertised next and nothing a driver has already read. The reliability record
and the reviews both refer to past windows, so a menu that rewrote history would make
them unauditable.

Also covered: tenancy (another vendor's item is indistinguishable from one that does
not exist) and PHASE A (no money moves; a price is a number on a card).
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f02_facility import public as facility
from app.foundation.f13_flags import public as flags
from app.main import app
from app.modules.m13_vendor import public as m13

MADISON = (43.0700, -89.4000)


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def active(db):
    m13.register_module(db)
    flags.enable(db, m13.FLAG_KEY)
    # these tests predate the A6 half-split and mean "M13 is on", so they turn
    # on both halves. The split itself is asserted in test_vendor_flag_split.py.
    flags.enable(db, m13.SERVICE_CENTER_FLAG_KEY)
    return db


def _account(client, email):
    resp = client.post("/auth/register", json={"email": email, "password": "pw-123456"})
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _vendor(client, headers, name="Ana's Tamales"):
    resp = client.post(
        "/vendors/register",
        json={
            "name": name,
            "vendor_type": "food_mobile",
            "metro": "Madison WI",
            "languages": ["es", "en"],
            "halal_disclosure": "no halal claim",
            "halal_answered": True,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["vendor_id"]


@pytest.fixture
def cook(client, active):
    headers = _account(client, "cook@example.com")
    _vendor(client, headers)
    return headers


def _add(client, headers, name, price, portions=None):
    return client.post(
        "/vendor/menu",
        json={"name": name, "price_cents": price, "portions": portions},
        headers=headers,
    )


# --- the list a cook keeps ---
def test_a_cook_builds_a_menu_once(client, cook):
    assert _add(client, cook, "Tamales (pork)", 1200, 40).status_code == 201
    assert _add(client, cook, "Tamales (chicken)", 1200).status_code == 201

    # the cook's own order, not alphabetical — a menu is a list they arrange
    menu = client.get("/vendor/menu", headers=cook).json()
    assert [(i["name"], i["price_cents"]) for i in menu] == [
        ("Tamales (pork)", 1200),
        ("Tamales (chicken)", 1200),
    ]
    assert menu[0]["portions"] == 40


def test_a_price_can_be_changed_in_one_place(client, cook):
    item = _add(client, cook, "Tamales", 1200).json()
    resp = client.patch(f"/vendor/menu/{item['item_id']}", json={"price_cents": 1350}, headers=cook)
    assert resp.status_code == 200
    assert resp.json()["price_cents"] == 1350


def test_retiring_an_item_keeps_it_rather_than_deleting_it(client, cook):
    # a seasonal dish comes back, and its price should come back with it
    item = _add(client, cook, "Pozole", 1400).json()
    client.delete(f"/vendor/menu/{item['item_id']}", headers=cook)

    assert client.get("/vendor/menu", headers=cook).json() == []
    kept = client.get("/vendor/menu?include_inactive=true", headers=cook).json()
    assert [(i["name"], i["price_cents"], i["is_active"]) for i in kept] == [
        ("Pozole", 1400, False)
    ]


def test_re_adding_a_retired_dish_brings_it_back(client, cook):
    item = _add(client, cook, "Pozole", 1400).json()
    client.delete(f"/vendor/menu/{item['item_id']}", headers=cook)

    again = _add(client, cook, "Pozole", 1500)
    assert again.status_code == 201
    assert again.json()["item_id"] == item["item_id"]  # the same dish, not a second
    assert again.json()["is_active"] is True
    assert again.json()["price_cents"] == 1500


def test_a_mistyped_price_is_refused(client, cook):
    # Q-4 exists because "food available" is useless to a driver deciding on a
    # detour; a $1,200 tamale is the same failure wearing a number
    assert _add(client, cook, "Tamales", 120000).status_code == 422
    assert _add(client, cook, "Tamales", -1).status_code == 422
    assert _add(client, cook, "   ", 1200).status_code == 422


# --- tenancy ---
def test_a_vendor_cannot_touch_another_vendors_menu(client, active):
    ana = _account(client, "ana@example.com")
    _vendor(client, ana, "Ana's Tamales")
    item = _add(client, ana, "Tamales", 1200).json()

    bob = _account(client, "bob@example.com")
    _vendor(client, bob, "Bob's BBQ")

    # indistinguishable from an item that does not exist — the scoping is in the
    # QUERY, so it cannot be forgotten at a call site
    assert (
        client.patch(
            f"/vendor/menu/{item['item_id']}", json={"price_cents": 1}, headers=bob
        ).status_code
        == 404
    )
    assert client.delete(f"/vendor/menu/{item['item_id']}", headers=bob).status_code == 404
    assert client.get("/vendor/menu", headers=bob).json() == []


def test_the_menu_needs_a_vendor_profile(client, active):
    just_an_account = _account(client, "nobody@example.com")
    assert client.get("/vendor/menu", headers=just_an_account).status_code == 404


# --- publishing from the menu, and the snapshot guarantee ---
def _publish(client, headers, db, menu_item_ids=None, offerings=None):
    fac = facility.create_facility(db, facility.FacilityType.truck_stop, "Pilot 442", *MADISON)
    starts = datetime.now(UTC) + timedelta(hours=2)
    return client.post(
        "/vendor/appearances",
        json={
            "facility_id": str(fac.id),
            "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(hours=4)).isoformat(),
            "offerings": offerings or [],
            "menu_item_ids": menu_item_ids,
        },
        headers=headers,
    )


def test_publishing_can_name_the_whole_menu(client, cook, db):
    _add(client, cook, "Tamales (pork)", 1200, 40)
    _add(client, cook, "Tamales (chicken)", 1200)

    resp = _publish(client, cook, db, menu_item_ids=[])
    assert resp.status_code == 201, resp.text

    appearance = client.get("/vendor/appearances", headers=cook).json()[0]
    assert sorted(o["name"] for o in appearance["offerings"]) == [
        "Tamales (chicken)",
        "Tamales (pork)",
    ]


def test_publishing_can_name_just_some_of_it(client, cook, db):
    pork = _add(client, cook, "Tamales (pork)", 1200).json()
    _add(client, cook, "Pozole", 1400)

    _publish(client, cook, db, menu_item_ids=[pork["item_id"]])
    appearance = client.get("/vendor/appearances", headers=cook).json()[0]
    assert [o["name"] for o in appearance["offerings"]] == ["Tamales (pork)"]


def test_editing_the_menu_never_rewrites_what_was_already_advertised(client, cook, db):
    """The guarantee the whole split exists for. A driver read $12.00 on Tuesday;
    Wednesday's price rise must not make Tuesday's listing claim $13.50."""
    item = _add(client, cook, "Tamales", 1200).json()
    _publish(client, cook, db, menu_item_ids=[])

    client.patch(f"/vendor/menu/{item['item_id']}", json={"price_cents": 1350}, headers=cook)

    published = client.get("/vendor/appearances", headers=cook).json()[0]
    assert published["offerings"][0]["price_cents"] == 1200  # as advertised, not as now
    assert client.get("/vendor/menu", headers=cook).json()[0]["price_cents"] == 1350


def test_retiring_a_dish_does_not_empty_a_published_window(client, cook, db):
    item = _add(client, cook, "Tamales", 1200).json()
    _publish(client, cook, db, menu_item_ids=[])

    client.delete(f"/vendor/menu/{item['item_id']}", headers=cook)

    published = client.get("/vendor/appearances", headers=cook).json()[0]
    assert [o["name"] for o in published["offerings"]] == ["Tamales"]


def test_typed_offerings_still_work_without_a_menu(client, cook, db):
    # the menu is a convenience, not a new requirement
    resp = _publish(
        client, cook, db, offerings=[{"name": "Today only: birria", "price_cents": 1500}]
    )
    assert resp.status_code == 201


def test_publishing_nothing_priced_is_refused_with_the_named_gap(client, cook, db):
    resp = _publish(client, cook, db, menu_item_ids=[])
    assert resp.status_code == 422
    assert "offering_with_price" in resp.json()["detail"]["missing"]


# --- Phase A ---
def test_the_menu_ships_no_payment_path(client, cook, db):
    from fastapi.testclient import TestClient as _TC

    spec = _TC(app).get("/openapi.json").json()
    menu_paths = [p for p in spec["paths"] if "/vendor/menu" in p]
    assert menu_paths
    blob = str({p: spec["paths"][p] for p in menu_paths}).lower()
    for forbidden in ("checkout", "payment", "charge", "order", "invoice", "payout"):
        assert forbidden not in blob, f"{forbidden} reached the menu API"

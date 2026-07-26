"""AI-CONTEXT: how far away a cook is, and the lot they are at.

Two things the map has never carried and the decision to detour depends on:

1. **Distance.** `appearances_in_bbox` took no origin, so `distance_m` was null on
   every map entry — which also left Q-3's LAST tie-breaker permanently unreachable.
   Populating it makes that tie-breaker fire for the first time, so the ordering
   change is asserted here deliberately rather than discovered later.
2. **The lot.** Every entry names the facility and carries its coordinates, because
   a sheet that cannot name where a cook is standing cannot offer to take you there.

The honesty rule: **no origin means no distance.** A driver who has not shared a
location must see nothing rather than a figure measured from a guess.
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
BBOX = {"min_lat": 42.9, "min_lon": -89.6, "max_lat": 43.2, "max_lon": -89.2}


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
    return db


def _account(client, email):
    resp = client.post("/auth/register", json={"email": email, "password": "pw-123456"})
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _cook(client, db, name, lat, lon, facility_name=None):
    headers = _account(client, f"{name.replace(' ', '').lower()}@example.com")
    client.post(
        "/vendors/register",
        json={
            "name": name,
            "vendor_type": "food_mobile",
            "metro": "Madison WI",
            "languages": ["en"],
            "halal_disclosure": "no halal claim",
            "halal_answered": True,
        },
        headers=headers,
    )
    # the Q-4 floor refuses a listing with no priced offering, so every cook here
    # has a menu — publishing snapshots it into the appearance
    client.post("/vendor/menu", json={"name": "Plov", "price_cents": 1200}, headers=headers)
    fac = facility.create_facility(
        db, facility.FacilityType.truck_stop, facility_name or f"{name} stop", lat, lon
    )
    starts = datetime.now(UTC) + timedelta(minutes=30)
    client.post(
        "/vendor/appearances",
        json={
            "facility_id": str(fac.id),
            "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(hours=4)).isoformat(),
            "menu_item_ids": [],
        },
        headers=headers,
    )
    return headers, fac


def _search(client, driver, **params):
    return client.get("/vendors/appearances", params={**BBOX, **params}, headers=driver).json()


def test_no_location_means_no_distance_never_a_guess(client, active, db):
    _cook(client, db, "Anas Tamales", *MADISON)
    driver = _account(client, "driver-a@example.com")

    rows = _search(client, driver)
    assert len(rows) == 1
    assert rows[0]["distance_m"] is None


def test_an_origin_measures_from_the_driver(client, active, db):
    _cook(client, db, "Anas Tamales", *MADISON)
    driver = _account(client, "driver-b@example.com")

    # ~1.1 km south of the lot
    rows = _search(client, driver, lat=43.06, lon=-89.4000)
    assert 1000 < rows[0]["distance_m"] < 1300


def test_every_entry_names_the_lot_it_is_at(client, active, db):
    _cook(client, db, "Anas Tamales", *MADISON, facility_name="Loves 212")
    driver = _account(client, "driver-c@example.com")

    row = _search(client, driver)[0]
    # a sheet that cannot name the lot cannot offer to take a driver there
    assert row["facility_name"] == "Loves 212"
    assert round(row["lat"], 3) == round(MADISON[0], 3)
    assert round(row["lon"], 3) == round(MADISON[1], 3)


def test_the_q3_distance_tie_breaker_finally_fires(client, active, db):
    """Both cooks are unverified, unapproved, equally reliable and in the same
    bucket, so every earlier key ties and distance is the only thing left. Before an
    origin existed it was `inf` for both and the order was arbitrary."""
    _cook(client, db, "Far Cook", 43.20, -89.40)
    _cook(client, db, "Near Cook", 43.0705, -89.40)
    driver = _account(client, "driver-d@example.com")

    near_first = [r["name"] for r in _search(client, driver, lat=MADISON[0], lon=MADISON[1])]
    assert near_first[0] == "Near Cook"

    # and from the other end of the same viewport the order flips — the ranking is
    # reading the driver's position, not a stored preference for one cook
    far_first = [r["name"] for r in _search(client, driver, lat=43.20, lon=-89.40)]
    assert far_first[0] == "Far Cook"


def test_a_filter_still_cannot_reorder_anything(client, active, db):
    """Distance is a TIE-BREAKER inside Q-3, not a filter. Narrowing the result set
    must not change the relative order of what survives (§11.3)."""
    _cook(client, db, "Far Cook", 43.20, -89.40)
    _cook(client, db, "Near Cook", 43.0705, -89.40)
    driver = _account(client, "driver-e@example.com")

    everyone = [r["name"] for r in _search(client, driver, lat=MADISON[0], lon=MADISON[1])]
    narrowed = [
        r["name"] for r in _search(client, driver, lat=MADISON[0], lon=MADISON[1], language="en")
    ]
    assert narrowed == [n for n in everyone if n in narrowed]

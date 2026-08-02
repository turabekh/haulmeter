"""AI-CONTEXT: M13 HTTP surface. The wire format is where the §11.7 honesty split
becomes real: every presence payload carries `source`, so a client physically cannot
render "N drivers" for something the vendor said about itself.

Also pinned here: the module is invisible while its flag is off (PRD §6), Q-6 caps
survive the round trip, and no payment endpoint exists.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f13_flags import public as flags
from app.main import app
from app.modules.m13_vendor import public as m13

DALLAS = (32.7767, -96.7970)


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def live(db):
    m13.register_module(db)
    flags.enable(db, m13.FLAG_KEY)
    # these tests predate the A6 half-split and mean "M13 is on", so they turn
    # on both halves. The split itself is asserted in test_vendor_flag_split.py.
    flags.enable(db, m13.SERVICE_CENTER_FLAG_KEY)
    return True


def _headers(client, email):
    token = client.post("/auth/register", json={"email": email, "password": "pw-123456"}).json()[
        "token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _facility(db, name="Loves 212"):
    return facility.create_facility(db, facility.FacilityType.truck_stop, name, *DALLAS)


def _window():
    start = datetime.now(UTC) - timedelta(minutes=10)
    return start.isoformat(), (start + timedelta(hours=4)).isoformat()


def _make_vendor(client, db, headers, fac, name="Osh Express", metro="dallas-tx"):
    resp = client.post(
        "/vendors/register",
        json={
            "name": name,
            "metro": metro,
            "languages": ["uz", "ru"],
            "halal_answered": True,
            "halal_disclosure": "Halal butcher, Dallas",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    starts, ends = _window()
    published = client.post(
        "/vendors/appearances",
        json={
            "facility_id": str(fac.id),
            "starts_at": starts,
            "ends_at": ends,
            "offerings": [{"name": "Osh", "price_cents": 1200, "portions": 40}],
            "property_approved": True,
        },
        headers=headers,
    )
    assert published.status_code == 201, published.text
    return resp.json()["vendor_id"], published.json()["appearance_ids"][0]


def test_the_module_is_invisible_while_its_flag_is_off(client, db):
    headers = _headers(client, "off@example.com")
    fac = _facility(db)
    assert client.get(f"/vendors/at/{fac.id}", headers=headers).status_code == 404


def test_publish_then_discover_at_a_facility(client, db, live):
    headers = _headers(client, "cook@example.com")
    fac = _facility(db)
    vendor_id, _ = _make_vendor(client, db, headers, fac)

    found = client.get(f"/vendors/at/{fac.id}", headers=headers).json()
    assert [v["vendor_id"] for v in found] == [vendor_id]
    assert found[0]["offerings"][0]["price_cents"] == 1200
    assert found[0]["property_approved"] is True


def test_an_incomplete_listing_names_what_is_missing(client, db, live):
    headers = _headers(client, "sloppy@example.com")
    fac = _facility(db)
    client.post(
        "/vendors/register",
        json={
            "name": "No Menu Cook",
            "metro": "waco-tx",
            "languages": ["en"],
            "halal_answered": True,
        },
        headers=headers,
    )
    starts, ends = _window()
    resp = client.post(
        "/vendors/appearances",
        json={"facility_id": str(fac.id), "starts_at": starts, "ends_at": ends, "offerings": []},
        headers=headers,
    )

    assert resp.status_code == 422
    assert "offering_with_price" in resp.json()["detail"]["missing"]


def test_a_duplicate_registration_points_at_the_existing_vendor(client, db, live):
    first = _headers(client, "one@example.com")
    fac = _facility(db)
    vendor_id, _ = _make_vendor(client, db, first, fac)

    second = _headers(client, "two@example.com")
    resp = client.post(
        "/vendors/register",
        json={"name": "osh express", "metro": "dallas-tx"},
        headers=second,
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["existing_vendor_id"] == vendor_id


def test_a_driver_confirmation_reads_as_crowd(client, db, live):
    cook = _headers(client, "cook2@example.com")
    fac = _facility(db)
    vendor_id, _ = _make_vendor(client, db, cook, fac)

    driver = _headers(client, "driver@example.com")
    me = client.get("/auth/me", headers=driver).json()["account_id"]
    location.arm_geofence(db, me, fac.id)
    location.evaluate_ping(db, me, *DALLAS, occurred_at=datetime.now(UTC))

    resp = client.post(
        f"/vendors/{vendor_id}/confirm",
        json={"facility_id": str(fac.id), "present": True},
        headers=driver,
    )
    body = resp.json()
    assert body["present"] is True
    assert body["source"] == "crowd"
    assert body["sample_size"] == 1


def test_a_vendor_self_report_reads_as_vendor_not_as_drivers(client, db, live):
    # the wire contract that protects §11.7: the client is TOLD this is the vendor
    # speaking, so it can never print a driver count for it
    cook = _headers(client, "cook3@example.com")
    fac = _facility(db)
    _make_vendor(client, db, cook, fac)

    resp = client.post(
        "/vendors/self-report", json={"facility_id": str(fac.id), "present": True}, headers=cook
    )
    assert resp.json()["source"] == "vendor"


def test_the_sheet_shows_reliability_as_a_pair_not_a_percentage(client, db, live):
    cook = _headers(client, "cook4@example.com")
    fac = _facility(db)
    vendor_id, _ = _make_vendor(client, db, cook, fac)

    sheet = client.get(f"/vendors/{vendor_id}", headers=cook).json()
    assert sheet["shows_up"] == {"confirmed": 0, "published": 0}
    assert sheet["halal_disclosure"] == "Halal butcher, Dallas"
    assert sheet["languages"] == ["uz", "ru"]


def test_the_card_caps_at_two_and_the_sheet_shows_all(client, db, live):
    fac = _facility(db)
    for i in range(3):
        headers = _headers(client, f"many{i}@example.com")
        _make_vendor(client, db, headers, fac, name=f"Cook {i}", metro=f"metro-{i}")

    reader = _headers(client, "reader@example.com")
    assert len(client.get(f"/vendors/at/{fac.id}", headers=reader).json()) == 2
    assert len(client.get(f"/vendors/at/{fac.id}?all_vendors=true", headers=reader).json()) == 3


def test_the_bbox_feed_backs_the_map_badge(client, db, live):
    cook = _headers(client, "cook5@example.com")
    fac = _facility(db)
    _make_vendor(client, db, cook, fac)

    found = client.get(
        "/vendors/appearances?min_lat=32&min_lon=-97.5&max_lat=33.5&max_lon=-96",
        headers=cook,
    ).json()
    assert len(found) == 1
    assert found[0]["facility_id"] == str(fac.id)


def test_an_empty_viewport_returns_an_empty_list(client, db, live):
    headers = _headers(client, "empty@example.com")
    found = client.get(
        "/vendors/appearances?min_lat=44&min_lon=-100&max_lat=45&max_lon=-99", headers=headers
    ).json()
    assert found == []


def test_cancelling_notifies_and_removes_the_listing(client, db, live):
    cook = _headers(client, "cook6@example.com")
    fac = _facility(db)
    vendor_id, appearance_id = _make_vendor(client, db, cook, fac)

    resp = client.delete(f"/vendors/appearances/{appearance_id}", headers=cook)
    assert resp.status_code == 200
    assert client.get(f"/vendors/at/{fac.id}", headers=cook).json() == []


def test_a_vendor_cannot_cancel_someone_elses_appearance(client, db, live):
    cook = _headers(client, "cook7@example.com")
    fac = _facility(db)
    _, appearance_id = _make_vendor(client, db, cook, fac)

    stranger = _headers(client, "stranger@example.com")
    assert (
        client.delete(f"/vendors/appearances/{appearance_id}", headers=stranger).status_code == 404
    )


def test_alert_opt_in_is_explicit(client, db, live):
    headers = _headers(client, "optin@example.com")
    resp = client.put("/vendors/alerts/opt-in", json={"opted_in": True}, headers=headers)
    assert resp.json() == {"class": "vendor_alert", "opted_in": True}


def test_a_vendor_can_be_muted_individually(client, db, live):
    cook = _headers(client, "cook8@example.com")
    fac = _facility(db)
    vendor_id, _ = _make_vendor(client, db, cook, fac)

    driver = _headers(client, "muter@example.com")
    resp = client.post(f"/vendors/{vendor_id}/mute", headers=driver)
    assert vendor_id in resp.json()["muted"]


def test_no_payment_endpoint_exists():
    # Phase A: the router surface itself must offer no way to move money
    paths = {getattr(r, "path", "") for r in app.routes}
    for forbidden in ("/vendors/order", "/vendors/checkout", "/vendors/pay"):
        assert forbidden not in paths

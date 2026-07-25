"""AI-CONTEXT: M13-FR8 vendor portal API + the Session-B driver endpoints.

Two things this file exists to prove:

1. **Tenancy.** A vendor reaches their own records and nothing else. A portal that
   leaks between tenants is worse than no portal, so every write is checked against
   a second vendor trying the same call.
2. **One number, one meaning.** The show-up rate the vendor sees in /vendor/analytics
   is byte-identical to the pair a driver sees on the sheet — no vanity variant.
"""

import base64
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
def live(db):
    m13.register_module(db)
    flags.enable(db, m13.FLAG_KEY)
    return True


def _headers(client, email):
    token = client.post("/auth/register", json={"email": email, "password": "pw-123456"}).json()[
        "token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _account_id(client, headers):
    return client.get("/auth/me", headers=headers).json()["account_id"]


def _facility(db, name="Loves 212", coords=DALLAS, ftype=None):
    return facility.create_facility(db, ftype or facility.FacilityType.truck_stop, name, *coords)


def _window(hours=4):
    start = datetime.now(UTC) - timedelta(minutes=10)
    return start.isoformat(), (start + timedelta(hours=hours)).isoformat()


def _register_vendor(client, headers, name="Osh Express", metro="dallas-tx", vendor_type=None):
    payload = {
        "name": name,
        "metro": metro,
        "languages": ["uz", "ru"],
        "halal_answered": True,
        "halal_disclosure": "Halal butcher, Dallas",
    }
    if vendor_type:
        payload["vendor_type"] = vendor_type
    resp = client.post("/vendors/register", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["vendor_id"]


def _publish(client, headers, fac):
    starts, ends = _window()
    resp = client.post(
        "/vendor/appearances",
        json={
            "facility_id": str(fac.id),
            "starts_at": starts,
            "ends_at": ends,
            "offerings": [{"name": "Osh", "price_cents": 1200}],
            "property_approved": True,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["appearance_ids"][0]


# --- FR8: profile ---
def test_the_portal_is_invisible_while_the_flag_is_off(client, db):
    headers = _headers(client, "off@example.com")
    assert client.get("/vendor/profile", headers=headers).status_code == 404


def test_a_driver_with_no_vendor_profile_gets_404(client, db, live):
    headers = _headers(client, "justadriver@example.com")
    assert client.get("/vendor/profile", headers=headers).status_code == 404


def test_the_profile_names_exactly_what_blocks_publishing(client, db, live):
    headers = _headers(client, "gaps@example.com")
    client.post(
        "/vendors/register",
        json={"name": "Incomplete Cook", "metro": "waco-tx"},
        headers=headers,
    )
    body = client.get("/vendor/profile", headers=headers).json()
    assert set(body["profile_gaps"]) == {"languages", "halal_disclosure"}


def test_editing_the_profile_closes_the_gaps(client, db, live):
    headers = _headers(client, "fixit@example.com")
    client.post("/vendors/register", json={"name": "Fixable", "metro": "waco-tx"}, headers=headers)

    resp = client.patch(
        "/vendor/profile",
        json={"languages": ["en"], "halal_answered": True, "halal_disclosure": "No halal claim"},
        headers=headers,
    )
    assert resp.json()["profile_gaps"] == []


def test_uploading_a_document_moves_to_documents_on_file_only(client, db, live):
    headers = _headers(client, "docs@example.com")
    _register_vendor(client, headers)

    resp = client.post(
        "/vendor/documents", json={"kind": "license", "content_b64": PDF}, headers=headers
    )
    # the middle rung means paperwork is on file, never that anyone inspected (§11.7)
    assert resp.json()["verify_status"] == "documents_on_file"


# --- FR8: schedule management ---
def test_a_vendor_manages_their_own_schedule(client, db, live):
    headers = _headers(client, "sched@example.com")
    _register_vendor(client, headers)
    fac = _facility(db)
    appearance_id = _publish(client, headers, fac)

    listed = client.get("/vendor/appearances", headers=headers).json()
    assert [a["appearance_id"] for a in listed] == [appearance_id]
    assert listed[0]["offerings"][0]["price_cents"] == 1200


def test_a_weekly_schedule_materializes_through_the_portal(client, db, live):
    headers = _headers(client, "weekly@example.com")
    _register_vendor(client, headers)
    fac = _facility(db)
    starts, ends = _window()
    resp = client.post(
        "/vendor/appearances",
        json={
            "facility_id": str(fac.id),
            "starts_at": starts,
            "ends_at": ends,
            "offerings": [{"name": "Osh", "price_cents": 1200}],
            "weekly": [datetime.now(UTC).weekday()],
        },
        headers=headers,
    )
    # the Session-A materialization runs unchanged — 28-day horizon, weekly
    assert len(resp.json()["appearance_ids"]) == 4


def test_a_vendor_cannot_touch_another_vendors_appearance(client, db, live):
    mine = _headers(client, "mine@example.com")
    _register_vendor(client, mine)
    fac = _facility(db)
    appearance_id = _publish(client, mine, fac)

    theirs = _headers(client, "theirs@example.com")
    _register_vendor(client, theirs, name="Other Cook", metro="austin-tx")
    assert client.delete(f"/vendor/appearances/{appearance_id}", headers=theirs).status_code == 404


# --- FR6: promotions through the portal ---
def test_creating_a_promotion_reports_delivery_honestly(client, db, live):
    headers = _headers(client, "promo@example.com")
    _register_vendor(client, headers)
    fac = _facility(db)
    _publish(client, headers, fac)

    starts = datetime.now(UTC) - timedelta(minutes=5)
    resp = client.post(
        "/vendor/promotions",
        json={
            "text": "Free chai with any plate",
            "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(hours=6)).isoformat(),
        },
        headers=headers,
    )
    body = resp.json()
    # nobody has opted in, so nothing was delivered — and the portal SAYS so rather
    # than implying the promotion reached drivers
    assert body["alerts_delivered"] == 0
    assert client.get("/vendor/promotions", headers=headers).json()[0]["status"] == "active"


def test_a_promotion_appears_in_the_labelled_slot_endpoint_only(client, db, live):
    headers = _headers(client, "slot@example.com")
    _register_vendor(client, headers)
    fac = _facility(db)
    _publish(client, headers, fac)
    starts = datetime.now(UTC) - timedelta(minutes=5)
    client.post(
        "/vendor/promotions",
        json={
            "text": "Two somsa for $6",
            "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(hours=6)).isoformat(),
        },
        headers=headers,
    )

    slots = client.get(f"/vendors/promotions/at/{fac.id}", headers=headers).json()
    assert [s["text"] for s in slots] == ["Two somsa for $6"]
    assert slots[0]["promoted"] is True

    # and the ranked list carries no promotion key at all (Q-3)
    ranked = client.get(f"/vendors/at/{fac.id}", headers=headers).json()
    assert all("promoted" not in entry for entry in ranked)


def test_a_vendor_cannot_cancel_another_vendors_promotion(client, db, live):
    mine = _headers(client, "p1@example.com")
    _register_vendor(client, mine)
    fac = _facility(db)
    _publish(client, mine, fac)
    starts = datetime.now(UTC) - timedelta(minutes=5)
    promo_id = client.post(
        "/vendor/promotions",
        json={
            "text": "Mine",
            "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(hours=2)).isoformat(),
        },
        headers=mine,
    ).json()["promotion_id"]

    theirs = _headers(client, "p2@example.com")
    _register_vendor(client, theirs, name="Rival Cook", metro="austin-tx")
    assert client.delete(f"/vendor/promotions/{promo_id}", headers=theirs).status_code == 404


# --- FR5: reviews ---
def test_a_driver_reviews_a_vendor(client, db, live):
    cook = _headers(client, "rcook@example.com")
    vendor_id = _register_vendor(client, cook)
    driver = _headers(client, "rdriver@example.com")

    resp = client.post(
        f"/vendors/{vendor_id}/review", json={"rating": 5, "text": "Great"}, headers=driver
    )
    assert resp.status_code == 201
    assert resp.json()["average"] == 5.0
    assert resp.json()["reviewers"] == 1


def test_a_second_review_inside_the_window_says_when_to_return(client, db, live):
    cook = _headers(client, "rcook2@example.com")
    vendor_id = _register_vendor(client, cook)
    driver = _headers(client, "rdriver2@example.com")
    client.post(f"/vendors/{vendor_id}/review", json={"rating": 5}, headers=driver)

    resp = client.post(f"/vendors/{vendor_id}/review", json={"rating": 1}, headers=driver)
    assert resp.status_code == 409
    assert resp.json()["detail"]["next_allowed_at"]


def test_a_bad_rating_is_refused(client, db, live):
    cook = _headers(client, "rcook3@example.com")
    vendor_id = _register_vendor(client, cook)
    driver = _headers(client, "rdriver3@example.com")
    assert (
        client.post(f"/vendors/{vendor_id}/review", json={"rating": 9}, headers=driver).status_code
        == 422
    )


def test_the_sheet_carries_the_review_pair_and_the_promotions(client, db, live):
    cook = _headers(client, "rcook4@example.com")
    vendor_id = _register_vendor(client, cook)
    driver = _headers(client, "rdriver4@example.com")
    client.post(f"/vendors/{vendor_id}/review", json={"rating": 4, "text": "Solid"}, headers=driver)

    sheet = client.get(f"/vendors/{vendor_id}", headers=driver).json()
    assert sheet["reviews"]["average"] == 4.0
    assert sheet["reviews"]["reviewers"] == 1
    assert sheet["reviews"]["items"][0]["text"] == "Solid"
    assert sheet["promotions"] == []
    assert sheet["can_review"] is False  # they just reviewed


# --- Q-8: reporting ---
def test_reporting_a_review_hides_it_immediately(client, db, live):
    cook = _headers(client, "mcook@example.com")
    vendor_id = _register_vendor(client, cook)
    author = _headers(client, "author@example.com")
    client.post(f"/vendors/{vendor_id}/review", json={"rating": 1, "text": "junk"}, headers=author)
    # the id comes from the DB: the sheet omits review ids by design (a driver
    # reports from the row they are looking at, not by pasting an identifier)
    review = m13.list_reviews(db, vendor_id, include_hidden=True)[0]

    reporter = _headers(client, "reporter@example.com")
    resp = client.post(
        f"/vendors/reviews/{review.id}/report", json={"reason": "offensive"}, headers=reporter
    )
    assert resp.json() == {"reported": True, "hidden": True, "reports": 1}
    assert client.get(f"/vendors/{vendor_id}", headers=reporter).json()["reviews"]["reviewers"] == 0


def test_reporting_a_vendor_once_does_not_hide_it(client, db, live):
    cook = _headers(client, "mcook2@example.com")
    vendor_id = _register_vendor(client, cook)
    rival = _headers(client, "rival@example.com")

    resp = client.post(f"/vendors/{vendor_id}/report", json={"reason": "spam"}, headers=rival)
    assert resp.json()["hidden"] is False


def test_the_same_driver_cannot_report_twice(client, db, live):
    cook = _headers(client, "mcook3@example.com")
    vendor_id = _register_vendor(client, cook)
    rival = _headers(client, "rival2@example.com")
    client.post(f"/vendors/{vendor_id}/report", json={"reason": "spam"}, headers=rival)

    again = client.post(f"/vendors/{vendor_id}/report", json={"reason": "spam"}, headers=rival)
    assert again.status_code == 409


def test_an_unknown_report_reason_is_refused(client, db, live):
    cook = _headers(client, "mcook4@example.com")
    vendor_id = _register_vendor(client, cook)
    driver = _headers(client, "who@example.com")
    resp = client.post(
        f"/vendors/{vendor_id}/report", json={"reason": "i_dont_like_them"}, headers=driver
    )
    assert resp.status_code == 422


# --- FR7: claiming through the portal ---
def _service_setup(client, db, email="shop@example.com", name="Gateway Truck Service"):
    headers = _headers(client, email)
    _register_vendor(client, headers, name=name, metro="joplin-mo", vendor_type="service_center")
    fac = facility.create_facility(db, facility.FacilityType.repair, name, *JOPLIN)
    fac.attributes = {"services": [facility.SERVICE_TIRE]}
    return headers, fac


def test_a_service_center_claims_and_curates(client, db, live):
    headers, fac = _service_setup(client, db)
    claim_id = client.post(
        "/vendor/claims",
        json={
            "facility_id": str(fac.id),
            "claimed_name": "Gateway Truck Service",
            "content_b64": PDF,
        },
        headers=headers,
    ).json()["claim_id"]

    claim = db.get(m13.FacilityClaim, __import__("uuid").UUID(claim_id))
    m13.decide_claim(db, claim, approve=True)

    resp = client.patch(
        f"/vendor/claims/{claim_id}",
        json={"services_added": ["towing"], "hours": "24/7", "phone": "4175550123"},
        headers=headers,
    )
    # the union is echoed back: the ingested "tire" survives the curation (E3.2)
    assert set(resp.json()["services"]) == {"tire", "towing"}
    assert resp.json()["hours"] == "24/7"


def test_curation_is_refused_before_approval(client, db, live):
    headers, fac = _service_setup(client, db, "shop2@example.com", "Gateway Truck Service")
    claim_id = client.post(
        "/vendor/claims",
        json={"facility_id": str(fac.id), "claimed_name": "Gateway Truck Service"},
        headers=headers,
    ).json()["claim_id"]

    resp = client.patch(f"/vendor/claims/{claim_id}", json={"hours": "24/7"}, headers=headers)
    assert resp.status_code == 409


def test_a_food_vendor_is_refused_a_claim(client, db, live):
    headers = _headers(client, "cookclaim@example.com")
    _register_vendor(client, headers, name="Osh Express", metro="joplin-mo")
    fac = facility.create_facility(
        db, facility.FacilityType.repair, "Gateway Truck Service", *JOPLIN
    )
    fac.attributes = {"services": [facility.SERVICE_TIRE]}

    resp = client.post(
        "/vendor/claims",
        json={"facility_id": str(fac.id), "claimed_name": "Gateway Truck Service"},
        headers=headers,
    )
    assert resp.status_code == 403


def test_a_mismatched_name_reports_its_score(client, db, live):
    headers, fac = _service_setup(client, db, "shop3@example.com", "Gateway Truck Service")
    resp = client.post(
        "/vendor/claims",
        json={"facility_id": str(fac.id), "claimed_name": "Completely Different Ltd"},
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "name_mismatch"


def test_an_unclaimed_facility_has_no_service_center_page(client, db, live):
    headers = _headers(client, "plain@example.com")
    fac = facility.create_facility(db, facility.FacilityType.repair, "Nobody's Shop", *JOPLIN)
    assert client.get(f"/vendors/service-center/{fac.id}", headers=headers).status_code == 404


# --- FR8: analytics honesty ---
def test_the_vendor_sees_the_same_show_up_pair_a_driver_sees(client, db, live):
    cook = _headers(client, "acook@example.com")
    vendor_id = _register_vendor(client, cook)
    fac = _facility(db)
    _publish(client, cook, fac)

    driver = _headers(client, "adriver@example.com")
    me = _account_id(client, driver)
    location.arm_geofence(db, me, fac.id)
    location.evaluate_ping(db, me, *DALLAS, occurred_at=datetime.now(UTC))
    client.post(
        f"/vendors/{vendor_id}/confirm",
        json={"facility_id": str(fac.id), "present": True},
        headers=driver,
    )
    m13.sweep_appearances(db, now=datetime.now(UTC) + timedelta(hours=6))

    vendor_view = client.get("/vendor/analytics", headers=cook).json()["shows_up"]
    driver_view = client.get(f"/vendors/{vendor_id}", headers=driver).json()["shows_up"]
    assert vendor_view == driver_view == {"confirmed": 1, "published": 1}


def test_analytics_counts_sheet_views(client, db, live):
    cook = _headers(client, "vcook@example.com")
    vendor_id = _register_vendor(client, cook)
    driver = _headers(client, "vdriver@example.com")
    client.get(f"/vendors/{vendor_id}", headers=driver)
    client.get(f"/vendors/{vendor_id}", headers=driver)

    assert client.get("/vendor/analytics", headers=cook).json()["sheet_views"] == 2


def test_no_billing_endpoint_exists_on_the_portal():
    # Phase A: promotions are free and the portal offers no way to pay for anything
    paths = set(app.openapi()["paths"])
    for forbidden in ("/vendor/billing", "/vendor/invoice", "/vendor/payout", "/vendor/orders"):
        assert forbidden not in paths

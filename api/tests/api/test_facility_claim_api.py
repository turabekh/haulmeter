"""AI-CONTEXT: M13-FR7 — the claim flow's discovery half and what the portal is told.

The claim/curate endpoints themselves are covered in `test_vendor_portal_api.py`.
This file exists for the two things the UI depends on being true:

1. **A vendor never has to recognise their own site from a UUID.** Every claim row
   and every search hit carries the facility's own name and address.
2. **A dispute is disclosed BEFORE the form is filled.** A rival claim on a claimed
   facility becomes a dispute an admin decides (never a silent loss), so the search
   result says so up front rather than the vendor learning it from the outcome.
"""

import base64

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
def live(db):
    m13.register_module(db)
    flags.enable(db, m13.FLAG_KEY)
    return True


def _headers(client, email):
    token = client.post("/auth/register", json={"email": email, "password": "pw-123456"}).json()[
        "token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _vendor(client, headers, name, vendor_type="service_center"):
    resp = client.post(
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
    assert resp.status_code == 201, resp.text
    return resp.json()["vendor_id"]


def _service_facility(db, name, services=None, coords=JOPLIN):
    fac = facility.create_facility(db, facility.FacilityType.repair, name, *coords)
    fac.attributes = {"services": services if services is not None else [facility.SERVICE_TIRE]}
    db.flush()
    return fac


def test_search_returns_the_name_and_address_a_claimant_recognises(client, db, live):
    headers = _headers(client, "shop-a@example.com")
    _vendor(client, headers, "Gateway Truck Service")
    fac = _service_facility(db, "Gateway Truck Service")
    fac.address = "1400 Range Line Rd, Joplin MO"

    rows = client.get("/vendor/claimable?q=gateway", headers=headers).json()
    assert len(rows) == 1
    assert rows[0]["name"] == "Gateway Truck Service"
    assert rows[0]["address"] == "1400 Range Line Rd, Joplin MO"
    assert rows[0]["services"] == ["tire"]
    assert rows[0]["already_claimed"] is False


def test_search_omits_a_facility_with_no_service_to_claim(client, db, live):
    headers = _headers(client, "shop-b@example.com")
    _vendor(client, headers, "Gateway Truck Service")
    _service_facility(db, "Gateway Truck Service")
    _service_facility(db, "Gateway Rest Area", services=[])

    names = [r["name"] for r in client.get("/vendor/claimable?q=gateway", headers=headers).json()]
    assert names == ["Gateway Truck Service"]


def test_an_already_claimed_site_says_so_before_the_form_is_filled(client, db, live):
    first = _headers(client, "shop-c@example.com")
    _vendor(client, first, "Gateway Truck Service")
    fac = _service_facility(db, "Gateway Truck Service")
    claim_id = client.post(
        "/vendor/claims",
        json={"facility_id": str(fac.id), "claimed_name": "Gateway Truck Service"},
        headers=first,
    ).json()["claim_id"]
    import uuid as _uuid

    m13.decide_claim(db, db.get(m13.FacilityClaim, _uuid.UUID(claim_id)), approve=True)

    rival = _headers(client, "shop-d@example.com")
    # a distinct BUSINESS name (Q-5 refuses a near-duplicate in the same metro) —
    # what is claimed is the site's name, which is a different field
    _vendor(client, rival, "Range Line Repair Co")
    rows = client.get("/vendor/claimable?q=gateway", headers=rival).json()
    assert rows[0]["already_claimed"] is True
    assert rows[0]["claimed_by_me"] is False

    # and the claimant themselves is told it is THEIRS, not merely taken
    mine = client.get("/vendor/claimable?q=gateway", headers=first).json()
    assert mine[0]["claimed_by_me"] is True


def test_a_rival_claim_becomes_a_dispute_not_a_rejection(client, db, live):
    first = _headers(client, "shop-e@example.com")
    _vendor(client, first, "Gateway Truck Service")
    fac = _service_facility(db, "Gateway Truck Service")
    claim_id = client.post(
        "/vendor/claims",
        json={"facility_id": str(fac.id), "claimed_name": "Gateway Truck Service"},
        headers=first,
    ).json()["claim_id"]
    import uuid as _uuid

    m13.decide_claim(db, db.get(m13.FacilityClaim, _uuid.UUID(claim_id)), approve=True)

    rival = _headers(client, "shop-f@example.com")
    # a distinct BUSINESS name (Q-5 refuses a near-duplicate in the same metro) —
    # what is claimed is the site's name, which is a different field
    _vendor(client, rival, "Range Line Repair Co")
    resp = client.post(
        "/vendor/claims",
        json={"facility_id": str(fac.id), "claimed_name": "Gateway Truck Service"},
        headers=rival,
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "disputed"


def test_a_food_vendor_gets_no_claimable_search(client, db, live):
    headers = _headers(client, "cook-a@example.com")
    _vendor(client, headers, "Osh Express", vendor_type="food_mobile")
    _service_facility(db, "Gateway Truck Service")
    assert client.get("/vendor/claimable?q=gateway", headers=headers).status_code == 403


def test_a_claim_row_never_forces_a_vendor_to_read_a_uuid(client, db, live):
    headers = _headers(client, "shop-g@example.com")
    _vendor(client, headers, "Gateway Truck Service")
    fac = _service_facility(db, "Gateway Truck Service")
    fac.address = "1400 Range Line Rd"
    client.post(
        "/vendor/claims",
        json={
            "facility_id": str(fac.id),
            "claimed_name": "Gateway Truck Service",
            "content_b64": PDF,
        },
        headers=headers,
    )

    body = client.get("/vendor/claims", headers=headers).json()
    rows = body["claims"]
    assert rows[0]["facility_name"] == "Gateway Truck Service"
    assert rows[0]["facility_address"] == "1400 Range Line Rd"
    assert rows[0]["status"] == "pending"
    assert rows[0]["has_document"] is True


def test_a_claim_row_carries_both_halves_of_the_union(client, db, live):
    headers = _headers(client, "shop-h@example.com")
    _vendor(client, headers, "Gateway Truck Service")
    fac = _service_facility(db, "Gateway Truck Service")
    claim_id = client.post(
        "/vendor/claims",
        json={"facility_id": str(fac.id), "claimed_name": "Gateway Truck Service"},
        headers=headers,
    ).json()["claim_id"]
    import uuid as _uuid

    m13.decide_claim(db, db.get(m13.FacilityClaim, _uuid.UUID(claim_id)), approve=True)
    client.patch(
        f"/vendor/claims/{claim_id}", json={"services_added": ["towing"]}, headers=headers
    )

    row = client.get("/vendor/claims", headers=headers).json()["claims"][0]
    # the portal shows the addition AND what it was added to — E3.2 union, visibly
    assert row["services_ingested"] == ["tire"]
    assert row["services_added"] == ["towing"]
    assert row["services"] == ["tire", "towing"]


def test_a_vendor_cannot_curate_another_vendors_claim(client, db, live):
    owner = _headers(client, "shop-i@example.com")
    _vendor(client, owner, "Gateway Truck Service")
    fac = _service_facility(db, "Gateway Truck Service")
    claim_id = client.post(
        "/vendor/claims",
        json={"facility_id": str(fac.id), "claimed_name": "Gateway Truck Service"},
        headers=owner,
    ).json()["claim_id"]
    import uuid as _uuid

    m13.decide_claim(db, db.get(m13.FacilityClaim, _uuid.UUID(claim_id)), approve=True)

    other = _headers(client, "shop-j@example.com")
    _vendor(client, other, "Somebody Else Repair")
    resp = client.patch(f"/vendor/claims/{claim_id}", json={"hours": "24/7"}, headers=other)
    assert resp.status_code == 404


def test_the_portal_is_never_offered_a_service_the_layer_owns(client, db, live):
    # `scale` feeds the M1 weigh-station layer. A service a claimant could simply
    # tick would put an unverified scale in front of a driver deciding to pull in.
    headers = _headers(client, "shop-k@example.com")
    _vendor(client, headers, "Gateway Truck Service")
    kinds = client.get("/vendor/claims", headers=headers).json()["service_kinds"]
    assert "scale" not in kinds
    assert "tire" in kinds and "wash" in kinds


def test_a_scale_only_site_is_not_a_business_anyone_can_claim(client, db, live):
    # 604 of the 605 facilities carrying a services list in dev are OSM
    # weighbridges. A scale is public infrastructure feeding the M1 layer, not a
    # service business — so it is neither offered in the picker nor accepted.
    headers = _headers(client, "shop-l@example.com")
    _vendor(client, headers, "Gateway Truck Service")
    fac = _service_facility(db, "Gateway Truck Scale", services=["scale"])

    assert client.get("/vendor/claimable?q=gateway", headers=headers).json() == []
    resp = client.post(
        "/vendor/claims",
        json={"facility_id": str(fac.id), "claimed_name": "Gateway Truck Scale"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_a_site_with_a_real_service_alongside_a_scale_is_claimable(client, db, live):
    # E3.2 composites are the norm: a truck stop with a tire bay AND a weighbridge
    # keeps both facts, and the tire bay is what makes it claimable.
    headers = _headers(client, "shop-m@example.com")
    _vendor(client, headers, "Gateway Truck Service")
    _service_facility(db, "Gateway Truck Service", services=["scale", "tire"])

    rows = client.get("/vendor/claimable?q=gateway", headers=headers).json()
    assert len(rows) == 1
    # and the scale is not presented as something they speak for
    assert rows[0]["services"] == ["tire"]

"""AI-CONTEXT: the rest of the vendor portal — self-serve signup, verification,
reputation, promotion editing, and the analytics figure that was lying.

The honesty rules this file defends are the ones the portal's own header states and
that a portal is most tempted to soften, because its reader is the person being
described:

· `sheet_views` was PLATFORM-WIDE and shown to each vendor as their own. Every cook
  saw the same inflated number. Now scoped, and asserted so it cannot drift back.
· The show-up pair and the rating count are the same figures drivers see.
· Verification says what it means: `documents_on_file` is paperwork received, never
  an inspection.
· An upheld report is shown to the vendor, because a suspension that arrives without
  warning is exactly what this portal exists to prevent.
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
    return db


def _account(client, email="cook@example.com"):
    resp = client.post("/auth/register", json={"email": email, "password": "pw-123456"})
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _register(client, headers, **over):
    body = {
        "name": "Ana's Tamales",
        "vendor_type": "food_mobile",
        "metro": "Madison WI",
        "languages": ["es", "en"],
        "halal_disclosure": "no halal claim",
        "halal_answered": True,
    }
    body.update(over)
    return client.post("/vendors/register", json=body, headers=headers)


@pytest.fixture
def cook(client, active):
    headers = _account(client)
    assert _register(client, headers).status_code == 201
    return headers


# --- self-serve signup (owner decision: open, existing guards apply) ---
def test_a_cook_signs_themselves_up_and_starts_unverified(client, active):
    headers = _account(client, "newcook@example.com")
    resp = _register(client, headers)

    assert resp.status_code == 201
    # the ladder starts at the bottom and the pin will say so — no approval queue,
    # because the Q-4 floor, the tier label and Q-8 moderation are the gate
    assert resp.json()["verify_status"] == "unverified"


def test_signing_up_grants_the_vendor_role_and_reaches_the_portal(client, active, db):
    headers = _account(client, "newcook@example.com")
    _register(client, headers)

    profile = client.get("/vendor/profile", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["name"] == "Ana's Tamales"


def test_an_incomplete_signup_is_told_exactly_what_blocks_publishing(client, active, db):
    headers = _account(client, "vague@example.com")
    _register(client, headers, languages=[], halal_answered=False)

    gaps = client.get("/vendor/profile", headers=headers).json()["profile_gaps"]
    assert sorted(gaps) == ["halal_disclosure", "languages"]

    fac = facility.create_facility(db, facility.FacilityType.truck_stop, "Pilot", *MADISON)
    starts = datetime.now(UTC) + timedelta(hours=2)
    resp = client.post(
        "/vendor/appearances",
        json={
            "facility_id": str(fac.id),
            "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(hours=3)).isoformat(),
            "offerings": [{"name": "Tamales", "price_cents": 1200}],
        },
        headers=headers,
    )
    # named gaps, so it can be fixed in one pass rather than guessed at
    assert resp.status_code == 422
    assert sorted(resp.json()["detail"]["missing"]) == ["halal_disclosure", "languages"]


def test_a_second_profile_for_the_same_cook_is_refused(client, cook):
    # Q-5: duplicates merge, never coexist
    assert _register(client, cook).status_code == 409


# --- full profile editing ---
def test_a_cook_edits_every_field_of_their_own_profile(client, cook):
    resp = client.patch(
        "/vendor/profile",
        json={
            "name": "Ana's Tamales & Pozole",
            "vendor_type": "service_center",
            "metro": "Janesville WI",
            "contact_phone": "(608) 555-0142",
            "categories": ["mexican"],
            "languages": ["es"],
        },
        headers=cook,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Ana's Tamales & Pozole"
    assert body["vendor_type"] == "service_center"
    assert body["metro"] == "Janesville WI"
    assert body["contact_phone"] == "6085550142"  # normalised, not as typed


def test_an_unknown_vendor_type_is_refused(client, cook):
    assert (
        client.patch(
            "/vendor/profile", json={"vendor_type": "food_stall"}, headers=cook
        ).status_code
        == 422
    )


# --- verification ---
def test_the_ladder_reports_what_is_on_file_and_nothing_more(client, cook):
    import base64

    before = client.get("/vendor/documents", headers=cook).json()
    assert before["verify_status"] == "unverified"
    assert before["documents"] == []
    assert "food_permit" in before["kinds"] or before["kinds"]

    resp = client.post(
        "/vendor/documents",
        json={
            "kind": before["kinds"][0],
            "content_b64": base64.b64encode(b"a permit").decode(),
            "filename": "permit.pdf",
        },
        headers=cook,
    )
    assert resp.status_code == 201

    after = client.get("/vendor/documents", headers=cook).json()
    assert len(after["documents"]) == 1
    # pending review — uploading is not approval, and the portal must not imply it
    assert after["documents"][0]["review_status"] == "pending"


# --- reputation ---
def test_an_unreviewed_vendor_reads_as_no_reviews_not_zero(client, cook):
    body = client.get("/vendor/reputation", headers=cook).json()
    # a 0.0 average reads as "rated badly" when it means "nobody has said"
    assert body["rating"]["average"] is None
    assert body["rating"]["reviewers"] == 0
    assert body["reviews"] == []


def test_the_show_up_pair_is_the_raw_fraction_drivers_see(client, cook):
    body = client.get("/vendor/reputation", headers=cook).json()
    assert set(body["shows_up"]) == {"confirmed", "published"}
    # no percentage anywhere: a fraction carries its own sample size, and "95%" over
    # two appearances would overstate what anyone knows
    assert "percent" not in str(body).lower()
    assert "rate" not in str(body["shows_up"]).lower()


def test_upheld_reports_and_no_shows_are_shown_to_the_vendor(client, cook):
    body = client.get("/vendor/reputation", headers=cook).json()
    assert body["upheld_reports"] == 0
    assert body["consecutive_no_shows"] == 0
    assert body["publish_suspended"] is False


# --- the analytics figure that was lying ---
def test_sheet_views_count_only_this_vendors_sheet(client, active, db):
    ana = _account(client, "ana@example.com")
    _register(client, ana, name="Ana's Tamales")
    bob = _account(client, "bob@example.com")
    _register(client, bob, name="Bob's BBQ")

    bob_vendor_id = client.get("/vendor/profile", headers=bob).json()["vendor_id"]
    driver = _account(client, "driver@example.com")
    for _ in range(3):
        client.get(f"/vendors/{bob_vendor_id}", headers=driver)

    # Bob was looked at three times. Ana was not looked at at all, and must not be
    # shown Bob's traffic as her own — which is exactly what used to happen.
    assert client.get("/vendor/analytics", headers=bob).json()["sheet_views"] == 3
    assert client.get("/vendor/analytics", headers=ana).json()["sheet_views"] == 0


# --- promotions ---
def _promo(client, headers, text="Fresh tamales at 11", days=1):
    starts = datetime.now(UTC)
    return client.post(
        "/vendor/promotions",
        json={
            "text": text,
            "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(days=days)).isoformat(),
        },
        headers=headers,
    )


def test_a_vendor_edits_their_own_promotion(client, cook):
    promo = _promo(client, cook).json()
    resp = client.patch(
        f"/vendor/promotions/{promo['promotion_id']}",
        json={"text": "Fresh tamales at noon"},
        headers=cook,
    )
    assert resp.status_code == 200
    assert resp.json()["text"] == "Fresh tamales at noon"


def test_editing_a_promotion_never_re_sends_the_alert(client, cook):
    """The alert budget was spent when it was created. An edit that pushed again
    would be a way around the one-per-driver-per-day cap the class is defined by."""
    promo = _promo(client, cook).json()
    resp = client.patch(
        f"/vendor/promotions/{promo['promotion_id']}",
        json={"text": "Now with pozole"},
        headers=cook,
    )
    assert resp.json()["alerts_delivered"] == 0


def test_an_over_long_promotion_is_refused(client, cook):
    promo = _promo(client, cook).json()
    resp = client.patch(
        f"/vendor/promotions/{promo['promotion_id']}",
        json={"text": "x" * (m13.MAX_PROMOTION_CHARS + 1)},
        headers=cook,
    )
    assert resp.status_code == 422


def test_a_vendor_cannot_edit_another_vendors_promotion(client, active):
    ana = _account(client, "ana@example.com")
    _register(client, ana, name="Ana's Tamales")
    promo = _promo(client, ana).json()

    bob = _account(client, "bob@example.com")
    _register(client, bob, name="Bob's BBQ")
    assert (
        client.patch(
            f"/vendor/promotions/{promo['promotion_id']}", json={"text": "mine now"}, headers=bob
        ).status_code
        == 404
    )


# --- the whole portal stays behind the flag ---
def test_every_portal_route_is_dark_while_the_module_is_off(client, db):
    headers = _account(client)
    for path in ("/vendor/profile", "/vendor/menu", "/vendor/documents", "/vendor/reputation"):
        assert client.get(path, headers=headers).status_code == 404, path


def test_the_portal_ships_no_payment_path(client):
    spec = TestClient(app).get("/openapi.json").json()
    portal = {p: v for p, v in spec["paths"].items() if p.startswith("/vendor/")}
    blob = str(portal).lower()
    for forbidden in ("checkout", "payment", "charge", "invoice", "payout", "billing"):
        assert forbidden not in blob, f"{forbidden} reached the vendor portal"


def test_the_portal_never_reads_a_credential_or_grants_a_role(client, cook):
    # the portal manages a business, not an identity — credentials and roles stay
    # where E-D6 put them, behind the admin console's own limits
    spec = TestClient(app).get("/openapi.json").json()
    portal = str({p: v for p, v in spec["paths"].items() if p.startswith("/vendor/")}).lower()
    assert "password" not in portal
    assert "platform_admin" not in portal

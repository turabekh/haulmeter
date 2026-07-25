"""AI-CONTEXT: E-D5 scoped impersonation — "view as vendor".

This is the most dangerous mechanism in the console: it lets one human act as
another. Its safety properties are therefore STRUCTURAL rather than procedural, and
each one is asserted here because each is a place where a plausible refactor would
silently remove it:

· **The session belongs to the ADMIN and merely names the vendor.** Writes attribute
  to the admin because of who owns the session, not because a caller remembered to
  pass an actor.
· **An impersonation token is refused by ordinary authentication.** It cannot reach a
  driver endpoint however it is passed around — which is how "vendors only" (E-D5)
  is enforced rather than merely intended.
· **Reads render the vendor's own screen.** That is the point: "my screen looks
  wrong" is unanswerable otherwise.
· **It expires.** A support session left open is an unlocked door.
· **The vendor sees what support did.** Assisted edits surface on their portal.
· **No bypass.** The Q-4 publish floor applies to an admin publishing on a vendor's
  behalf exactly as it applies to the vendor.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f01_identity.domain.models import Account, AuthSession
from app.foundation.f02_facility import public as facility
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
    return True


def _admin(client, db, email="ops@example.com"):
    resp = client.post("/auth/register", json={"email": email, "password": "pw-123456"})
    identity.attach_role(
        db, db.get(Account, uuid.UUID(resp.json()["account_id"])), identity.Role.platform_admin
    )
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _vendor(client, db, email="cook@example.com", name="Osh Express"):
    resp = client.post("/auth/register", json={"email": email, "password": "pw-123456"})
    account_id = uuid.UUID(resp.json()["account_id"])
    vendor = m13.register_vendor(
        db,
        account_id,
        name,
        m13.VendorType.food_mobile,
        metro="dallas-tx",
        languages=["uz"],
        halal_answered=True,
    )
    return vendor, {"Authorization": f"Bearer {resp.json()['token']}"}


def _impersonate(client, db, admin_headers, vendor):
    resp = client.post(f"/admin/vendors/{vendor.id}/impersonate", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    return resp.json(), {"Authorization": f"Bearer {resp.json()['token']}"}


# --- the structural guarantees ---
def test_the_session_belongs_to_the_admin_and_names_the_vendor(client, db, live):
    # the ordering IS the safety property: writes attribute to the admin because of
    # who owns the session, not because a caller remembered to pass an actor
    headers = _admin(client, db)
    vendor, _ = _vendor(client, db)
    body, _ = _impersonate(client, db, headers, vendor)

    session = db.scalar(select_session(db, body["token"]))
    admin_account = db.get(Account, session.account_id)
    assert admin_account.email == "ops@example.com"
    assert session.impersonating_account_id == vendor.owner_account_id


def select_session(db, token):
    from sqlalchemy import select

    return select(AuthSession).where(AuthSession.token == token)


def test_an_impersonation_token_cannot_reach_a_driver_endpoint(client, db, live):
    # this is how "vendors only" is ENFORCED rather than merely intended
    headers = _admin(client, db)
    vendor, _ = _vendor(client, db)
    _, imp = _impersonate(client, db, headers, vendor)

    assert client.get("/auth/me", headers=imp).status_code == 401
    assert client.get("/money/summary", headers=imp).status_code in (401, 404)


def test_an_impersonation_token_cannot_reach_the_admin_console(client, db, live):
    # an impersonating admin is scoped DOWN, not sideways
    headers = _admin(client, db)
    vendor, _ = _vendor(client, db)
    _, imp = _impersonate(client, db, headers, vendor)

    assert client.get("/admin/overview", headers=imp).status_code == 401


def test_reads_render_the_vendors_own_screen(client, db, live):
    # the whole point — debugging "my screen looks wrong"
    headers = _admin(client, db)
    vendor, vendor_headers = _vendor(client, db)
    _, imp = _impersonate(client, db, headers, vendor)

    theirs = client.get("/vendor/profile", headers=vendor_headers).json()
    ours = client.get("/vendor/profile", headers=imp).json()
    assert ours["vendor_id"] == theirs["vendor_id"] == str(vendor.id)
    assert ours["name"] == theirs["name"]


def test_the_session_expires(client, db, live):
    # a support session left open is an unlocked door
    headers = _admin(client, db)
    vendor, _ = _vendor(client, db)
    body, imp = _impersonate(client, db, headers, vendor)

    assert client.get("/vendor/profile", headers=imp).status_code == 200

    session = db.scalar(select_session(db, body["token"]))
    session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()
    assert client.get("/vendor/profile", headers=imp).status_code == 401


def test_the_time_box_is_thirty_minutes(client, db, live):
    headers = _admin(client, db)
    vendor, _ = _vendor(client, db)
    body, _ = _impersonate(client, db, headers, vendor)
    assert body["ttl_minutes"] == 30


def test_ending_a_session_kills_it_immediately(client, db, live):
    headers = _admin(client, db)
    vendor, _ = _vendor(client, db)
    body, imp = _impersonate(client, db, headers, vendor)

    client.post("/admin/impersonation/end", json={"token": body["token"]}, headers=headers)
    assert client.get("/vendor/profile", headers=imp).status_code == 401


def test_start_and_end_are_both_recorded(client, db, live):
    headers = _admin(client, db)
    vendor, _ = _vendor(client, db)
    body, _ = _impersonate(client, db, headers, vendor)
    client.post("/admin/impersonation/end", json={"token": body["token"]}, headers=headers)

    actions = {a["action"] for a in client.get("/admin/audit", headers=headers).json()}
    assert {"impersonation_start", "impersonation_end"} <= actions


def test_a_deactivated_vendor_cannot_be_impersonated(client, db, live):
    headers = _admin(client, db)
    vendor, _ = _vendor(client, db)
    identity.deactivate_account(db, db.get(Account, vendor.owner_account_id))

    resp = client.post(f"/admin/vendors/{vendor.id}/impersonate", headers=headers)
    assert resp.status_code == 409


def test_impersonation_requires_admin(client, db, live):
    vendor, vendor_headers = _vendor(client, db)
    resp = client.post(f"/admin/vendors/{vendor.id}/impersonate", headers=vendor_headers)
    assert resp.status_code == 403


def test_a_driver_account_is_not_impersonable(db):
    # E-D5 approves vendors only, and the domain refuses at the source rather than
    # relying on no route existing
    driver = identity.register_account(db, "justadriver@x.com", "pw-123456")
    admin_account = identity.register_account(db, "adm@x.com", "pw-123456")
    with pytest.raises(identity.ImpersonationNotPermitted):
        identity.start_impersonation(db, admin_account, driver, is_vendor=False)


# --- assisted writes attribute to the admin, and the vendor is told ---
def test_an_assisted_edit_attributes_to_the_admin_not_the_vendor(client, db, live):
    headers = _admin(client, db)
    vendor, _ = _vendor(client, db)
    _, imp = _impersonate(client, db, headers, vendor)

    client.patch("/vendor/profile", json={"languages": ["uz", "ru"]}, headers=imp)

    entries = client.get("/admin/audit?action=assisted_profile_edit", headers=headers).json()
    assert entries[0]["actor"] == "ops@example.com"  # the admin, never the vendor
    assert entries[0]["before"]["languages"] == ["uz"]
    assert entries[0]["after"]["languages"] == ["uz", "ru"]


def test_the_vendor_sees_that_support_edited_their_profile(client, db, live):
    # derived from the audit log via target_ref — one source of truth, no extra
    # columns on three tables
    headers = _admin(client, db)
    vendor, vendor_headers = _vendor(client, db)
    _, imp = _impersonate(client, db, headers, vendor)
    client.patch("/vendor/profile", json={"languages": ["uz", "ru"]}, headers=imp)

    theirs = client.get("/vendor/profile", headers=vendor_headers).json()
    assert theirs["assisted"]
    assert theirs["assisted"][0]["action"] == "profile_edit"


def test_a_vendors_own_edit_records_nothing_assisted(client, db, live):
    # an audit entry for every ordinary edit would bury the ones that matter
    headers = _admin(client, db)
    vendor, vendor_headers = _vendor(client, db)
    client.patch("/vendor/profile", json={"languages": ["en"]}, headers=vendor_headers)

    assert client.get("/vendor/profile", headers=vendor_headers).json()["assisted"] == []
    assert client.get("/admin/audit?action=assisted_profile_edit", headers=headers).json() == []


def test_an_assisted_publish_still_obeys_the_publish_floor(client, db, live):
    # Q-4 applies to an admin publishing on a vendor's behalf exactly as it applies
    # to the vendor — attribution, never bypass
    headers = _admin(client, db)
    account = identity.register_account(db, "incomplete@x.com", "pw-123456")
    vendor = m13.register_vendor(
        db, account.id, "Incomplete Cook", m13.VendorType.food_mobile, metro="waco-tx"
    )
    fac = facility.create_facility(db, facility.FacilityType.truck_stop, "Stop", *DALLAS)
    _, imp = _impersonate(client, db, headers, vendor)

    start = datetime.now(UTC)
    resp = client.post(
        "/vendor/appearances",
        json={
            "facility_id": str(fac.id),
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(hours=3)).isoformat(),
            "offerings": [{"name": "Osh", "price_cents": 1200}],
        },
        headers=imp,
    )
    assert resp.status_code == 422
    assert set(resp.json()["detail"]["missing"]) >= {"languages", "halal_disclosure"}


def test_an_assisted_publish_is_recorded_when_it_succeeds(client, db, live):
    headers = _admin(client, db)
    vendor, _ = _vendor(client, db)
    fac = facility.create_facility(db, facility.FacilityType.truck_stop, "Stop2", *DALLAS)
    _, imp = _impersonate(client, db, headers, vendor)

    start = datetime.now(UTC)
    resp = client.post(
        "/vendor/appearances",
        json={
            "facility_id": str(fac.id),
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(hours=3)).isoformat(),
            "offerings": [{"name": "Osh", "price_cents": 1200}],
        },
        headers=imp,
    )
    assert resp.status_code == 201
    entries = client.get("/admin/audit?action=assisted_appearance_publish", headers=headers).json()
    assert entries[0]["actor"] == "ops@example.com"


# --- the vendor detail page ---
def test_the_detail_page_carries_everything_about_one_vendor(client, db, live):
    headers = _admin(client, db)
    vendor, _ = _vendor(client, db)

    body = client.get(f"/admin/vendors/{vendor.id}/detail", headers=headers).json()
    assert body["name"] == "Osh Express"
    assert body["shows_up"] == {"confirmed": 0, "published": 0}
    assert body["reviews"] == {"average": None, "reviewers": 0}
    assert body["upheld_reports"] == 0
    assert body["profile_gaps"] == []
    assert "audit" in body

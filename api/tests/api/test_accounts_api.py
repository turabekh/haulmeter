"""AI-CONTEXT: E-D6 account management — the operator's account powers and, more
importantly, their limits.

An admin can create, edit, reset a credential, and deactivate. They can never read a
password, never set a permanent one, and never delete. Each of those limits is
asserted here rather than assumed, because every one of them is a place where a
well-meaning future change would quietly make the product less trustworthy:

· **No hard delete.** Accounts reference money, claims and evidence. Erasing one
  tears holes in records a third party may need to verify, so deletion is a
  retention workflow (PRD §17 Q16), not a button.
· **A temporary password, returned once.** Support that can read a password is
  support that can be social-engineered into surrendering one.
· **Deactivation bites immediately**, including on anyone already signed in.
· **platform_admin needs an explicit confirm** — it hands over every power in the
  admin router, including the power to grant it onward.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f01_identity.domain.models import Account
from app.main import app


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _admin(client, db, email="ops@example.com"):
    resp = client.post("/auth/register", json={"email": email, "password": "pw-123456"})
    identity.attach_role(
        db, db.get(Account, uuid.UUID(resp.json()["account_id"])), identity.Role.platform_admin
    )
    return {"Authorization": f"Bearer {resp.json()['token']}"}, resp.json()["account_id"]


def _create(client, headers, email="driver@example.com", role="driver", name=None):
    return client.post(
        "/admin/accounts",
        json={"email": email, "role": role, "display_name": name},
        headers=headers,
    )


# --- the guardrails ---
def test_there_is_no_hard_delete_endpoint():
    # accounts reference money, claims and evidence; deletion is a retention
    # workflow (PRD §17 Q16), never a button
    spec = app.openapi()["paths"]
    for path, methods in spec.items():
        if path.startswith("/admin/accounts"):
            assert "delete" not in {m.lower() for m in methods}


def test_no_endpoint_ever_reads_a_password_back():
    # the temporary password is returned ONCE at creation/reset and is not
    # retrievable afterwards
    spec = app.openapi()["paths"]
    readable = [p for p in spec if "password" in p or "credential" in p]
    for path in readable:
        assert "get" not in {m.lower() for m in spec[path]}


def test_account_detail_never_exposes_a_credential(client, db):
    headers, _ = _admin(client, db)
    account_id = _create(client, headers).json()["account_id"]

    body = client.get(f"/admin/accounts/{account_id}", headers=headers).json()
    serialized = str(body)
    assert "secret_ref" not in serialized
    assert "temporary_password" not in serialized


def test_accounts_require_admin(client, db):
    resp = client.post("/auth/register", json={"email": "nobody@x.com", "password": "pw-123456"})
    headers = {"Authorization": f"Bearer {resp.json()['token']}"}
    assert client.get("/admin/accounts", headers=headers).status_code == 403


# --- create: the phone-onboarding case ---
def test_creating_an_account_returns_a_temporary_password_once(client, db):
    headers, _ = _admin(client, db)
    resp = _create(client, headers, name="Bek")

    assert resp.status_code == 201
    body = resp.json()
    assert body["temporary_password"]
    assert body["must_change_credential"] is True
    assert body["display_name"] == "Bek"

    # and it is gone from every subsequent read
    later = client.get(f"/admin/accounts/{body['account_id']}", headers=headers).json()
    assert "temporary_password" not in later


def test_the_temporary_password_works_and_forces_a_change(client, db):
    headers, _ = _admin(client, db)
    body = _create(client, headers, "newdriver@example.com").json()

    account = db.get(Account, uuid.UUID(body["account_id"]))
    assert identity.authenticate(db, "newdriver@example.com", body["temporary_password"])
    assert identity.must_change_credential(db, account) is True

    identity.complete_credential_change(db, account, "their-own-password")
    assert identity.must_change_credential(db, account) is False
    assert identity.authenticate(db, "newdriver@example.com", "their-own-password")


def test_platform_admin_cannot_be_granted_at_creation(client, db):
    # it is granted deliberately, afterwards, with a confirm — never as a field on a
    # creation form somebody tabs through
    headers, _ = _admin(client, db)
    resp = _create(client, headers, "sneaky@x.com", role="platform_admin")
    assert resp.status_code == 422


def test_a_duplicate_email_is_refused(client, db):
    headers, _ = _admin(client, db)
    _create(client, headers, "dupe@example.com")
    assert _create(client, headers, "dupe@example.com").status_code == 409


# --- edit ---
def test_editing_an_account_updates_the_profile_and_audits_before_and_after(client, db):
    headers, _ = _admin(client, db)
    account_id = _create(client, headers, "edit@example.com").json()["account_id"]

    resp = client.patch(
        f"/admin/accounts/{account_id}",
        json={"display_name": "Bek T", "mc_number": "123456", "plate_state": "FL"},
        headers=headers,
    )
    assert resp.json()["profile"]["mc_number"] == "123456"

    audit = client.get("/admin/audit?action=account_edit", headers=headers).json()
    # the account had no driver profile at all before this edit, and the log says so
    # rather than inventing an empty one
    assert audit[0]["before"]["profile"] is None
    assert audit[0]["after"]["profile"]["mc_number"] == "123456"


def test_the_account_page_carries_its_own_audit_trail(client, db):
    # "what has support done to this person" is answerable where it matters
    headers, _ = _admin(client, db)
    account_id = _create(client, headers, "trail@example.com").json()["account_id"]
    client.patch(f"/admin/accounts/{account_id}", json={"display_name": "X"}, headers=headers)

    body = client.get(f"/admin/accounts/{account_id}", headers=headers).json()
    assert {a["action"] for a in body["audit"]} >= {"account_create", "account_edit"}


# --- credential reset ---
def test_a_reset_issues_a_new_temporary_credential(client, db):
    headers, _ = _admin(client, db)
    created = _create(client, headers, "reset@example.com").json()
    account = db.get(Account, uuid.UUID(created["account_id"]))
    identity.complete_credential_change(db, account, "chosen-password")

    resp = client.post(f"/admin/accounts/{created['account_id']}/reset-credential", headers=headers)
    temporary = resp.json()["temporary_password"]

    assert temporary != created["temporary_password"]
    assert identity.must_change_credential(db, account) is True
    assert identity.authenticate(db, "reset@example.com", temporary)
    # and the old password is dead
    assert identity.authenticate(db, "reset@example.com", "chosen-password") is None


def test_the_audit_records_the_reset_but_never_the_credential(client, db):
    headers, _ = _admin(client, db)
    created = _create(client, headers, "auditreset@example.com").json()
    resp = client.post(f"/admin/accounts/{created['account_id']}/reset-credential", headers=headers)

    audit = client.get("/admin/audit?action=account_credential_reset", headers=headers).json()
    assert audit[0]["after"] == {"must_change": True}
    assert resp.json()["temporary_password"] not in str(audit)


# --- deactivate / reactivate ---
def test_deactivation_blocks_login_and_kills_live_sessions(client, db):
    headers, _ = _admin(client, db)
    created = _create(client, headers, "gone@example.com").json()
    account = db.get(Account, uuid.UUID(created["account_id"]))
    session = identity.create_session(db, account)

    client.post(f"/admin/accounts/{created['account_id']}/deactivate", headers=headers)

    with pytest.raises(identity.AccountInactive):
        identity.authenticate(db, "gone@example.com", created["temporary_password"])
    # deactivation that took 30 days to reach anyone already signed in would be
    # theatre, so live sessions die with the account
    assert identity.resolve_session(db, session.token) is None


def test_deactivation_preserves_every_row_the_account_points_at(client, db):
    headers, _ = _admin(client, db)
    created = _create(client, headers, "keep@example.com").json()
    account = db.get(Account, uuid.UUID(created["account_id"]))
    identity.upsert_driver_profile(db, account, mc_number="999999")

    client.post(f"/admin/accounts/{created['account_id']}/deactivate", headers=headers)

    body = client.get(f"/admin/accounts/{created['account_id']}", headers=headers).json()
    assert body["active"] is False
    assert body["profile"]["mc_number"] == "999999"  # a locked door, not an erasure


def test_reactivation_restores_login(client, db):
    headers, _ = _admin(client, db)
    created = _create(client, headers, "back@example.com").json()
    client.post(f"/admin/accounts/{created['account_id']}/deactivate", headers=headers)
    client.post(f"/admin/accounts/{created['account_id']}/reactivate", headers=headers)

    assert identity.authenticate(db, "back@example.com", created["temporary_password"])


def test_an_admin_cannot_deactivate_themselves(client, db):
    # locking yourself out mid-incident helps nobody
    headers, account_id = _admin(client, db)
    resp = client.post(f"/admin/accounts/{account_id}/deactivate", headers=headers)
    assert resp.status_code == 409


# --- roles ---
def test_granting_platform_admin_requires_an_explicit_confirm(client, db):
    # it hands over every power in the admin router, including granting it onward
    headers, _ = _admin(client, db)
    account_id = _create(client, headers, "promote@example.com").json()["account_id"]

    refused = client.post(
        f"/admin/accounts/{account_id}/roles",
        json={"role": "platform_admin", "grant": True},
        headers=headers,
    )
    assert refused.status_code == 409
    assert refused.json()["detail"]["error"] == "confirm_required"

    granted = client.post(
        f"/admin/accounts/{account_id}/roles",
        json={"role": "platform_admin", "grant": True, "confirm": True},
        headers=headers,
    )
    assert "platform_admin" in granted.json()["roles"]


def test_the_admin_grant_is_the_loudest_entry_in_the_log(client, db):
    headers, _ = _admin(client, db)
    account_id = _create(client, headers, "loud@example.com").json()["account_id"]
    client.post(
        f"/admin/accounts/{account_id}/roles",
        json={"role": "platform_admin", "grant": True, "confirm": True},
        headers=headers,
    )

    # its own action name, so it can be filtered for and alerted on
    audit = client.get("/admin/audit?action=account_role_admin", headers=headers).json()
    assert audit[0]["after"]["roles"] == ["driver", "platform_admin"]


def test_an_ordinary_role_needs_no_confirm(client, db):
    headers, _ = _admin(client, db)
    account_id = _create(client, headers, "vendorrole@example.com").json()["account_id"]
    resp = client.post(
        f"/admin/accounts/{account_id}/roles",
        json={"role": "vendor", "grant": True},
        headers=headers,
    )
    assert "vendor" in resp.json()["roles"]


def test_a_role_can_be_revoked(client, db):
    headers, _ = _admin(client, db)
    account_id = _create(client, headers, "revoke@example.com").json()["account_id"]
    client.post(
        f"/admin/accounts/{account_id}/roles",
        json={"role": "vendor", "grant": True},
        headers=headers,
    )
    resp = client.post(
        f"/admin/accounts/{account_id}/roles",
        json={"role": "vendor", "grant": False},
        headers=headers,
    )
    assert "vendor" not in resp.json()["roles"]


def test_an_admin_cannot_revoke_their_own_admin_role(client, db):
    headers, account_id = _admin(client, db)
    resp = client.post(
        f"/admin/accounts/{account_id}/roles",
        json={"role": "platform_admin", "grant": False, "confirm": True},
        headers=headers,
    )
    assert resp.status_code == 409


# --- search ---
def test_search_matches_the_facts_an_operator_actually_has(client, db):
    # an email, a name, an MC number or a plate — a directory that only matches
    # email is useless to someone holding a driver's paperwork
    headers, _ = _admin(client, db)
    created = _create(client, headers, "findme@example.com", name="Bek Tashkent").json()
    client.patch(
        f"/admin/accounts/{created['account_id']}",
        json={"mc_number": "778899", "plate_number": "4XN2291"},
        headers=headers,
    )

    for term in ("findme", "Tashkent", "778899", "4XN2291"):
        found = client.get(f"/admin/accounts?q={term}", headers=headers).json()
        assert created["account_id"] in [a["account_id"] for a in found], term


def test_search_filters_by_role(client, db):
    headers, _ = _admin(client, db)
    _create(client, headers, "adriver@example.com")
    found = client.get("/admin/accounts?role=platform_admin", headers=headers).json()
    assert all("platform_admin" in a["roles"] for a in found)


def test_an_unknown_role_filter_is_refused(client, db):
    headers, _ = _admin(client, db)
    assert client.get("/admin/accounts?role=wizard", headers=headers).status_code == 422

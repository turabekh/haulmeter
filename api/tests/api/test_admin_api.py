"""AI-CONTEXT: HTTP API tests for the F14 admin console. TestClient with get_db
overridden. Proves the platform_admin gate and the flag/moderation surfaces.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f13_flags import public as flags
from app.main import app


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _register(client, email):
    resp = client.post("/auth/register", json={"email": email, "password": "pw-123456"})
    assert resp.status_code == 201
    return resp.json()["account_id"], {"Authorization": f"Bearer {resp.json()['token']}"}


def _make_admin(db, account_id):
    from app.foundation.f01_identity.domain.models import Account

    acct = db.get(Account, uuid.UUID(account_id))
    identity.attach_role(db, acct, identity.Role.platform_admin)


def test_flags_requires_admin(client, db):
    # a plain driver is refused the admin surface
    _, headers = _register(client, "driver@example.com")
    assert client.get("/admin/flags", headers=headers).status_code == 403


def test_admin_lists_and_toggles_flags(client, db):
    account_id, headers = _register(client, "ops@example.com")
    _make_admin(db, account_id)
    # a gate-free flag we can toggle; a gated one that can't activate
    flags.register_flag(db, "free_flag", description="no gates")
    flags.register_flag(db, "gated_flag", description="needs a gate")
    flags.add_gate(db, "gated_flag", "legal_signoff")

    listing = client.get("/admin/flags", headers=headers)
    assert listing.status_code == 200
    by_key = {f["key"]: f for f in listing.json()}
    assert by_key["free_flag"]["can_activate"] is True
    assert by_key["gated_flag"]["can_activate"] is False
    assert by_key["gated_flag"]["gates"][0]["name"] == "legal_signoff"

    # enable the free flag; the gated one is blocked (409) until its gate is met
    on = client.post("/admin/flags/free_flag/enable", headers=headers)
    assert on.status_code == 200 and on.json()["enabled"] is True
    blocked = client.post("/admin/flags/gated_flag/enable", headers=headers)
    assert blocked.status_code == 409

    off = client.post("/admin/flags/free_flag/disable", headers=headers)
    assert off.json()["enabled"] is False


def test_admin_views_listed(client, db):
    account_id, headers = _register(client, "ops@example.com")
    _make_admin(db, account_id)
    from app.foundation.f14_admin import public as admin

    admin.register_admin_view(db, "m03.claims", "m03", "Detention Claims", "/admin/m03/claims")

    resp = client.get("/admin/views", headers=headers)
    assert resp.status_code == 200
    assert any(v["title"] == "Detention Claims" for v in resp.json())

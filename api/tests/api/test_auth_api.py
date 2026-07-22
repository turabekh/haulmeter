"""AI-CONTEXT: HTTP tests for onboarding — the operating authority declared at
signup decides whether detention claims are invoiced to the broker (owner-op) or
exported to a carrier (company driver). TestClient with get_db overridden.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app

DALLAS = (32.7767, -96.7970)


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _claim_mode(client, headers):
    stop_id = client.post(
        "/load",
        json={
            "facility_name": "Dock",
            "lat": DALLAS[0],
            "lon": DALLAS[1],
            "counterparty": "Acme",
            "free_time_minutes": 0,
        },
        headers=headers,
    ).json()["stop_id"]
    client.post(f"/load/{stop_id}/arrive", headers=headers)
    client.post(f"/load/{stop_id}/claim", headers=headers)
    return client.get(f"/load/{stop_id}/claim", headers=headers).json()["mode"]


def test_register_with_own_authority_invoices_claims(client, db):
    reg = client.post(
        "/auth/register",
        json={"email": "op@example.com", "password": "pw-123456", "authority": "own_mc"},
    )
    assert reg.status_code == 201
    headers = {"Authorization": f"Bearer {reg.json()['token']}"}
    assert _claim_mode(client, headers) == "invoice"  # owner-operator -> owed to them


def test_register_without_authority_defaults_to_evidence_only(client, db):
    reg = client.post("/auth/register", json={"email": "co@example.com", "password": "pw-123456"})
    assert reg.status_code == 201
    headers = {"Authorization": f"Bearer {reg.json()['token']}"}
    assert _claim_mode(client, headers) == "evidence_only"  # company driver -> to carrier


def test_register_rejects_unknown_authority(client):
    resp = client.post(
        "/auth/register",
        json={"email": "x@example.com", "password": "pw-123456", "authority": "bogus"},
    )
    assert resp.status_code == 422


def _register(client, email, authority="own_mc"):
    reg = client.post(
        "/auth/register",
        json={"email": email, "password": "pw-123456", "authority": authority},
    )
    return {"Authorization": f"Bearer {reg.json()['token']}"}


def test_verify_authority_gated_off_by_default(client):
    from app.foundation.f13_flags import public as flags

    headers = _register(client, "gated@example.com")
    resp = client.post("/auth/verify-authority", json={"mc_number": "123456"}, headers=headers)
    assert resp.status_code == 403  # flag registered but not enabled
    assert flags is not None


def test_verify_authority_when_enabled_returns_verified(client, db):
    from app.foundation.f01_identity import public as identity
    from app.foundation.f13_flags import public as flags

    headers = _register(client, "verify@example.com")
    identity.register_authority_verification(db)
    flags.enable(db, identity.AUTHORITY_VERIFICATION_FLAG)

    resp = client.post(
        "/auth/verify-authority",
        json={"mc_number": "123456", "dot_number": "1000001"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["verified"] is True
    assert body["verify_status"] == "verified"
    assert body["mc_number"] == "123456"
    assert body["legal_name"]


def test_verify_authority_requires_an_identifier(client, db):
    from app.foundation.f01_identity import public as identity
    from app.foundation.f13_flags import public as flags

    headers = _register(client, "noid@example.com")
    identity.register_authority_verification(db)
    flags.enable(db, identity.AUTHORITY_VERIFICATION_FLAG)

    resp = client.post("/auth/verify-authority", json={}, headers=headers)
    assert resp.status_code == 422


def test_verify_authority_requires_auth(client):
    resp = client.post("/auth/verify-authority", json={"mc_number": "123456"})
    assert resp.status_code == 401


def test_me_reports_authority_and_verification_state(client, db):
    from app.foundation.f01_identity import public as identity
    from app.foundation.f13_flags import public as flags

    headers = _register(client, "me@example.com")
    before = client.get("/auth/me", headers=headers).json()
    assert before["authority"] == "own_mc"
    assert before["verified"] is False
    assert before["verification_enabled"] is False

    identity.register_authority_verification(db)
    flags.enable(db, identity.AUTHORITY_VERIFICATION_FLAG)
    client.post("/auth/verify-authority", json={"mc_number": "123456"}, headers=headers)

    after = client.get("/auth/me", headers=headers).json()
    assert after["verified"] is True
    assert after["verification_enabled"] is True
    assert after["legal_name"]

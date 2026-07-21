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


DALLAS = (32.7767, -96.7970)


def _create_load(client, headers):
    resp = client.post(
        "/load",
        json={
            "facility_name": "Dallas Receiver",
            "lat": DALLAS[0],
            "lon": DALLAS[1],
            "counterparty": "Acme Brokerage",
            "free_time_minutes": 120,
            "rate_cents_per_hour": 7500,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["stop_id"]


def test_admin_analytics_funnel_reflects_real_lifecycle(client, db):
    # the North Star funnel is instrumented in the load lifecycle: driving it
    # end-to-end (create -> arrive -> claim) must show all three steps reached.
    account_id, headers = _register(client, "ops@example.com")
    _make_admin(db, account_id)

    stop_id = _create_load(client, headers)  # load_added
    client.post(f"/load/{stop_id}/arrive", headers=headers)  # arrived
    client.post(f"/load/{stop_id}/claim", headers=headers)  # claim_sent

    resp = client.get("/admin/analytics", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    steps = {s["event"]: s["count"] for s in body["funnel"]["steps"]}
    assert steps == {"load_added": 1, "arrived": 1, "claim_sent": 1}
    assert body["totals"]["load_added"] == 1
    assert body["totals"]["claim_sent"] == 1


def test_admin_analytics_funnel_shows_dropoff(client, db):
    # a driver who creates a load but never arrives drops out after step 1
    account_id, headers = _register(client, "ops@example.com")
    _make_admin(db, account_id)
    _create_load(client, headers)  # load_added only

    body = client.get("/admin/analytics", headers=headers).json()
    steps = {s["event"]: s["count"] for s in body["funnel"]["steps"]}
    assert steps == {"load_added": 1, "arrived": 0, "claim_sent": 0}


def test_admin_config_set_get_and_audited(client, db):
    account_id, headers = _register(client, "ops@example.com")
    _make_admin(db, account_id)

    # empty scope to start
    assert client.get("/admin/config?scope=pricing", headers=headers).json()["entries"] == {}

    # set a runtime config value (e.g. the M6 take rate -> F13 config, §21.8)
    put = client.post(
        "/admin/config",
        json={"key": "m06_take_rate_bps", "value": 1500, "scope": "pricing"},
        headers=headers,
    )
    assert put.status_code == 200 and put.json()["value"] == 1500

    got = client.get("/admin/config?scope=pricing", headers=headers).json()
    assert got["entries"]["m06_take_rate_bps"] == 1500

    # the mutation is in the F14 audit log, attributed to the operator
    from app.foundation.f14_admin import public as admin

    actions = admin.list_actions(db, action="config_set")
    assert len(actions) == 1
    assert actions[0].detail["key"] == "m06_take_rate_bps"
    assert str(actions[0].actor_account_id) == account_id


def test_admin_audit_log_records_flag_and_config_changes(client, db):
    account_id, headers = _register(client, "ops@example.com")
    _make_admin(db, account_id)
    flags.register_flag(db, "free_flag", description="no gates")

    # two operator mutations: a flag enable and a config edit
    client.post("/admin/flags/free_flag/enable", headers=headers)
    client.post(
        "/admin/config",
        json={"key": "m06_take_rate_bps", "value": 1500, "scope": "pricing"},
        headers=headers,
    )

    log = client.get("/admin/audit", headers=headers)
    assert log.status_code == 200
    rows = log.json()
    actions = [r["action"] for r in rows]
    assert "flag_enable" in actions
    assert "config_set" in actions
    # each row is attributed to the operator's email
    assert all(r["actor"] == "ops@example.com" for r in rows)
    cfg_row = next(r for r in rows if r["action"] == "config_set")
    assert cfg_row["detail"]["key"] == "m06_take_rate_bps"


def test_admin_audit_requires_admin(client, db):
    _, headers = _register(client, "driver@example.com")
    assert client.get("/admin/audit", headers=headers).status_code == 403


def test_admin_analytics_and_config_require_admin(client, db):
    _, headers = _register(client, "driver@example.com")
    assert client.get("/admin/analytics", headers=headers).status_code == 403
    assert client.get("/admin/config", headers=headers).status_code == 403
    assert (
        client.post("/admin/config", json={"key": "x", "value": 1}, headers=headers).status_code
        == 403
    )

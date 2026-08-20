"""AI-CONTEXT: who signed in, when, from where — and what they did (§23 entry 234).

THE TRAP THIS SLICE EXISTS AROUND. `f01.login_attempt` carries a `client_ip` and looks
exactly like a login history. It is a THROTTLE: it records failures only, prunes itself on
every write, and `clear_failed_logins` deletes a driver's rows the instant they get in.
Production held ONE row against 236 live sessions. An admin screen built on it would have
been confidently, permanently empty — and it would have LOOKED like it was working.

So the successes go in their own table, and these tests hold the three properties that
make it worth having: it records the success, it keeps the address and device, and it
survives the very call that empties the throttle.
"""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f14_admin import public as admin
from app.main import app


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


UA = "Mozilla/5.0 (Linux; Android 13; SM-A536B) AppleWebKit/537.36"
HDRS = {"User-Agent": UA, "X-Forwarded-For": "203.0.113.7"}


def _register(client, email):
    r = client.post("/auth/register", json={"email": email, "password": "pw-123456"}, headers=HDRS)
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()["account_id"])


def test_registering_is_recorded_as_a_sign_in(client, db):
    account_id = _register(client, "trail-reg@example.com")

    events = identity.recent_logins(db, account_id)

    assert [e.kind for e in events] == [identity.LOGIN_REGISTER]
    assert events[0].user_agent == UA


def test_a_successful_login_is_recorded_with_address_and_device(client, db):
    account_id = _register(client, "trail-login@example.com")
    r = client.post(
        "/auth/login", json={"email": "trail-login@example.com", "password": "pw-123456"},
        headers=HDRS,
    )
    assert r.status_code == 200, r.text

    events = identity.recent_logins(db, account_id)

    assert [e.kind for e in events] == [identity.LOGIN_LOGIN, identity.LOGIN_REGISTER]
    assert events[0].client_ip == "203.0.113.7"
    assert events[0].user_agent == UA


def test_it_survives_the_call_that_empties_the_throttle(client, db):
    """THE WHOLE POINT. `clear_failed_logins` runs on every successful login and deletes
    that driver's throttle rows — which is why the throttle can never answer this
    question. The history must be untouched by it."""
    account_id = _register(client, "trail-clear@example.com")
    client.post(
        "/auth/login", json={"email": "trail-clear@example.com", "password": "pw-123456"},
        headers=HDRS,
    )
    identity.clear_failed_logins(db, "trail-clear@example.com")

    assert len(identity.recent_logins(db, account_id)) == 2


def test_a_failed_login_is_not_a_sign_in(client, db):
    account_id = _register(client, "trail-bad@example.com")
    r = client.post(
        "/auth/login", json={"email": "trail-bad@example.com", "password": "wrong-pw-000"},
        headers=HDRS,
    )
    assert r.status_code == 401

    # the register only. A refused attempt belongs to the throttle, not to the history —
    # a list of sign-ins that includes people who did not get in answers a different
    # question than the one an operator is asking
    assert [e.kind for e in identity.recent_logins(db, account_id)] == [identity.LOGIN_REGISTER]


def test_a_long_user_agent_is_truncated_rather_than_refused(client, db):
    r = client.post(
        "/auth/register",
        json={"email": "trail-longua@example.com", "password": "pw-123456"},
        headers={"User-Agent": "x" * 900, "X-Forwarded-For": "203.0.113.9"},
    )
    assert r.status_code == 201, "a verbose browser must never fail a sign-in"
    account_id = uuid.UUID(r.json()["account_id"])
    assert len(identity.recent_logins(db, account_id)[0].user_agent) == 300


def test_the_admin_page_shows_logins_and_activity_apart(client, db):
    """Three trails, kept separate: what an OPERATOR did to them, when THEY got in, and
    what they DID. Merging them would lose what makes each one answerable."""
    account_id = _register(client, "trail-admin@example.com")
    admin.emit(db, "load_added", "m03", datetime.now(UTC), account_id=account_id)

    account = db.get(identity.Account, account_id)
    identity.attach_role(db, account, identity.Role.platform_admin)
    tok = client.post(
        "/auth/login", json={"email": "trail-admin@example.com", "password": "pw-123456"},
        headers=HDRS,
    ).json()["token"]

    body = client.get(
        f"/admin/accounts/{account_id}", headers={"Authorization": f"Bearer {tok}"}
    ).json()

    assert [e["kind"] for e in body["logins"]] == [identity.LOGIN_LOGIN, identity.LOGIN_REGISTER]
    assert body["logins"][0]["client_ip"] == "203.0.113.7"
    assert [e["event"] for e in body["activity"]] == ["load_added"]
    assert "audit" in body, "the operator trail stays its own list"


def test_retention_is_bounded_and_stated(db):
    # personal data about where people were. An unbounded PII table is a liability that
    # grows whether anyone reads it or not, so the window is a stated constant.
    assert identity.LOGIN_EVENT_RETENTION_DAYS == 180

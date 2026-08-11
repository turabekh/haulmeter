"""The password a driver can actually change (D1–D4).

`complete_credential_change` had zero production callers, which made three finished pieces
of work inert — revocation, the floor, the rehash — and inverted what `reset_credential`'s
docstring promises: an admin issued a temporary password, the driver was never told to
replace it and could not, so the temporary became the permanent one and the admin knew a
working credential indefinitely.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f01_identity.domain import service as identity_service
from app.main import app

EMAIL = "driver@example.com"
OLD = "pw-123456"
NEW = "a-better-password"
IP = "203.0.113.9"


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _signed_in(client, email=EMAIL, password=OLD):
    body = client.post("/auth/register", json={"email": email, "password": password}).json()
    return body["token"], {"Authorization": f"Bearer {body['token']}"}


def _change(client, headers, current=OLD, new=NEW, ip=IP):
    return client.post(
        "/auth/password",
        json={"current_password": current, "new_password": new},
        headers={**headers, "X-Forwarded-For": ip},
    )


def _login(client, email=EMAIL, password=OLD):
    return client.post("/auth/login", json={"email": email, "password": password})


# --- the happy path ---
def test_a_correct_current_password_changes_it(client, db):
    _, headers = _signed_in(client)

    assert _change(client, headers).status_code == 200

    assert _login(client, password=NEW).status_code == 200
    assert _login(client, password=OLD).status_code == 401


def test_the_caller_keeps_their_seat(client, db):
    """Being signed out at the moment you change a credential reads as "that failed"."""
    token, headers = _signed_in(client)

    _change(client, headers)

    assert client.get("/auth/me", headers=headers).status_code == 200


def test_every_other_session_ends_and_the_driver_is_told_how_many(client, db):
    _, headers = _signed_in(client)
    other = client.post("/auth/login", json={"email": EMAIL, "password": OLD}).json()["token"]
    another = client.post("/auth/login", json={"email": EMAIL, "password": OLD}).json()["token"]

    resp = _change(client, headers)

    assert resp.json()["other_sessions_ended"] == 2
    for token in (other, another):
        assert (
            client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
        )


# --- the control that matters most ---
def test_a_stolen_token_alone_cannot_seize_the_account(client, db):
    """The one control between a leaked session and permanent takeover."""
    _, headers = _signed_in(client)

    resp = _change(client, headers, current="not-the-password")

    assert resp.status_code == 401
    assert _login(client, password=OLD).status_code == 200  # unchanged
    assert _login(client, password=NEW).status_code == 401


def test_wrong_current_passwords_are_counted_and_eventually_throttled(client, db):
    _, headers = _signed_in(client)
    limit = identity_service.CHANGE_MAX_PER_IDENTIFIER

    for _ in range(limit):
        assert _change(client, headers, current="wrong").status_code == 401
    blocked = _change(client, headers, current="wrong")

    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0


def test_mistyping_the_current_password_does_not_lock_you_out_of_LOGIN(client, db):
    """The discriminator's whole job, breaching the REAL login ceiling.

    The per-IP login limit is the higher of login's two, so the flood is taken past THAT —
    a count under it would pass with the counters merged and prove nothing.
    """
    _, headers = _signed_in(client)
    from app.foundation.f13_flags import public as flags

    flood = identity_service.LOGIN_MAX_PER_IP + 5
    flags.set_config(db, identity_service.CONFIG_CHANGE_MAX_IP, flood, scope="security")
    flags.set_config(db, identity_service.CONFIG_CHANGE_MAX_IDENTIFIER, flood, scope="security")
    for _ in range(flood):
        assert _change(client, headers, current="wrong").status_code == 401

    assert _login(client, password=OLD).status_code == 200


def test_failed_logins_do_not_consume_the_change_budget(client, db):
    """...and the reverse, so the two counters are genuinely separate."""
    _, headers = _signed_in(client)
    for _ in range(identity_service.LOGIN_MAX_PER_IDENTIFIER):
        _login(client, password="wrong")

    assert _change(client, headers).status_code == 200


# --- the floor ---
def test_a_new_password_below_the_floor_is_refused(client, db):
    _, headers = _signed_in(client)

    resp = _change(client, headers, new="sevench")

    assert resp.status_code == 422
    assert _login(client, password=OLD).status_code == 200


# --- must_change: the flag, and the flow it unblocks ---
def test_a_temporary_password_can_finally_be_replaced(client, db):
    """The whole point. An admin issues one; the driver replaces it themselves."""
    account = identity.register_account(db, "reset-me@example.com", OLD)
    temporary = identity.reset_credential(db, account)
    assert identity.must_change_credential(db, account) is True

    signin = client.post(
        "/auth/login", json={"email": "reset-me@example.com", "password": temporary}
    ).json()
    assert signin["must_change_password"] is True
    headers = {"Authorization": f"Bearer {signin['token']}"}

    changed = client.post(
        "/auth/password",
        json={"current_password": temporary, "new_password": NEW},
        headers=headers,
    )

    assert changed.status_code == 200
    assert identity.must_change_credential(db, account) is False
    assert (
        client.post(
            "/auth/login", json={"email": "reset-me@example.com", "password": temporary}
        ).status_code
        == 401
    )


def test_a_temporary_password_is_still_required_to_change_itself(client, db):
    """No exception for `must_change` — the driver holding it knows it."""
    account = identity.register_account(db, "forced@example.com", OLD)
    temporary = identity.reset_credential(db, account)
    signin = client.post(
        "/auth/login", json={"email": "forced@example.com", "password": temporary}
    ).json()

    resp = client.post(
        "/auth/password",
        json={"current_password": "guessed", "new_password": NEW},
        headers={"Authorization": f"Bearer {signin['token']}"},
    )

    assert resp.status_code == 401


# --- D4: the flag survives a cold start ---
def test_a_cold_start_with_an_existing_token_still_learns_the_flag(client, db):
    """THE test. Sessions last 30 days: a driver who signs in with a temporary password and
    reopens the app next morning never sees `/login` again."""
    account = identity.register_account(db, "cold@example.com", OLD)
    temporary = identity.reset_credential(db, account)
    token = client.post(
        "/auth/login", json={"email": "cold@example.com", "password": temporary}
    ).json()["token"]

    # no login this time — just the call a cold start makes
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()

    assert me["must_change_password"] is True


def test_an_ordinary_account_reports_the_flag_as_false(client, db):
    _, headers = _signed_in(client, email="ordinary@example.com")

    assert client.get("/auth/me", headers=headers).json()["must_change_password"] is False


def test_changing_the_password_clears_the_flag_on_both_surfaces(client, db):
    account = identity.register_account(db, "clears@example.com", OLD)
    temporary = identity.reset_credential(db, account)
    signin = client.post(
        "/auth/login", json={"email": "clears@example.com", "password": temporary}
    ).json()
    headers = {"Authorization": f"Bearer {signin['token']}"}

    client.post(
        "/auth/password",
        json={"current_password": temporary, "new_password": NEW},
        headers=headers,
    )

    assert client.get("/auth/me", headers=headers).json()["must_change_password"] is False
    fresh = client.post(
        "/auth/login", json={"email": "clears@example.com", "password": NEW}
    ).json()
    assert fresh["must_change_password"] is False


def test_it_needs_a_session(client, db):
    assert client.post(
        "/auth/password", json={"current_password": OLD, "new_password": NEW}
    ).status_code == 401

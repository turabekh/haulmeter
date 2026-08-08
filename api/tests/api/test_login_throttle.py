"""F-07 — nothing counted a failed login.

No rate limiter, no lockout, no attempt counter anywhere in the application, against a
live product with real driver accounts on one VM with no monitoring. Two attacks, and
they need two different defences:

  1. Credential stuffing, unbounded — answered by counting per identifier and per IP.
  2. CPU exhaustion. `authenticate` runs Argon2, deliberately memory-hard and slow, so a
     few hundred concurrent POSTs take the box down with NO credentials. A per-identifier
     limit cannot help — the attacker uses a different email every time.

The test that matters most is the one asserting the throttle rejects BEFORE any password
is verified. A throttle that counts correctly and still pays for the hash stops the
stuffing and leaves the denial-of-service exactly as it was.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f01_identity.domain import service as identity_service
from app.foundation.f13_flags import public as flags
from app.main import app

EMAIL = "driver@example.com"
PASSWORD = "pw-123456"
MAX = identity_service.LOGIN_MAX_PER_IDENTIFIER


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def account(db):
    return identity.register_account(db, EMAIL, PASSWORD)


def _login(client, email=EMAIL, password="wrong-password", ip="203.0.113.7"):
    return client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"X-Forwarded-For": ip},
    )


def test_a_wrong_password_still_returns_401_until_the_limit(client: TestClient, account):
    for _ in range(MAX):
        assert _login(client).status_code == 401


def test_the_limit_locks_the_identifier_out_with_retry_after(client: TestClient, account):
    for _ in range(MAX):
        _login(client)
    blocked = _login(client)
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0


def test_the_lockout_also_blocks_the_CORRECT_password(client: TestClient, account):
    # the point of a throttle: an attacker who guesses right on attempt six still waits
    for _ in range(MAX):
        _login(client)
    assert _login(client, password=PASSWORD).status_code == 429


def test_the_throttle_rejects_before_any_password_is_verified(
    client: TestClient, account, monkeypatch
):
    # THE test. If this fails, credential stuffing is bounded and the CPU-exhaustion
    # vector the finding actually names is untouched — every rejected attempt would
    # still pay for a full Argon2 verify.
    for _ in range(MAX):
        _login(client)

    calls = []
    handler = identity.get_handler(identity.MethodType.password)
    real_verify = handler.verify

    def counting_verify(secret_ref, password):
        calls.append(password)
        return real_verify(secret_ref, password)

    monkeypatch.setattr(handler, "verify", counting_verify)
    assert _login(client).status_code == 429
    assert calls == [], "a throttled request must never reach the hash"


def test_a_success_clears_the_lockout(client: TestClient, account):
    for _ in range(MAX - 1):
        _login(client)
    assert _login(client, password=PASSWORD).status_code == 200
    # the counter is reset, so the next wrong guess is attempt one and not attempt five
    for _ in range(MAX - 1):
        assert _login(client).status_code == 401


def test_the_window_expires_on_its_own(client: TestClient, db, account):
    # a sliding window, never a permanent lockout: a lockout would hand an attacker a
    # denial-of-service against a driver — fail five times against their email and they
    # cannot reach their own detention clock
    for _ in range(MAX):
        _login(client)
    assert _login(client).status_code == 429

    stale = datetime.now(UTC) - timedelta(seconds=identity_service.LOGIN_WINDOW_SECONDS + 60)
    for row in db.scalars(select(identity.LoginAttempt)):
        row.occurred_at = stale
    db.flush()

    assert _login(client).status_code == 401


def test_one_account_lockout_does_not_lock_out_another_driver(client: TestClient, db, account):
    other = identity.register_account(db, "other@example.com", PASSWORD)
    for _ in range(MAX):
        _login(client)
    assert _login(client).status_code == 429
    # a different identifier from the same address is still under the (higher) IP limit
    assert _login(client, email=other.email, password=PASSWORD).status_code == 200


def test_an_unknown_address_is_throttled_exactly_like_a_real_one(client: TestClient, account):
    # counting only real accounts would make the throttle an account-existence oracle:
    # "throttled after five" versus "never throttled" answers what the 401 will not
    ghost = "nobody@example.com"
    for _ in range(MAX):
        assert _login(client, email=ghost).status_code == 401
    assert _login(client, email=ghost).status_code == 429


def test_spraying_many_accounts_from_one_address_is_bounded(client: TestClient, db):
    # the stuffing case a per-identifier limit alone cannot see: one attempt against each
    # of many addresses never trips the per-identifier counter
    ip = "198.51.100.99"
    limit = identity_service.LOGIN_MAX_PER_IP
    for i in range(limit):
        assert _login(client, email=f"spray-{i}@example.com", ip=ip).status_code == 401
    assert _login(client, email="spray-final@example.com", ip=ip).status_code == 429


def test_the_ip_limit_reads_the_LAST_forwarded_entry(client: TestClient, db):
    # Caddy APPENDS the peer it actually saw, so client-supplied entries come first and
    # the trustworthy one is last. Taking the first would let an attacker rotate a header
    # and evade the per-IP limit entirely.
    real = "198.51.100.50"
    limit = identity_service.LOGIN_MAX_PER_IP
    for i in range(limit):
        client.post(
            "/auth/login",
            json={"email": f"rot-{i}@example.com", "password": "wrong"},
            headers={"X-Forwarded-For": f"10.0.0.{i}, {real}"},
        )
    spoofed = client.post(
        "/auth/login",
        json={"email": "rot-final@example.com", "password": "wrong"},
        headers={"X-Forwarded-For": f"10.9.9.9, {real}"},
    )
    assert spoofed.status_code == 429, "a rotated leading entry must not reset the count"


def test_the_limits_are_live_f13_config(client: TestClient, db, account):
    # the HANDOFF-041 pattern: a box under attack can be tightened from the admin console
    # without a deploy
    flags.set_config(db, identity_service.CONFIG_LOGIN_MAX_IDENTIFIER, 2, scope="security")
    assert _login(client).status_code == 401
    assert _login(client).status_code == 401
    assert _login(client).status_code == 429


def test_a_saturated_verifier_sheds_load_rather_than_falling_over(
    client: TestClient, account, monkeypatch
):
    # the CPU-exhaustion answer. Uvicorn runs sync endpoints in a threadpool; without a
    # cap every worker can end up inside Argon2 and the whole API stops answering,
    # including endpoints with nothing to do with logging in. 503 beats a dead box.
    import threading

    monkeypatch.setattr(identity_service, "VERIFY_SLOTS", threading.BoundedSemaphore(1))
    identity_service.VERIFY_SLOTS.acquire()
    try:
        resp = _login(client, password=PASSWORD)
        assert resp.status_code == 503
        assert resp.headers["Retry-After"] == "1"
    finally:
        identity_service.VERIFY_SLOTS.release()

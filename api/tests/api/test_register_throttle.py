"""F1-6 / F1-7 — the registration route gets the defences the login route had.

`/register` took no `Request`, so it could not throttle by IP even if it had wanted to, and
`build_secret_ref` ran Argon2 for an unauthenticated caller with no concurrency bound. That
is the CPU-exhaustion vector audit F-07 hardened `/login` against, on the route beside it.
"""

import threading

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f01_identity.domain import security
from app.foundation.f01_identity.domain import service as identity_service
from app.main import app

PASSWORD = "pw-123456"
IP = "203.0.113.42"


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _register(client, email, ip=IP):
    return client.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD},
        headers={"X-Forwarded-For": ip},
    )


# --- the throttle ---
def test_repeating_one_address_is_bounded(client, db):
    limit = identity_service.REGISTER_MAX_PER_IDENTIFIER
    for _ in range(limit):
        _register(client, "taken@example.com")

    blocked = _register(client, "taken@example.com")

    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0


def test_many_addresses_from_one_ip_are_bounded(client, db):
    """The flood case a per-identifier limit cannot see."""
    limit = identity_service.REGISTER_MAX_PER_IP
    for i in range(limit):
        assert _register(client, f"flood-{i}@example.com").status_code == 201

    assert _register(client, "flood-final@example.com").status_code == 429


def test_every_attempt_counts_not_only_the_failures(client, db):
    """Unlike login. What is rationed is the hashing, and a success costs the same."""
    limit = identity_service.REGISTER_MAX_PER_IP
    for i in range(limit):
        assert _register(client, f"ok-{i}@example.com").status_code == 201

    # nothing failed, and the limit still bites
    assert _register(client, "one-more@example.com").status_code == 429


def test_the_limits_are_live_f13_config(client, db):
    from app.foundation.f13_flags import public as flags

    flags.set_config(db, identity_service.CONFIG_REGISTER_MAX_IP, 1, scope="security")

    assert _register(client, "a@example.com").status_code == 201
    assert _register(client, "b@example.com").status_code == 429


# --- the discriminator: the whole reason for `kind` ---
def test_a_registration_flood_does_not_lock_anyone_out_of_LOGIN(client, db):
    """Without `kind`, a carrier NAT's signups would fill the per-IP LOGIN bucket.

    That is the exact false positive `LOGIN_MAX_PER_IP`'s own comment exists to avoid.
    """
    from app.foundation.f13_flags import public as flags

    driver = identity.register_account(db, "driver@example.com", PASSWORD)
    assert driver is not None
    # deliberately ABOVE `LOGIN_MAX_PER_IP`: with a shared counter, this many registrations
    # would exhaust the login bucket for the same address, which is the false positive the
    # discriminator exists to prevent. Below it, the test would pass without `kind`.
    flood = identity_service.LOGIN_MAX_PER_IP + 5
    flags.set_config(db, identity_service.CONFIG_REGISTER_MAX_IP, flood, scope="security")
    for i in range(flood):
        assert _register(client, f"nat-{i}@example.com").status_code == 201
    assert _register(client, "nat-final@example.com").status_code == 429

    signin = client.post(
        "/auth/login",
        json={"email": "driver@example.com", "password": PASSWORD},
        headers={"X-Forwarded-For": IP},
    )

    assert signin.status_code == 200


def test_failed_logins_do_not_consume_the_registration_budget(client, db):
    """...and the same in reverse: the two counters are genuinely separate."""
    identity.register_account(db, "known@example.com", PASSWORD)
    for _ in range(identity_service.LOGIN_MAX_PER_IDENTIFIER):
        client.post(
            "/auth/login",
            json={"email": "known@example.com", "password": "wrong"},
            headers={"X-Forwarded-For": IP},
        )

    assert _register(client, "fresh@example.com").status_code == 201


# --- the pool split ---
def test_an_exhausted_creation_pool_answers_503_not_500(client, db, monkeypatch):
    monkeypatch.setattr(security, "HASH_SLOTS", threading.BoundedSemaphore(1))
    security.HASH_SLOTS.acquire()
    try:
        resp = _register(client, "busy@example.com")
    finally:
        security.HASH_SLOTS.release()

    assert resp.status_code == 503
    assert resp.headers["Retry-After"] == "1"


def test_a_registration_flood_does_not_shed_LOGINS(client, db):
    """THE reason for two pools, asserted as behaviour rather than as a constant.

    With one shared pool, an attacker saturating account creation turns away every honest
    driver trying to reach their detention clock. With two, the flood sheds only itself.

    THE REAL POOL IS DRAINED, not substituted, and that distinction is the test. A
    monkeypatched replacement rebinds the NAME — so if the two pools were merged into one
    object, swapping `HASH_SLOTS` for a fresh semaphore would leave verification's permits
    untouched and this would pass while proving nothing. Draining the live object is the
    only thing a merge cannot survive.
    """
    identity.register_account(db, "steady@example.com", PASSWORD)
    held = 0
    while security.HASH_SLOTS.acquire(blocking=False):
        held += 1
    try:
        assert held > 0
        assert _register(client, "shed@example.com").status_code == 503

        signin = client.post(
            "/auth/login",
            json={"email": "steady@example.com", "password": PASSWORD},
            headers={"X-Forwarded-For": "198.51.100.7"},
        )
    finally:
        for _ in range(held):
            security.HASH_SLOTS.release()

    assert signin.status_code == 200, "verification must not draw on the creation pool"


def test_authenticate_does_not_acquire_the_slot_itself(db):
    """`BoundedSemaphore` is not reentrant — acquiring in both places would deadlock.

    A plain "does it still work" login proves it: if `authenticate` still took the slot the
    handler now takes, this call would block forever rather than return an account.
    """
    identity.register_account(db, "reentrant@example.com", PASSWORD)

    assert identity.authenticate(db, "reentrant@example.com", PASSWORD) is not None

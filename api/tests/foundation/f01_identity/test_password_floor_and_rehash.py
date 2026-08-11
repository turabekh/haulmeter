"""F1-8 and F1-3 — a floor that cannot lock anyone out, and hashes that can age.

The non-retroactivity test is FIRST deliberately. A password floor is the one change in
this session that could take a live driver's access away, and the property that prevents it
is that the floor is checked where a password is SET and nowhere else.
"""

import threading

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f01_identity.domain import security
from app.foundation.f01_identity.domain.models import AuthMethod
from app.foundation.f01_identity.domain.enums import MethodType


# --- the property that matters most ---
def test_an_existing_short_password_still_logs_in(db):
    """NEVER RETROACTIVE. A floor applied at verification would lock out live drivers to
    enforce a rule they were never given a chance to satisfy."""
    account = identity.register_account(db, "old@example.com", "pw-123456")
    method = db.scalar(
        select_method(account)
    )
    # rewrite the stored hash to a 3-character password, the way an old account would look
    method.secret_ref = identity.get_handler(MethodType.password).build_secret_ref("abc")
    db.flush()

    assert identity.authenticate(db, "old@example.com", "abc") is not None


def select_method(account):
    from sqlalchemy import select

    return select(AuthMethod).where(
        AuthMethod.account_id == account.id, AuthMethod.method_type == MethodType.password
    )


# --- the floor, at all three set-paths ---
def test_registration_refuses_a_short_password(db):
    with pytest.raises(identity.WeakPassword):
        identity.register_account(db, "short@example.com", "pw-1234")


def test_a_credential_change_refuses_a_short_password(db):
    account = identity.register_account(db, "chg@example.com", "pw-123456")

    with pytest.raises(identity.WeakPassword):
        identity.complete_credential_change(db, account, "sevench")


def test_admin_creation_goes_through_the_same_floor(db):
    """It calls `register_account`, so the floor is inherited rather than duplicated."""
    account, temporary = identity.admin_create_account(db, "adm@example.com")

    assert len(temporary) >= identity.MIN_PASSWORD_LENGTH


def test_exactly_the_floor_is_accepted(db):
    account = identity.register_account(db, "edge@example.com", "12345678")

    assert account is not None
    assert identity.authenticate(db, "edge@example.com", "12345678") is not None


def test_every_seed_password_clears_the_floor():
    """A seed that fails the floor takes the dev stack down. Checked, not assumed."""
    for seed in ("pw-123456", "longhaul-dev-1", "longhaul-admin-dev"):
        assert len(seed) >= identity.MIN_PASSWORD_LENGTH, seed


# --- F1-3: hashes that age ---
def _weak_hasher():
    from argon2 import PasswordHasher

    # deliberately below the library default, so `check_needs_rehash` says yes
    return PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)


def test_a_stale_hash_is_upgraded_on_the_next_successful_login(db, monkeypatch):
    """`needs_rehash` was exported and called by NOTHING — so parameters could never rise."""
    account = identity.register_account(db, "stale@example.com", "pw-123456")
    method = db.scalar(select_method(account))
    method.secret_ref = _weak_hasher().hash("pw-123456")
    db.flush()
    stale_ref = method.secret_ref
    assert security.needs_rehash(stale_ref) is True

    assert identity.authenticate(db, "stale@example.com", "pw-123456") is not None

    assert method.secret_ref != stale_ref
    assert security.needs_rehash(method.secret_ref) is False


def test_a_current_hash_is_left_alone(db):
    account = identity.register_account(db, "fresh@example.com", "pw-123456")
    method = db.scalar(select_method(account))
    before = method.secret_ref

    identity.authenticate(db, "fresh@example.com", "pw-123456")

    assert method.secret_ref == before


def test_a_full_creation_pool_skips_the_upgrade_and_the_login_still_succeeds(db):
    """OPPORTUNISTIC. A missed rehash is harmless and self-correcting; a refused login is not.

    The live pool is DRAINED rather than substituted — the rehash resolves it through the
    module, so a replacement would leave the real object untouched and prove nothing.
    """
    account = identity.register_account(db, "busy@example.com", "pw-123456")
    method = db.scalar(select_method(account))
    method.secret_ref = _weak_hasher().hash("pw-123456")
    db.flush()
    stale_ref = method.secret_ref

    held = 0
    while security.HASH_SLOTS.acquire(blocking=False):
        held += 1
    try:
        assert held > 0
        signed_in = identity.authenticate(db, "busy@example.com", "pw-123456")
    finally:
        for _ in range(held):
            security.HASH_SLOTS.release()

    assert signed_in is not None, "a busy pool must never refuse a login"
    assert method.secret_ref == stale_ref, "and the upgrade is simply skipped"


def test_a_wrong_password_never_triggers_an_upgrade(db):
    account = identity.register_account(db, "wrong@example.com", "pw-123456")
    method = db.scalar(select_method(account))
    method.secret_ref = _weak_hasher().hash("pw-123456")
    db.flush()
    before = method.secret_ref

    assert identity.authenticate(db, "wrong@example.com", "not-the-password") is None

    assert method.secret_ref == before

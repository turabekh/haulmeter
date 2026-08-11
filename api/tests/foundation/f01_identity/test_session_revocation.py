"""F1-1 — a credential change ends every other session.

`DEFAULT_SESSION_TTL` is 30 days and the bearer lives in `localStorage`, so a driver who
changed their password because they believed they were compromised was not evicting the
attacker at all — for up to a month. `deactivate_account` already knew the rule and said so
in a comment; it was one of three sites that needed it.

The assertions are about the INVARIANT — no session for that account resolves — rather than
about row counts, because the primitive expires in place instead of deleting.
"""

from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f01_identity.domain.models import AuthSession

T0 = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)


def _account(db, email="rev@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _tokens(db, account, n=3):
    return [identity.create_session(db, account).token for _ in range(n)]


def _alive(db, tokens):
    return [t for t in tokens if identity.resolve_session(db, t) is not None]


# --- the primitive ---
def test_it_ends_every_session_and_says_how_many(db):
    account = _account(db)
    tokens = _tokens(db, account)

    revoked = identity.revoke_sessions(db, account)

    assert revoked == 3
    assert _alive(db, tokens) == []


def test_it_expires_in_place_rather_than_deleting(db):
    """A request already in flight gets a clean 401, and the revocation stays auditable."""
    account = _account(db)
    tokens = _tokens(db, account, n=2)
    before = db.query(AuthSession).filter_by(account_id=account.id).count()

    identity.revoke_sessions(db, account, now=T0)

    assert db.query(AuthSession).filter_by(account_id=account.id).count() == before
    rows = db.query(AuthSession).filter_by(account_id=account.id).all()
    assert all(r.ended_at == T0 and r.expires_at == T0 for r in rows)
    assert _alive(db, tokens) == []


def test_except_token_keeps_exactly_one_alive(db):
    account = _account(db)
    tokens = _tokens(db, account)

    identity.revoke_sessions(db, account, except_token=tokens[1])

    assert _alive(db, tokens) == [tokens[1]]


def test_it_leaves_other_accounts_alone(db):
    mine = _account(db)
    theirs = _account(db, email="other@example.com")
    my_tokens = _tokens(db, mine, n=1)
    their_tokens = _tokens(db, theirs, n=1)

    identity.revoke_sessions(db, mine)

    assert _alive(db, my_tokens) == []
    assert _alive(db, their_tokens) == their_tokens


def test_revoking_twice_is_idempotent_and_reports_nothing_the_second_time(db):
    account = _account(db)
    _tokens(db, account, n=2)

    first = identity.revoke_sessions(db, account)
    second = identity.revoke_sessions(db, account)

    assert first == 2
    assert second == 0  # already-ended rows are not re-counted


# --- site 1: a password change ---
def test_changing_a_password_ends_the_other_sessions(db):
    account = _account(db)
    stale = _tokens(db, account, n=2)

    identity.complete_credential_change(db, account, "a-new-password")

    assert _alive(db, stale) == []


def test_the_session_making_the_change_survives(db):
    """Being signed out at the moment you change a credential reads as "that failed"."""
    account = _account(db)
    mine, *others = _tokens(db, account, n=3)

    identity.complete_credential_change(db, account, "a-new-password", except_token=mine)

    assert _alive(db, [mine]) == [mine]
    assert _alive(db, others) == []


# --- site 2: an admin reset ---
def test_an_admin_reset_ends_every_session_with_no_exception(db):
    """A temporary credential means presumed compromised — nothing is worth preserving."""
    account = _account(db)
    tokens = _tokens(db, account)

    identity.reset_credential(db, account)

    assert _alive(db, tokens) == []


# --- site 3: deactivation, asserted as the invariant ---
def test_deactivation_still_ends_every_session(db):
    """REPLACES an assertion about deleted ROWS — the primitive expires in place now.

    The invariant is what mattered all along: no session for that account resolves.
    """
    account = _account(db)
    tokens = _tokens(db, account)

    identity.deactivate_account(db, account)

    assert _alive(db, tokens) == []


def test_a_revoked_session_cannot_be_used_after_the_credential_changes(db):
    """The end-to-end shape of F1-1: the attacker's token, after the driver reacts."""
    account = _account(db)
    attacker = identity.create_session(db, account).token
    assert identity.resolve_session(db, attacker) is not None

    identity.complete_credential_change(db, account, "chosen-by-the-driver")

    assert identity.resolve_session(db, attacker) is None

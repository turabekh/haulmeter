"""AI-CONTEXT: guest principals, expiry, and the two-halved claim (E3 §E3.2 item 2).

This file holds F1's half ONLY: issue, opt-in, expiry, and the principal's own
single-claim rule. The cross-layer half — the module's rows actually moving, and the two
halves rolling back together — lives in `tests/modules/m15_roadside/test_guest_claim.py`,
because a foundation test that imports a module has the dependency backwards even where
no linter is watching.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f01_identity.domain import guests


def _account(db, email="guest-claimer@example.com"):
    return identity.register_account(db, email, "pw-123456")


# --- issue and opt-in ---------------------------------------------------------------


def test_a_guest_principal_is_issued_to_an_opted_in_module(db):
    principal = guests.issue_guest(db, "m15")
    assert principal.token is not None
    assert principal.claimed_at is None
    assert principal.expires_at > datetime.now(UTC)


def test_a_module_that_has_not_opted_in_is_refused(db):
    """The opt-in is the point: unauthenticated writes do not spread by convenience."""
    with pytest.raises(guests.GuestModuleNotEnabled):
        guests.issue_guest(db, "m03")
    assert "m15" in guests.GUEST_ENABLED_MODULES


def test_the_ttl_is_seven_days(db):
    """E3 §E3.2 states the number, so the number is asserted rather than the mechanism."""
    now = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
    principal = guests.issue_guest(db, "m15", now=now)
    assert principal.expires_at == now + timedelta(days=7)
    assert guests.GUEST_TTL == timedelta(days=7)


# --- expiry -------------------------------------------------------------------------


def test_an_expired_principal_does_not_resolve(db):
    now = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
    principal = guests.issue_guest(db, "m15", now=now)

    assert guests.resolve_guest(db, principal.token, now=now) is not None
    later = now + timedelta(days=7, seconds=1)
    assert guests.resolve_guest(db, principal.token, now=later) is None
    assert guests.is_expired(principal, now=later) is True


def test_expiry_needs_no_sweep_to_have_happened(db):
    """A principal is dead when it is due, not when a job notices.

    Nothing in this test runs a cleanup job, and the principal is still unusable — which
    is the property that makes expiry a guarantee rather than a schedule.
    """
    now = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
    principal = guests.issue_guest(db, "m15", now=now)
    later = now + timedelta(days=30)

    with pytest.raises(guests.GuestPrincipalUnusable):
        guests.claim_guest(db, principal.token, uuid.uuid4(), now=later)


def test_an_expired_principal_cannot_be_claimed(db):
    now = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
    account = _account(db)
    principal = guests.issue_guest(db, "m15", now=now)
    later = now + timedelta(days=8)

    with pytest.raises(guests.GuestPrincipalUnusable):
        guests.claim_guest(db, principal.token, account.id, now=later)


# --- the principal's own single-claim rule ------------------------------------------


def test_a_principal_cannot_be_claimed_twice(db):
    """The second claim is a race, not a retry — two accounts would each think they won."""
    first = _account(db, "first-claimer@example.com")
    second = _account(db, "second-claimer@example.com")
    principal = guests.issue_guest(db, "m15")

    guests.claim_guest(db, principal.token, first.id)
    with pytest.raises(guests.GuestPrincipalUnusable):
        guests.claim_guest(db, principal.token, second.id)


def test_a_claimed_principal_stops_resolving(db):
    account = _account(db)
    principal = guests.issue_guest(db, "m15")
    guests.claim_guest(db, principal.token, account.id)
    assert guests.resolve_guest(db, principal.token) is None


def test_an_unknown_token_is_refused_rather_than_ignored(db):
    with pytest.raises(guests.GuestPrincipalUnusable):
        guests.claim_guest(db, uuid.uuid4(), uuid.uuid4())



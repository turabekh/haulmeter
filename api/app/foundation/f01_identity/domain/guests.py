"""AI-CONTEXT: guest principals and the claim (E3 §E3.2 item 2, D14).

WHY THE CLAIM IS SPLIT IN TWO, and why that is not a compromise. F1 is foundation and m15
is a module; `core < foundation < modules` means F1 cannot import m15 and must not know
what a session or a turn is. So the claim has two halves:

· **here** — the principal's own lifecycle: it is live, it is now claimed by this account,
  and it can never be claimed again;
· **in the module** — re-pointing its rows at the account, which only the module that
  owns those rows can do.

Atomicity comes from both halves running in ONE database transaction, which is the
caller's job. That is a real obligation rather than a detail: `claim` marking a principal
claimed while the module's rows fail to move would lose a driver's work and leave the
token dead, and quality law Q-10 says guest work is never lost silently. The test proves
the pair rolls back together.

EXPIRY IS CHECKED ON READ, NOT SWEPT. There is no job to fall behind: a principal is dead
the moment it is due, whether or not anything has run. A sweep may reclaim rows later, but
nothing depends on it having run.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import GuestPrincipal

# E3 §E3.2: "Guest principals expire in 7 days."
GUEST_TTL = timedelta(days=7)

# AI-CONTEXT: THE OPT-IN, and it is deliberately a hardcoded set rather than a flag or a
# config key. Which modules may accept unauthenticated writes is an architectural decision
# with a decision-log entry behind it, not an operator knob to be turned at 3am. A module
# joining this set should be a diff someone reviews.
GUEST_ENABLED_MODULES = frozenset({"m15"})


class GuestModuleNotEnabled(ValueError):
    """A module asked for a guest principal without opting in."""


class GuestPrincipalUnusable(ValueError):
    """The token is expired, already claimed, or unknown."""


def _now(now: datetime | None = None) -> datetime:
    return now or datetime.now(UTC)


def issue_guest(db: Session, module: str, *, now: datetime | None = None) -> GuestPrincipal:
    if module not in GUEST_ENABLED_MODULES:
        raise GuestModuleNotEnabled(
            f"module {module!r} has not opted in to guest principals; "
            f"enabled: {sorted(GUEST_ENABLED_MODULES)}"
        )
    current = _now(now)
    principal = GuestPrincipal(
        token=uuid.uuid4(), module=module, expires_at=current + GUEST_TTL
    )
    db.add(principal)
    db.flush()
    return principal


def resolve_guest(
    db: Session, token: uuid.UUID, *, now: datetime | None = None
) -> GuestPrincipal | None:
    """The live principal for this token, or None. Expired and claimed both read as None."""
    principal = db.scalar(select(GuestPrincipal).where(GuestPrincipal.token == token))
    if principal is None:
        return None
    if principal.claimed_at is not None:
        return None
    if principal.expires_at <= _now(now):
        return None
    return principal


def is_expired(principal: GuestPrincipal, *, now: datetime | None = None) -> bool:
    return principal.expires_at <= _now(now)


def claim_guest(
    db: Session, token: uuid.UUID, account_id: uuid.UUID, *, now: datetime | None = None
) -> GuestPrincipal:
    """Mark the principal claimed. The module moves its own rows in the SAME transaction.

    Raises rather than returning None: a claim that quietly does nothing is how a driver
    finishes a check, signs up, and finds an empty account — with no error anywhere.
    """
    current = _now(now)
    principal = db.scalar(select(GuestPrincipal).where(GuestPrincipal.token == token))
    if principal is None:
        raise GuestPrincipalUnusable("no such guest token")
    if principal.claimed_at is not None:
        raise GuestPrincipalUnusable("guest token has already been claimed")
    if principal.expires_at <= current:
        raise GuestPrincipalUnusable("guest token has expired")

    principal.claimed_at = current
    principal.claimed_account_id = account_id
    db.flush()
    return principal

"""AI-CONTEXT: HTTP API layer dependencies. This package (app.api) is the
presentation/composition layer ABOVE modules — it may import module and
foundation public interfaces (never their internals; core/UI split keeps
app.core clean). Auth is F1 session tokens (email/password at launch, no
activation); the pluggable auth registry means OAuth/OTP slot in later without
touching this dependency.
"""

from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.foundation.f01_identity import public as identity


def get_db() -> Iterator[Session]:
    yield from get_session()


def bearer_token(authorization: str = Header(default="")) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    return authorization[len("Bearer ") :]


def current_account(
    token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
) -> identity.Account:
    """Ordinary authentication. An IMPERSONATION token resolves to nothing here
    (F1 `resolve_session` refuses it), which is what structurally prevents a
    "view as vendor" session from reaching a driver endpoint — E-D5 approves
    impersonating vendors only, and this is where "only" is enforced."""
    account = identity.resolve_session(db, token)
    if account is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired session")
    return account


@dataclass
class PortalActor:
    """Who is acting, and whose portal they are in. For an ordinary vendor session
    the two are the same account. Under impersonation `actor` is the ADMIN and
    `subject` is the vendor — reads scope to the subject so the screen matches what
    the vendor sees, while every write attributes to the actor."""

    actor: identity.Account
    subject: identity.Account
    impersonated: bool

    @property
    def attribution(self) -> identity.Account:
        return self.actor


def portal_actor(
    token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
) -> PortalActor:
    impersonation = identity.resolve_impersonation(db, token)
    if impersonation is not None:
        actor, subject = impersonation
        return PortalActor(actor=actor, subject=subject, impersonated=True)
    account = identity.resolve_session(db, token)
    if account is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired session")
    return PortalActor(actor=account, subject=account, impersonated=False)

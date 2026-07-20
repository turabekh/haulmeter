"""AI-CONTEXT: HTTP API layer dependencies. This package (app.api) is the
presentation/composition layer ABOVE modules — it may import module and
foundation public interfaces (never their internals; core/UI split keeps
app.core clean). Auth is F1 session tokens (email/password at launch, no
activation); the pluggable auth registry means OAuth/OTP slot in later without
touching this dependency.
"""

from collections.abc import Iterator

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.foundation.f01_identity import public as identity


def get_db() -> Iterator[Session]:
    yield from get_session()


def current_account(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> identity.Account:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization[len("Bearer ") :]
    account = identity.resolve_session(db, token)
    if account is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired session")
    return account

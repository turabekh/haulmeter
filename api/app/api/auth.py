"""AI-CONTEXT: Auth endpoints (F1). Email/password only at launch, NO activation
step — a driver onboards in under 60 seconds (PRD §7.1). Registration attaches
the driver role. Sessions are bearer tokens resolved by current_account.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    token: str
    account_id: str


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(body: Credentials, db: Session = Depends(get_db)) -> TokenOut:
    try:
        account = identity.register_account(db, body.email, body.password)
    except identity.EmailAlreadyRegistered as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered") from exc
    identity.attach_role(db, account, identity.Role.driver)
    session = identity.create_session(db, account)
    return TokenOut(token=session.token, account_id=str(account.id))


@router.post("/login", response_model=TokenOut)
def login(body: Credentials, db: Session = Depends(get_db)) -> TokenOut:
    account = identity.authenticate(db, body.email, body.password)
    if account is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    session = identity.create_session(db, account)
    return TokenOut(token=session.token, account_id=str(account.id))

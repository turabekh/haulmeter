"""AI-CONTEXT: Auth endpoints (F1). Email/password only at launch, NO activation
step — a driver onboards in under 60 seconds (PRD §7.1). Registration attaches
the driver role. Sessions are bearer tokens resolved by current_account.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_account, get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f13_flags import public as flags

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: str
    password: str


def _profile_out(profile: identity.DriverProfile | None) -> dict:
    if profile is None:
        return {
            "authority": None,
            "mc_number": None,
            "dot_number": None,
            "legal_name": None,
            "verify_status": identity.VerifyStatus.unverified.value,
            "verified": False,
        }
    return {
        "authority": profile.authority_type.value if profile.authority_type else None,
        "mc_number": profile.mc_number,
        "dot_number": profile.dot_number,
        "legal_name": profile.legal_name,
        "verify_status": profile.authority_verify_status.value,
        "verified": profile.authority_verify_status == identity.VerifyStatus.verified,
    }


class RegisterIn(Credentials):
    # the driver's operating authority, declared at onboarding (own_mc | leased |
    # company). Decides whether detention claims are invoiced (owed to the driver)
    # or exported to a carrier. Optional — defaults to unset until they declare.
    authority: str | None = None


class TokenOut(BaseModel):
    token: str
    account_id: str


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> TokenOut:
    try:
        account = identity.register_account(db, body.email, body.password)
    except identity.EmailAlreadyRegistered as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered") from exc
    identity.attach_role(db, account, identity.Role.driver)
    if body.authority:
        try:
            identity.upsert_driver_profile(
                db, account, authority_type=identity.AuthorityType(body.authority)
            )
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown authority") from None
    session = identity.create_session(db, account)
    return TokenOut(token=session.token, account_id=str(account.id))


@router.post("/login", response_model=TokenOut)
def login(body: Credentials, db: Session = Depends(get_db)) -> TokenOut:
    account = identity.authenticate(db, body.email, body.password)
    if account is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    session = identity.create_session(db, account)
    return TokenOut(token=session.token, account_id=str(account.id))


class VerifyAuthorityIn(BaseModel):
    mc_number: str | None = None
    dot_number: str | None = None


@router.get("/me")
def me(
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    profile = db.get(identity.DriverProfile, account.id)
    return {
        "account_id": str(account.id),
        "email": account.email,
        "verification_enabled": flags.is_enabled(db, identity.AUTHORITY_VERIFICATION_FLAG),
        **_profile_out(profile),
    }


@router.post("/verify-authority")
def verify_authority(
    body: VerifyAuthorityIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    identity.register_authority_verification(db)  # idempotent
    if not flags.is_enabled(db, identity.AUTHORITY_VERIFICATION_FLAG):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "authority verification not enabled")
    if not (body.mc_number or body.dot_number):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "mc_number or dot_number required"
        )
    profile = identity.verify_authority(db, account, body.mc_number, body.dot_number)
    return _profile_out(profile)

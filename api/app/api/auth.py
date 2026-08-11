"""AI-CONTEXT: Auth endpoints (F1). Email/password only at launch, NO activation
step — a driver onboards in under 60 seconds (PRD §7.1). Registration attaches
the driver role. Sessions are bearer tokens resolved by current_account.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import bearer_token, current_account, get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f13_flags import public as flags

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    """The address the throttle counts against.

    AI-CONTEXT: the LAST `X-Forwarded-For` entry, not the first, and the difference is
    the whole security of this function. Caddy APPENDS the peer it actually saw, so the
    entries a client supplied come first and the trustworthy one is last. Taking
    `xff.split(",")[0]` — which is what most examples do — would let an attacker rotate
    a header and evade the per-IP limit entirely.

    Trusting the header at all is safe only because Caddy is the ONLY ingress: the API
    publishes no port in `docker-compose.deploy.yml`, so nothing reaches it directly. If
    that ever changes, this must change with it.

    `request.client.host` on its own would be worse than nothing in production — every
    driver arrives from Caddy's address, so one attacker would throttle all of them.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        candidates = [part.strip() for part in forwarded.split(",") if part.strip()]
        if candidates:
            return candidates[-1]
    return request.client.host if request.client else None


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
            **_equipment_out(None),
        }
    return {
        "authority": profile.authority_type.value if profile.authority_type else None,
        "mc_number": profile.mc_number,
        "dot_number": profile.dot_number,
        "legal_name": profile.legal_name,
        "verify_status": profile.authority_verify_status.value,
        "verified": profile.authority_verify_status == identity.VerifyStatus.verified,
        **_equipment_out(profile),
    }


def _equipment_out(profile: identity.DriverProfile | None) -> dict:
    # E2: self-reported equipment. Always present in the payload (nulls when unset)
    # so the client renders one stable section rather than a shifting shape.
    if profile is None:
        return {"plate_state": None, "plate_number": None, "unit_number": None, "vin": None}
    return {
        "plate_state": profile.plate_state,
        "plate_number": profile.plate_number,
        "unit_number": profile.unit_number,
        "vin": profile.vin,
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


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    account: identity.Account = Depends(current_account),
    token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
) -> Response:
    """End THIS session, server-side (finding F1-2).

    AI-CONTEXT: there was no logout route at all — the only revocation anywhere in the
    product was the impersonation path. Signing out cleared `localStorage` and nothing
    else, so the bearer stayed valid for the rest of its 30-day TTL: a driver handing a
    phone to a mechanic, or signing out of a borrowed tablet, had not signed out of
    anything a server would notice.

    ONLY this token. "Sign out everywhere" is a different act with a different meaning, and
    `revoke_sessions` makes it a one-line route the day someone asks for it — named as a
    follow-up rather than guessed at here.
    """
    identity.revoke_sessions_for_token(db, account, token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/login", response_model=TokenOut)
def login(body: Credentials, request: Request, db: Session = Depends(get_db)) -> TokenOut:
    # AI-CONTEXT: audit F-07. Nothing counted a failed login, so credential stuffing was
    # unbounded and `authenticate`'s Argon2 verify was a CPU-exhaustion vector needing no
    # credentials at all. The throttle runs FIRST — a check after authenticate would count
    # correctly and still pay for the hash on every attempt.
    now = datetime.now(UTC)
    client_ip = _client_ip(request)
    try:
        identity.check_login_allowed(db, body.email, client_ip, now)
    except identity.Throttled as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too many attempts",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc

    try:
        account = identity.authenticate(db, body.email, body.password)
    except identity.VerifierBusy as exc:
        # every verification slot is in use. Shedding this request keeps the rest of the
        # API answering, which is the difference between a slow login and a dead box.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "authentication is busy",
            headers={"Retry-After": "1"},
        ) from exc

    if account is None:
        # recorded on the SUBMITTED address whether or not it exists — counting only real
        # accounts would make the throttle an account-existence oracle, answering the
        # question this 401 is deliberately careful not to
        identity.record_failed_login(db, body.email, client_ip, now)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    identity.clear_failed_logins(db, body.email)
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


class EquipmentIn(BaseModel):
    # E2: every field optional — a driver fills what they have. Blank clears.
    plate_state: str | None = None
    plate_number: str | None = None
    unit_number: str | None = None
    vin: str | None = None


@router.patch("/equipment")
def update_equipment(
    body: EquipmentIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    # AI-CONTEXT: E2 self-reported equipment. The VIN is format-checked (ISO-3779)
    # so a typo is caught at entry, but nothing is decoded and no claim of
    # verification is made anywhere in the payload or the UI (§11.7).
    try:
        vin = identity.validate_vin(body.vin)
    except identity.InvalidVin as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    profile = identity.upsert_driver_profile(
        db,
        account,
        plate_state=(body.plate_state or "").strip().upper()[:2] or None,
        plate_number=(body.plate_number or "").strip().upper() or None,
        unit_number=(body.unit_number or "").strip() or None,
        vin=vin,
    )
    return _equipment_out(profile)


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

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
from app.foundation.f15_localization import public as localization
from app.modules.m13_vendor import public as m13
from app.modules.m15_roadside import public as m15

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
        return {
            "plate_state": None,
            "plate_number": None,
            "unit_number": None,
            "vin": None,
            "mpg": None,
        }
    return {
        "plate_state": profile.plate_state,
        "plate_number": profile.plate_number,
        "unit_number": profile.unit_number,
        "vin": profile.vin,
        # AI-CONTEXT: a float on the wire and NULL when unset (§23 entry 154). The null
        # is the load-bearing half: it means "this driver has not told us", which the
        # calculator's basis line renders differently from any number, including 6.0.
        "mpg": float(profile.mpg) if profile.mpg is not None else None,
    }


class RegisterIn(Credentials):
    # the driver's operating authority, declared at onboarding (own_mc | leased |
    # company). Decides whether detention claims are invoiced (owed to the driver)
    # or exported to a carrier. Optional — defaults to unset until they declare.
    authority: str | None = None


class TokenOut(BaseModel):
    token: str
    account_id: str
    # AI-CONTEXT: additive with a default, so `/register` (which shares this model and can
    # never set it) is unchanged and no existing client breaks on the new key.
    must_change_password: bool = False


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)) -> TokenOut:
    """AI-CONTEXT: throttled and slot-bounded, like the route beside it (F1-6, F1-7).

    This took no `Request` at all, so it could not throttle by IP even if it had wanted to,
    and `build_secret_ref` ran Argon2 for an unauthenticated caller with no bound. That is
    the CPU-exhaustion vector audit F-07 hardened `/login` against, on the next route down.

    THE ATTEMPT IS RECORDED WHETHER OR NOT IT SUCCEEDS, unlike login. What is rationed here
    is the hashing and the probing, and a successful registration costs exactly as much CPU
    as a failed one.

    THE 409 STAYS, and that is a considered decision rather than an oversight. It makes
    registration an account-existence oracle, which login goes to real lengths not to be —
    but the honest alternative ("we've emailed you if that address exists") requires an
    email-verification step, and no verification at signup is owner-LOCKED. A product that
    cannot send that email must not imply it did. So the oracle stays and stops being FREE:
    the throttle above makes enumeration cost attempts. Closing it properly is downstream
    of the owner's verification decision, not a problem this route can solve.
    """
    now = datetime.now(UTC)
    client_ip = _client_ip(request)
    try:
        identity.check_registration_allowed(db, body.email, client_ip, now)
    except identity.Throttled as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too many registration attempts",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    identity.record_registration_attempt(db, body.email, client_ip, now)
    try:
        account = identity.register_account(db, body.email, body.password)
    except identity.EmailAlreadyRegistered as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered") from exc
    except identity.WeakPassword as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except identity.VerifierBusy as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "account creation is busy",
            headers={"Retry-After": "1"},
        ) from exc
    identity.attach_role(db, account, identity.Role.driver)
    if body.authority:
        try:
            identity.upsert_driver_profile(
                db, account, authority_type=identity.AuthorityType(body.authority)
            )
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown authority") from None
    session = identity.create_session(db, account)
    # the first sign-in a driver has, and it is a sign-in like any other
    identity.record_login_event(
        db,
        account.id,
        identity.LOGIN_REGISTER,
        client_ip,
        request.headers.get("user-agent"),
        now,
    )
    return TokenOut(
        token=session.token,
        account_id=str(account.id),
        must_change_password=identity.must_change_credential(db, account),
    )


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
    # AI-CONTEXT: the SUCCESS is recorded here and nowhere else (§23 entry 234).
    # `clear_failed_logins` one line up deletes this driver's throttle rows, which is
    # exactly why the throttle table can never answer "who signed in" — the moment it
    # would have known, it forgets.
    identity.record_login_event(
        db,
        account.id,
        identity.LOGIN_LOGIN,
        client_ip,
        request.headers.get("user-agent"),
        now,
    )
    return TokenOut(
        token=session.token,
        account_id=str(account.id),
        must_change_password=identity.must_change_credential(db, account),
    )


class VerifyAuthorityIn(BaseModel):
    mc_number: str | None = None
    dot_number: str | None = None


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str


class PasswordChangeOut(BaseModel):
    changed: bool
    # how many OTHER sessions ended. The driver is told, because a security action they
    # cannot observe is one they cannot trust (D3).
    other_sessions_ended: int


@router.post("/password", response_model=PasswordChangeOut)
def change_password(
    body: PasswordChangeIn,
    request: Request,
    account: identity.Account = Depends(current_account),
    token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
) -> PasswordChangeOut:
    """Change this account's password. ONE endpoint for both cases (D1).

    AI-CONTEXT: there was no way for a driver to change their password at all —
    `complete_credential_change` had zero production callers. That made three finished
    pieces of work inert (revocation, the floor, the rehash) and inverted the property
    `reset_credential`'s own docstring promises: an admin issued a temporary password, the
    driver was never told to replace it and could not, so **the temporary became the
    permanent one** and the admin knew a working credential indefinitely.

    THE CURRENT PASSWORD IS REQUIRED, with no exception for the `must_change` case. A
    stolen bearer token must not be enough to seize an account — this is the one control
    standing between a leaked session and permanent takeover, and a driver holding a
    temporary password knows it. "Authenticated, therefore allowed" would make the session
    itself the credential.

    The voluntary change and the forced post-reset change are the same operation with the
    same requirements; two endpoints would drift.
    """
    now = datetime.now(UTC)
    client_ip = _client_ip(request)
    try:
        identity.check_password_change_allowed(db, account.email, client_ip, now)
    except identity.Throttled as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too many attempts",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc

    # counted BEFORE the change, because that is the number `complete_credential_change`
    # is about to end — asking afterwards would count what survived
    others = identity.other_live_sessions(db, account, except_token=token)

    try:
        correct = identity.verify_current_password(db, account, body.current_password)
    except identity.VerifierBusy as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "busy",
            headers={"Retry-After": "1"},
        ) from exc
    if not correct:
        identity.record_failed_password_change(db, account.email, client_ip, now)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "current password is incorrect")

    try:
        # `complete_credential_change` applies the floor, revokes every OTHER session and
        # clears `must_change` — all three already existed and had no caller
        identity.complete_credential_change(db, account, body.new_password, except_token=token)
    except identity.WeakPassword as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except identity.VerifierBusy as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "busy",
            headers={"Retry-After": "1"},
        ) from exc

    identity.clear_failed_password_changes(db, account.email)
    return PasswordChangeOut(changed=True, other_sessions_ended=others)


@router.get("/me")
def me(
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    profile = db.get(identity.DriverProfile, account.id)
    return {
        "account_id": str(account.id),
        "email": account.email,
        # AI-CONTEXT: the language the SERVER will write this driver's alerts in (§23
        # entry 232). It rides `/me` so a fresh install has something to adopt: a phone
        # with no stored choice must not silently reset a driver to English, which is
        # what "the device always wins" would do on a new handset.
        "locale": localization.get_user_locale(db, account),
        "verification_enabled": flags.is_enabled(db, identity.AUTHORITY_VERIFICATION_FLAG),
        # AI-CONTEXT: the More row's condition, and it rides `/me` for the same reason
        # `verification_enabled` does — a driver app cannot read F13, and a capability
        # nobody has switched on must not advertise itself. The FLAG_KEY constant rather
        # than a literal: `is_enabled` treats an unregistered flag as OFF, so a typo here
        # would not fail, it would silently hide the entry forever.
        "roadside_enabled": flags.is_enabled(db, m15.FLAG_KEY),
        # AI-CONTEXT: the food-alerts card's condition, and it exists because that card
        # had none (§23 entry 223). `m13_vendor` has been FALSE in production since the
        # food half was switched off (HANDOFF-114), and the More screen went on offering
        # "Food alerts" to every driver — an opt-in to notifications from a module that
        # is not running. The rule two lines up is the one it broke: a capability nobody
        # has switched on must not advertise itself.
        "food_enabled": flags.is_enabled(db, m13.FLAG_KEY),
        # AI-CONTEXT: on `/me` as well as on the login response, and THIS is the one that
        # mattered (D4). Sessions last 30 days, so a driver who signs in with a temporary
        # password and reopens the app next morning never sees `/login` again — the flag
        # reaching only the login response is why it never reached anyone at all.
        "must_change_password": identity.must_change_credential(db, account),
        **_profile_out(profile),
    }


class EquipmentIn(BaseModel):
    # E2: every field optional — a driver fills what they have. Blank clears.
    plate_state: str | None = None
    plate_number: str | None = None
    unit_number: str | None = None
    vin: str | None = None
    # sent as a string so an empty one can mean CLEAR; a float field would make "unset"
    # and "0" the same wire value on a form that submits everything it holds
    mpg: str | float | None = None


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
        mpg = identity.validate_mpg(body.mpg)
    except (identity.InvalidVin, identity.InvalidMpg) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    profile = identity.upsert_driver_profile(
        db,
        account,
        plate_state=(body.plate_state or "").strip().upper()[:2] or None,
        plate_number=(body.plate_number or "").strip().upper() or None,
        unit_number=(body.unit_number or "").strip() or None,
        vin=vin,
        mpg=mpg,
    )
    return _equipment_out(profile)


class LocaleIn(BaseModel):
    locale: str


@router.patch("/locale")
def update_locale(
    body: LocaleIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    """AI-CONTEXT: N-02's last mile (§23 entry 232).

    F8 has resolved every driver notification's language from `f01.driver_profile.locale`
    since N-02 — six modules' message tables, the fallback to compiled English, the tests.
    **Nothing ever wrote that column.** `f15.set_user_locale` was exported and called by
    tests and by nothing else, and the app's own picker wrote `localStorage` and stopped.
    So all twelve production profiles read `en` and a driver running the app in Uzbek got
    their detention alert in English — the whole catalogue built, shipped, and never once
    reached by a real driver.

    Validation is F15's, not this endpoint's: `set_user_locale` raises `UnsupportedLocale`
    for anything outside the six launch locales, so the wire cannot widen the set that the
    rest of the product believes in.
    """
    try:
        localization.set_user_locale(db, account, body.locale)
    except localization.UnsupportedLocale as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"unsupported locale: {body.locale}"
        ) from exc
    return {"locale": localization.get_user_locale(db, account)}


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

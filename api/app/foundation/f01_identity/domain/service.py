import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import security
from . import security as _security
from .auth_methods import get_handler
from .enums import AuthorityType, MethodType, OrgType, Role, VerifyStatus
from .models import (
    Account,
    AuthMethod,
    AuthSession,
    DriverProfile,
    LoginAttempt,
    Organization,
    OrgMembership,
    RoleAttachment,
)
from .verifier import AuthorityVerifier, resolve_verifier

DEFAULT_SESSION_TTL = timedelta(days=30)
INVOICING_AUTHORITIES = {AuthorityType.own_mc, AuthorityType.leased}

# F13 flag gating the FMCSA verification seam (activation switch, PRD §6).
AUTHORITY_VERIFICATION_FLAG = "f01_authority_verification"


# AI-CONTEXT: authentication throttling (audit F-07). There was none — no limiter, no
# lockout, no attempt counter anywhere in the application — against a live product with
# real driver accounts on a single VM with no monitoring.
#
# The finding names TWO attacks, and they need two different defences:
#
#  1. CREDENTIAL STUFFING against an account. Bounded per identifier, and per client IP
#     for the spray case. Compiled defaults below, overridable as F13 config so the
#     numbers can be tuned on a live box without a deploy (the HANDOFF-041 pattern that
#     m06's take rate and m10's earn rates already use).
#
#  2. CPU EXHAUSTION. `verify` runs Argon2, which is deliberately memory-hard and slow.
#     A few hundred concurrent POSTs take the box down with NO credentials, so no
#     per-identifier limit can help — the attacker simply uses a different email each
#     time. `VERIFY_SLOTS` is the answer: it caps how many password verifications run
#     at once, whatever they claim to be. Uvicorn runs sync endpoints in a threadpool,
#     so without it every worker can end up inside Argon2 and the whole API stops
#     answering — including the endpoints that have nothing to do with logging in.
#     Capping it isolates the expensive operation instead of letting it starve the rest.
LOGIN_WINDOW_SECONDS = 900  # 15 minutes, and the lockout expires WITH it
LOGIN_MAX_PER_IDENTIFIER = 5
LOGIN_MAX_PER_IP = 20  # higher: a carrier NAT can put many honest drivers on one address
CONFIG_LOGIN_WINDOW = "f01_login_window_seconds"
CONFIG_LOGIN_MAX_IDENTIFIER = "f01_login_max_per_identifier"
CONFIG_LOGIN_MAX_IP = "f01_login_max_per_ip"

# AI-CONTEXT: registration's own counters (finding F1-6/F1-7). Deliberately NOT login's.
#
# Sharing the bucket would mean a registration flood from a carrier NAT locking honest
# drivers out of LOGIN on the same address — the exact false positive `LOGIN_MAX_PER_IP`'s
# comment above exists to avoid. `kind` on `login_attempt` is what keeps them apart.
#
# THE DEFAULTS ARE A FIRST GUESS WITH NO TRAFFIC BEHIND THEM, and they deliberately MATCH
# login's rather than being tighter. Registration is rarer than login, so a tighter number
# is tempting — and the realistic failure is a FLEET onboarding its drivers from one depot
# Wi-Fi, which looks exactly like a script from behind a NAT. Being wrong in that direction
# turns a customer's first hour into a support call, while being wrong in the other
# direction costs an attacker a few more Argon2 hashes than we would like.
#
# They are F13 keys precisely so the first week of real signup volume can tighten them from
# the console without a deploy. Tuning down on evidence is cheap; a lockout is not.
REGISTER_MAX_PER_IDENTIFIER = LOGIN_MAX_PER_IDENTIFIER
REGISTER_MAX_PER_IP = LOGIN_MAX_PER_IP
CONFIG_REGISTER_MAX_IDENTIFIER = "f01_register_max_per_identifier"
CONFIG_REGISTER_MAX_IP = "f01_register_max_per_ip"

# A SLIDING WINDOW, never a permanent lockout. A lockout would hand an attacker a
# denial-of-service against the driver: fail five times against a competitor's email and
# they cannot reach their own detention clock. This expires on its own.
# the pools and `VerifierBusy` moved to `security.py`, beside the operations they bound.
# Re-exported here so every existing caller and test keeps its import path.
VERIFY_SLOTS = _security.VERIFY_SLOTS
HASH_SLOTS = _security.HASH_SLOTS
VerifierBusy = _security.VerifierBusy


class Throttled(Exception):
    """Too many failed attempts. `retry_after` is seconds, for the HTTP header."""

    def __init__(self, retry_after: int):
        super().__init__(f"retry after {retry_after}s")
        self.retry_after = retry_after


# AI-CONTEXT: a length floor, no composition rules, and NEVER retroactive (finding F1-8).
#
# There was no minimum anywhere — `Credentials.password: str` and nothing else.
#
# LENGTH, NOT COMPOSITION. Requiring an uppercase, a digit and a symbol buys a predictable
# transformation of a short word and costs a driver typing on a phone keyboard in a cab.
# Eight characters is the floor because it is the point below which a password is guessable
# rather than merely weak, and because every seed and bootstrap credential in this repo
# already clears it — checked before the number was picked, not after.
#
# NEVER RETROACTIVE, and this is the part that must not drift. It is checked where a
# password is SET, never where one is verified, so an account created before this exists
# keeps working with whatever it has and meets the floor the next time its holder chooses
# one. A floor that applied at login would lock out live drivers to enforce a rule they
# were never given a chance to satisfy.
MIN_PASSWORD_LENGTH = 8


class WeakPassword(ValueError):
    """Raised where a password is SET. Never raised on a verification path."""

    def __init__(self, message: str | None = None):
        super().__init__(message or f"password must be at least {MIN_PASSWORD_LENGTH} characters")


def validate_password(password: str) -> str:
    """The ONE floor, used by all three paths that set a credential.

    A single validator rather than three Pydantic constraints, because three constraints
    drift: the day one of them is relaxed, the other two keep asserting a rule the product
    no longer has.
    """
    if password is None or len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPassword()
    return password


class EmailAlreadyRegistered(Exception):
    pass


class AuthMethodNotEnabled(Exception):
    pass


class InvalidVin(Exception):
    pass


# AI-CONTEXT: E2 — VIN is FORMAT-validated only (ISO-3779: 17 chars, no I/O/Q, the
# position-9 check digit). No decode service is called and no vehicle fact is
# inferred, so the profile never implies a verification that didn't happen (§11.7).
_VIN_LENGTH = 17
_VIN_FORBIDDEN = set("IOQ")
_VIN_TRANSLITERATION = {
    **{str(d): d for d in range(10)},
    "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8,
    "J": 1, "K": 2, "L": 3, "M": 4, "N": 5, "P": 7, "R": 9,
    "S": 2, "T": 3, "U": 4, "V": 5, "W": 6, "X": 7, "Y": 8, "Z": 9,
}  # fmt: skip
_VIN_WEIGHTS = (8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2)


def normalize_vin(vin: str | None) -> str | None:
    if vin is None:
        return None
    cleaned = vin.strip().upper().replace("-", "").replace(" ", "")
    return cleaned or None


def validate_vin(vin: str | None) -> str | None:
    """Returns the normalized VIN, or None when unset. Raises InvalidVin on a bad one."""
    cleaned = normalize_vin(vin)
    if cleaned is None:
        return None
    if len(cleaned) != _VIN_LENGTH:
        raise InvalidVin("a VIN is 17 characters")
    if any(ch not in _VIN_TRANSLITERATION for ch in cleaned):
        bad = sorted({ch for ch in cleaned if ch not in _VIN_TRANSLITERATION})
        reason = (
            "I, O and Q are never used in a VIN"
            if _VIN_FORBIDDEN & set(bad)
            else "invalid characters"
        )
        raise InvalidVin(reason)
    total = sum(_VIN_TRANSLITERATION[ch] * w for ch, w in zip(cleaned, _VIN_WEIGHTS, strict=True))
    expected = "X" if total % 11 == 10 else str(total % 11)
    if cleaned[8] != expected:
        raise InvalidVin("check digit does not match")
    return cleaned


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def register_account(db: Session, email: str, password: str) -> Account:
    validate_password(password)
    normalized = _normalize_email(email)
    existing = db.scalar(select(Account).where(Account.email == normalized))
    if existing is not None:
        raise EmailAlreadyRegistered(normalized)

    account = Account(email=normalized)
    db.add(account)
    db.flush()

    handler = get_handler(MethodType.password)
    method = AuthMethod(
        account_id=account.id,
        method_type=MethodType.password,
        identifier=normalized,
        secret_ref=handler.build_secret_ref(password),
        is_primary=True,
    )
    db.add(method)
    db.flush()
    return account


def add_auth_method(
    db: Session,
    account: Account,
    method_type: MethodType,
    identifier: str,
    credential: str | None = None,
) -> AuthMethod:
    handler = get_handler(method_type)
    try:
        secret_ref = handler.build_secret_ref(credential) if credential is not None else None
    except NotImplementedError as exc:
        raise AuthMethodNotEnabled(str(exc)) from exc

    stored_identifier = (
        _normalize_email(identifier) if method_type == MethodType.password else identifier
    )
    method = AuthMethod(
        account_id=account.id,
        method_type=method_type,
        identifier=stored_identifier,
        secret_ref=secret_ref,
    )
    db.add(method)
    db.flush()
    return method


def _login_limits(db: Session) -> tuple[int, int, int]:
    # live F13 config, falling back to the compiled defaults. Read per attempt so a box
    # under attack can be tightened from the admin console without a deploy.
    from app.foundation.f13_flags import public as flags

    return (
        int(flags.get_config(db, CONFIG_LOGIN_WINDOW, LOGIN_WINDOW_SECONDS)),
        int(flags.get_config(db, CONFIG_LOGIN_MAX_IDENTIFIER, LOGIN_MAX_PER_IDENTIFIER)),
        int(flags.get_config(db, CONFIG_LOGIN_MAX_IP, LOGIN_MAX_PER_IP)),
    )


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


ATTEMPT_LOGIN = "login"
ATTEMPT_REGISTER = "register"


def _attempts_since(
    db: Session, column, value, since: datetime, kind: str
) -> tuple[int, datetime | None]:
    row = db.execute(
        select(func.count(), func.min(LoginAttempt.occurred_at)).where(
            column == value,
            LoginAttempt.kind == kind,
            LoginAttempt.occurred_at >= since,
        )
    ).one()
    return int(row[0]), row[1]


def check_login_allowed(db: Session, email: str, client_ip: str | None, now: datetime) -> None:
    """Raise `Throttled` BEFORE any password is verified.

    AI-CONTEXT: the ordering is the fix, not a detail. Checking after `authenticate`
    would count the attempts correctly and still run Argon2 on every one of them — the
    throttle would stop credential stuffing while leaving the CPU-exhaustion vector
    exactly as it was. Nothing expensive may happen above this line.
    """
    window, max_identifier, max_ip = _login_limits(db)
    now = _as_utc(now)
    since = now - timedelta(seconds=window)

    checks = [(LoginAttempt.identifier, _normalize_email(email), max_identifier)]
    if client_ip:
        checks.append((LoginAttempt.client_ip, client_ip, max_ip))

    for column, value, limit in checks:
        count, oldest = _attempts_since(db, column, value, since, ATTEMPT_LOGIN)
        if count < limit:
            continue
        # the window slides off the OLDEST attempt still counted, so the wait shrinks as
        # attempts age out instead of resetting every time someone tries again
        elapsed = (now - _as_utc(oldest)).total_seconds() if oldest else 0
        raise Throttled(max(1, int(window - elapsed)))


def _register_limits(db: Session) -> tuple[int, int, int]:
    from app.foundation.f13_flags import public as flags

    return (
        int(flags.get_config(db, CONFIG_LOGIN_WINDOW, LOGIN_WINDOW_SECONDS)),
        int(flags.get_config(db, CONFIG_REGISTER_MAX_IDENTIFIER, REGISTER_MAX_PER_IDENTIFIER)),
        int(flags.get_config(db, CONFIG_REGISTER_MAX_IP, REGISTER_MAX_PER_IP)),
    )


def check_registration_allowed(
    db: Session, email: str, client_ip: str | None, now: datetime
) -> None:
    """Raise `Throttled` BEFORE any hashing — the same ordering rule login follows.

    AI-CONTEXT: registration runs Argon2 for an unauthenticated caller, at a cost per
    request at least equal to a verify, and nothing counted it (F1-6). `check_login_allowed`
    exists because "nothing expensive may happen above this line"; the route beside it had
    no such line at all.
    """
    window, max_identifier, max_ip = _register_limits(db)
    now = _as_utc(now)
    since = now - timedelta(seconds=window)

    checks = [(LoginAttempt.identifier, _normalize_email(email), max_identifier)]
    if client_ip:
        checks.append((LoginAttempt.client_ip, client_ip, max_ip))

    for column, value, limit in checks:
        count, oldest = _attempts_since(db, column, value, since, ATTEMPT_REGISTER)
        if count < limit:
            continue
        elapsed = (now - _as_utc(oldest)).total_seconds() if oldest else 0
        raise Throttled(max(1, int(window - elapsed)))


def record_registration_attempt(
    db: Session, email: str, client_ip: str | None, now: datetime
) -> None:
    """EVERY attempt, successful or not — unlike login, which records only failures.

    AI-CONTEXT: what is being rationed here is the Argon2 work and the probing, and a
    successful registration costs exactly as much CPU as a failed one. Recording only
    failures would let an attacker create accounts without limit and would leave the
    409-as-oracle (F1-7) just as free as it was.
    """
    window, _, _ = _register_limits(db)
    db.execute(
        delete(LoginAttempt).where(
            LoginAttempt.occurred_at < _as_utc(now) - timedelta(seconds=window)
        )
    )
    db.add(
        LoginAttempt(
            identifier=_normalize_email(email),
            kind=ATTEMPT_REGISTER,
            client_ip=client_ip,
            occurred_at=_as_utc(now),
        )
    )
    db.flush()


def record_failed_login(db: Session, email: str, client_ip: str | None, now: datetime) -> None:
    window, _, _ = _login_limits(db)
    normalized = _normalize_email(email)
    # bounded on write, so this table can never become F-09 in a second place
    db.execute(
        delete(LoginAttempt).where(
            LoginAttempt.occurred_at < _as_utc(now) - timedelta(seconds=window)
        )
    )
    db.add(
        LoginAttempt(
            identifier=normalized,
            kind=ATTEMPT_LOGIN,
            client_ip=client_ip,
            occurred_at=_as_utc(now),
        )
    )
    db.flush()


def clear_failed_logins(db: Session, email: str) -> None:
    # proving you are the account holder ends the lockout on it. The IP's own count is
    # deliberately NOT cleared: one success does not vouch for every attempt from an
    # address, which is the whole point of counting them separately.
    db.execute(
        delete(LoginAttempt).where(
            LoginAttempt.identifier == _normalize_email(email),
            # only the LOGIN rows: a successful sign-in says nothing about how many
            # accounts this address has been used to create
            LoginAttempt.kind == ATTEMPT_LOGIN,
        )
    )
    db.flush()


def authenticate(db: Session, email: str, password: str) -> Account | None:
    normalized = _normalize_email(email)
    method = db.scalar(
        select(AuthMethod).where(
            AuthMethod.method_type == MethodType.password,
            AuthMethod.identifier == normalized,
        )
    )
    if method is None:
        return None
    handler = get_handler(MethodType.password)
    # AI-CONTEXT: the slot is acquired INSIDE `handler.verify` now (F1-6). Acquiring here
    # as well would deadlock — `BoundedSemaphore` is not reentrant — which is why this is a
    # move rather than a belt-and-braces addition.
    verified = handler.verify(method.secret_ref, password)
    if not verified:
        return None
    _upgrade_hash_if_stale(db, method, password)
    account = db.get(Account, method.account_id)
    # a deactivated account fails CLOSED, and distinctly from a wrong password: the
    # console and the logs must be able to tell "switched off" from "bad credentials"
    if account is not None and not account.active:
        raise AccountInactive(str(account.id))
    method.last_used_at = datetime.now(UTC)
    db.flush()
    return account


def _upgrade_hash_if_stale(db: Session, method: AuthMethod, password: str) -> bool:
    """Re-hash a verified password when its stored parameters have gone stale (F1-3).

    AI-CONTEXT: `needs_rehash` was exported and called by NOTHING since it was written —
    the sixth built-and-inert engine in this codebase's tally — which meant Argon2
    parameters could never be raised for anyone who already had an account. Raising them in
    `PasswordHasher` would have protected new accounts and silently left every existing one
    on the old cost.

    OPPORTUNISTIC, and that is the whole safety property. The upgrade happens on a
    successful login, when the plaintext is in hand and correct — the only moment it can —
    but a full creation pool SKIPS it and completes the login anyway. A missed rehash is
    harmless and self-correcting: the next sign-in tries again. A refused login is neither.
    """
    if not security.needs_rehash(method.secret_ref):
        return False
    handler = get_handler(MethodType.password)
    try:
        method.secret_ref = handler.build_secret_ref(password)
    except VerifierBusy:
        return False  # the pool is for people signing in; they come first
    db.flush()
    return True


def create_session(
    db: Session,
    account: Account,
    ttl: timedelta = DEFAULT_SESSION_TTL,
    client_skew_ms: int | None = None,
) -> AuthSession:
    session = AuthSession(
        account_id=account.id,
        token=secrets.token_urlsafe(48),
        expires_at=datetime.now(UTC) + ttl,
        client_skew_ms=client_skew_ms,
    )
    db.add(session)
    db.flush()
    return session


def resolve_session(db: Session, token: str) -> Account | None:
    session = db.scalar(select(AuthSession).where(AuthSession.token == token))
    if session is None:
        return None
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        return None
    # an impersonation token is not an ordinary session and must never be treated as
    # one — this is what stops it reaching a driver endpoint (E-D5)
    if session.impersonating_account_id is not None:
        return None
    return db.get(Account, session.account_id)


def attach_role(db: Session, account: Account, role: Role, org_id=None) -> RoleAttachment:
    attachment = RoleAttachment(account_id=account.id, role=role, org_id=org_id)
    db.add(attachment)
    db.flush()
    return attachment


def create_organization(db: Session, org_type: OrgType, name: str) -> Organization:
    org = Organization(org_type=org_type, name=name)
    db.add(org)
    db.flush()
    return org


def add_membership(db: Session, org: Organization, account: Account) -> OrgMembership:
    membership = OrgMembership(org_id=org.id, account_id=account.id)
    db.add(membership)
    db.flush()
    return membership


def upsert_driver_profile(db: Session, account: Account, **fields) -> DriverProfile:
    profile = db.get(DriverProfile, account.id)
    if profile is None:
        profile = DriverProfile(account_id=account.id, **fields)
        db.add(profile)
    else:
        for key, value in fields.items():
            setattr(profile, key, value)
    db.flush()
    return profile


def can_invoice(profile: DriverProfile | None) -> bool:
    if profile is None or profile.authority_type is None:
        return False
    return profile.authority_type in INVOICING_AUTHORITIES


def register_authority_verification(db: Session) -> None:
    # idempotent: ensure the F13 activation flag exists (mirrors module register_*).
    from app.foundation.f13_flags import public as flags

    flags.register_flag(
        db, AUTHORITY_VERIFICATION_FLAG, description="F1 Operating-authority verification (FMCSA)"
    )
    # AI-CONTEXT: DECLARED, not merely readable. Session 112's finding was that
    # `/admin/config` listed only keys somebody had already set, so a tunable nobody had
    # touched was invisible and guessing its name was the only way in. These three are
    # the levers an operator reaches for while a box is being attacked — the moment when
    # hunting for an undocumented key name is worst — so they are on the console before
    # anyone needs them.
    flags.register_config(
        db,
        CONFIG_LOGIN_WINDOW,
        LOGIN_WINDOW_SECONDS,
        description="Failed-login counting window, seconds. The lockout expires with it.",
        scope="security",
    )
    flags.register_config(
        db,
        CONFIG_LOGIN_MAX_IDENTIFIER,
        LOGIN_MAX_PER_IDENTIFIER,
        description="Failed logins per email address within the window before 429.",
        scope="security",
    )
    flags.register_config(
        db,
        CONFIG_LOGIN_MAX_IP,
        LOGIN_MAX_PER_IP,
        description=(
            "Failed logins per client IP within the window. Higher than the per-address "
            "limit: a carrier NAT can put many honest drivers on one address."
        ),
        scope="security",
    )


def verify_authority(
    db: Session,
    account: Account,
    mc_number: str | None,
    dot_number: str | None,
    verifier: AuthorityVerifier | None = None,
) -> DriverProfile:
    # runs the (key-gated) FMCSA lookup and records the outcome on the profile.
    # Verification strengthens credibility; it never changes can_invoice.
    verifier = verifier or resolve_verifier()
    result = verifier.verify(mc_number, dot_number)
    verified = result.found and result.allowed_to_operate
    return upsert_driver_profile(
        db,
        account,
        mc_number=result.mc_number or (mc_number or None),
        dot_number=result.dot_number or (dot_number or None),
        legal_name=result.legal_name if verified else None,
        authority_verify_status=(VerifyStatus.verified if verified else VerifyStatus.failed),
        authority_verified_at=(datetime.now(UTC) if verified else None),
    )


# --- Admin account management (Admin Console 2.0, design-prd §23 E-D6) ---
# AI-CONTEXT: the operator's account powers, and their deliberate limits. An admin
# can create, edit, reset a credential and deactivate — never read a password, never
# set a permanent one, and never delete. Accounts reference money, claims and
# evidence, so erasure is a data-retention WORKFLOW (PRD §17 Q16), not a button.
TEMP_PASSWORD_BYTES = 9


class AccountInactive(Exception):
    """Login refused: the account is deactivated. Distinct from bad credentials so
    the console and the logs can tell "wrong password" from "switched off"."""


def search_accounts(
    db: Session, query: str | None = None, role: Role | None = None, limit: int = 50
) -> list[Account]:
    """One search box over the facts an operator actually has on the phone: an email,
    a name, an MC/DOT number, or a plate. A directory that only matches email is
    useless to someone holding a driver's paperwork."""
    stmt = select(Account)
    if query:
        term = f"%{query.strip().lower()}%"
        stmt = (
            stmt.outerjoin(DriverProfile, DriverProfile.account_id == Account.id)
            .where(
                func.lower(Account.email).like(term)
                | func.lower(func.coalesce(Account.display_name, "")).like(term)
                | func.lower(func.coalesce(DriverProfile.mc_number, "")).like(term)
                | func.lower(func.coalesce(DriverProfile.dot_number, "")).like(term)
                | func.lower(func.coalesce(DriverProfile.plate_number, "")).like(term)
                | func.lower(func.coalesce(DriverProfile.legal_name, "")).like(term)
            )
            .distinct()
        )
    if role is not None:
        stmt = stmt.join(RoleAttachment, RoleAttachment.account_id == Account.id).where(
            RoleAttachment.role == role
        )
    return list(db.scalars(stmt.order_by(Account.created_at.desc()).limit(limit)))


def admin_create_account(
    db: Session, email: str, role: Role = Role.driver, display_name: str | None = None
) -> tuple[Account, str]:
    """The phone-onboarding case: an operator creates the account while the driver is
    on the line. Returns the account and a TEMPORARY password — the only password an
    admin ever handles — which the holder must replace at first login."""
    account = register_account(db, email, _temp_password())
    temporary = reset_credential(db, account)
    if display_name:
        account.display_name = display_name.strip()
    attach_role(db, account, role)
    db.expire(account, ["roles"])
    db.flush()
    return account, temporary


def _temp_password() -> str:
    return secrets.token_urlsafe(TEMP_PASSWORD_BYTES)


def reset_credential(db: Session, account: Account) -> str:
    """Issue a temporary password and force its replacement. The permanent password
    is never seen, set or recoverable by anyone but its owner — support that can read
    a password is support that can be social-engineered into surrendering one."""
    temporary = _temp_password()
    handler = get_handler(MethodType.password)
    method = db.scalar(
        select(AuthMethod).where(
            AuthMethod.account_id == account.id, AuthMethod.method_type == MethodType.password
        )
    )
    if method is None:
        method = AuthMethod(
            account_id=account.id,
            method_type=MethodType.password,
            identifier=_normalize_email(account.email),
            is_primary=True,
        )
        db.add(method)
    method.secret_ref = handler.build_secret_ref(temporary)
    method.must_change = True
    # EVERY session, with no exception (F1-1). An admin issuing a temporary credential
    # means the account is presumed compromised or locked out, and in neither case is
    # there a session worth preserving — including the admin's own view of it.
    revoke_sessions(db, account)
    db.flush()
    return temporary


def complete_credential_change(
    db: Session, account: Account, new_password: str, except_token: str | None = None
) -> AuthMethod:
    method = db.scalar(
        select(AuthMethod).where(
            AuthMethod.account_id == account.id, AuthMethod.method_type == MethodType.password
        )
    )
    validate_password(new_password)
    handler = get_handler(MethodType.password)
    method.secret_ref = handler.build_secret_ref(new_password)
    method.must_change = False
    # a credential change ends every OTHER session (F1-1). Changing your password is the
    # act of a driver who thinks someone else has it; leaving those sessions alive for up
    # to `DEFAULT_SESSION_TTL` means the change evicts nobody.
    revoke_sessions(db, account, except_token=except_token)
    db.flush()
    return method


def must_change_credential(db: Session, account: Account) -> bool:
    method = db.scalar(
        select(AuthMethod).where(
            AuthMethod.account_id == account.id, AuthMethod.method_type == MethodType.password
        )
    )
    return bool(method and method.must_change)


def revoke_sessions(
    db: Session, account: Account, except_token: str | None = None, now: datetime | None = None
) -> int:
    """End every session for this account. Returns how many were revoked.

    AI-CONTEXT: ONE primitive, three call sites, so the next credential-state change cannot
    forget (findings F1-1, F1-2). `deactivate_account` already knew the rule and stated it:

        "live sessions die with the account, or deactivation would take up to 30 days
         to bite on anyone already signed in"

    That is `DEFAULT_SESSION_TTL` talking, and it applies just as hard to a password change
    — a driver who changes their password BECAUSE they believe they are compromised was not
    evicting the attacker at all. Deactivation was one of three sites that needed it.

    IT EXPIRES IN PLACE rather than deleting, taking `end_impersonation`'s shape: `ended_at`
    and `expires_at` both set to now, dead immediately and not merely marked. Two reasons.
    A request already in flight against a deleted row gets a confusing failure where an
    expired row gives it a clean 401; and a revocation is a security event, so it should be
    legible afterwards rather than being a gap where rows used to be.

    `except_token` exists for exactly one case — a driver changing their own password. They
    must not be thrown out mid-action, because being signed out at the moment you change a
    credential reads as "that failed". Every other caller passes nothing.
    """
    when = now or datetime.now(UTC)
    revoked = 0
    for session in db.scalars(
        select(AuthSession).where(
            AuthSession.account_id == account.id,
            AuthSession.ended_at.is_(None),
        )
    ):
        if except_token is not None and session.token == except_token:
            continue
        session.ended_at = when
        session.expires_at = when  # dead immediately, not merely marked
        revoked += 1
    db.flush()
    return revoked


def revoke_sessions_for_token(
    db: Session, account: Account, token: str, now: datetime | None = None
) -> bool:
    """End ONE session — this account's, with this token. Returns whether it ended one.

    Scoped to the account deliberately: a token is already resolved to its owner before
    this is reached, and taking the account as well means a caller cannot end a session
    belonging to somebody else even by mistake.
    """
    when = now or datetime.now(UTC)
    session = db.scalar(
        select(AuthSession).where(
            AuthSession.account_id == account.id,
            AuthSession.token == token,
            AuthSession.ended_at.is_(None),
        )
    )
    if session is None:
        return False
    session.ended_at = when
    session.expires_at = when  # dead immediately, not merely marked
    db.flush()
    return True


def deactivate_account(db: Session, account: Account, now: datetime | None = None) -> Account:
    """Blocks login and hides driver-facing presence. Every row the account points at
    survives — this is a door being locked, not a record being erased."""
    account.active = False
    account.deactivated_at = now or datetime.now(UTC)
    # live sessions die with the account, or deactivation would take up to 30 days
    # to bite on anyone already signed in. The loop that used to live here is now
    # `revoke_sessions` — same rule, three call sites, one implementation.
    revoke_sessions(db, account, now=account.deactivated_at)
    db.flush()
    return account


def reactivate_account(db: Session, account: Account) -> Account:
    account.active = True
    account.deactivated_at = None
    db.flush()
    return account


def revoke_role(db: Session, account: Account, role: Role, org_id=None) -> bool:
    attachment = db.scalar(
        select(RoleAttachment).where(
            RoleAttachment.account_id == account.id,
            RoleAttachment.role == role,
            RoleAttachment.org_id == org_id,
        )
    )
    if attachment is None:
        return False
    db.delete(attachment)
    db.expire(account, ["roles"])
    db.flush()
    return True


def has_role(db: Session, account: Account, role: Role) -> bool:
    return any(r.role == role for r in account.roles)


def set_display_name(db: Session, account: Account, display_name: str | None) -> Account:
    account.display_name = (display_name or "").strip() or None
    db.flush()
    return account


# --- Scoped impersonation (§23 E-D5): "view as vendor" ---
# AI-CONTEXT: an admin sees the vendor portal exactly as that vendor sees it, which
# is the point — "my screen looks wrong" is unanswerable otherwise. The safety
# properties are structural, not procedural:
#   · the session belongs to the ADMIN and merely NAMES the vendor, so every write
#     attributes to the admin without anyone remembering to do so;
#   · it is time-boxed, because a support session left open is an unlocked door;
#   · `resolve_session` refuses it for ordinary auth, so it cannot reach a driver
#     endpoint even if the token leaks into one.
# Driver impersonation is not merely unimplemented — `start_impersonation` refuses
# any account that is not a vendor member (E-D5).
IMPERSONATION_TTL = timedelta(minutes=30)


class ImpersonationNotPermitted(Exception):
    """The target is not a vendor. Driver accounts are never impersonated (E-D5)."""


def start_impersonation(
    db: Session,
    admin: Account,
    target: Account,
    is_vendor: bool,
    ttl: timedelta = IMPERSONATION_TTL,
) -> AuthSession:
    if not is_vendor:
        raise ImpersonationNotPermitted(str(target.id))
    if not target.active:
        raise AccountInactive(str(target.id))
    session = AuthSession(
        account_id=admin.id,
        impersonating_account_id=target.id,
        token=secrets.token_urlsafe(48),
        expires_at=datetime.now(UTC) + ttl,
    )
    db.add(session)
    db.flush()
    return session


def end_impersonation(db: Session, token: str, now: datetime | None = None) -> AuthSession | None:
    session = db.scalar(select(AuthSession).where(AuthSession.token == token))
    if session is None or session.impersonating_account_id is None:
        return None
    session.ended_at = now or datetime.now(UTC)
    session.expires_at = session.ended_at  # dead immediately, not merely marked
    db.flush()
    return session


def resolve_impersonation(db: Session, token: str) -> tuple[Account, Account] | None:
    """Returns (actor_admin, subject_vendor_account) for a live impersonation token.
    Ordinary sessions return None here and impersonation tokens return None from
    `resolve_session` — the two paths never overlap."""
    session = db.scalar(select(AuthSession).where(AuthSession.token == token))
    if session is None or session.impersonating_account_id is None:
        return None
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        return None
    actor = db.get(Account, session.account_id)
    subject = db.get(Account, session.impersonating_account_id)
    if actor is None or subject is None:
        return None
    return actor, subject

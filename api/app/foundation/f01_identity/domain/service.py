import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth_methods import get_handler
from .enums import AuthorityType, MethodType, OrgType, Role, VerifyStatus
from .models import (
    Account,
    AuthMethod,
    AuthSession,
    DriverProfile,
    Organization,
    OrgMembership,
    RoleAttachment,
)
from .verifier import AuthorityVerifier, resolve_verifier

DEFAULT_SESSION_TTL = timedelta(days=30)
INVOICING_AUTHORITIES = {AuthorityType.own_mc, AuthorityType.leased}

# F13 flag gating the FMCSA verification seam (activation switch, PRD §6).
AUTHORITY_VERIFICATION_FLAG = "f01_authority_verification"


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
    if not handler.verify(method.secret_ref, password):
        return None
    method.last_used_at = datetime.now(UTC)
    db.flush()
    return db.get(Account, method.account_id)


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

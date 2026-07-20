import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth_methods import get_handler
from .enums import AuthorityType, MethodType, OrgType, Role
from .models import (
    Account,
    AuthMethod,
    AuthSession,
    DriverProfile,
    Organization,
    OrgMembership,
    RoleAttachment,
)

DEFAULT_SESSION_TTL = timedelta(days=30)
INVOICING_AUTHORITIES = {AuthorityType.own_mc, AuthorityType.leased}


class EmailAlreadyRegistered(Exception):
    pass


class AuthMethodNotEnabled(Exception):
    pass


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

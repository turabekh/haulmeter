import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

from .enums import AuthorityType, MethodType, OrgType, Role, VerifyStatus

SCHEMA = "f01"


class Account(Base):
    __tablename__ = "account"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # AI-CONTEXT: deactivation, never deletion. An account references money, claims
    # and evidence; erasing one would tear holes in records a third party may need to
    # verify. Deactivating blocks login and hides driver-facing presence while every
    # row it points at survives intact. Hard delete is a data-retention WORKFLOW
    # (PRD §17 Q16), not a button.
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), index=True
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    auth_methods: Mapped[list["AuthMethod"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )
    roles: Mapped[list["RoleAttachment"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )
    profile: Mapped["DriverProfile | None"] = relationship(
        back_populates="account", cascade="all, delete-orphan", uselist=False
    )


class AuthMethod(Base):
    """AI-CONTEXT: `must_change` carries the credential-reset flow. An admin can
    issue a TEMPORARY password and nothing else — they never see or set a permanent
    one, and the driver is forced to replace it at next login. Support that can read
    a password is support that can be impersonated by anyone who social-engineers it.
    """

    __tablename__ = "auth_method"
    __table_args__ = (
        UniqueConstraint("method_type", "identifier", name="uq_auth_method_type_identifier"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.account.id", ondelete="CASCADE"), index=True
    )
    method_type: Mapped[MethodType] = mapped_column(
        Enum(MethodType, name="method_type", schema=SCHEMA)
    )
    identifier: Mapped[str] = mapped_column(String(320))
    secret_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    is_primary: Mapped[bool] = mapped_column(default=False)
    # set when an admin issues a temporary credential; cleared when the holder
    # replaces it. Login is allowed but the client must force the change.
    must_change: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    account: Mapped[Account] = relationship(back_populates="auth_methods")


class AuthSession(Base):
    __tablename__ = "auth_session"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.account.id", ondelete="CASCADE"), index=True
    )
    token: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    client_skew_ms: Mapped[int | None] = mapped_column(nullable=True)
    # AI-CONTEXT: scoped impersonation (§23 E-D5). The session belongs to the ADMIN
    # (`account_id`) and names the vendor it acts for (`impersonating_account_id`),
    # never the other way round. That ordering is the whole safety property: every
    # write attributes to the admin structurally rather than by convention, and a
    # token carrying this column is refused by `current_account`, so it can never
    # reach a driver endpoint however it is passed around.
    impersonating_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.account.id", ondelete="CASCADE"), nullable=True, index=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LoginAttempt(Base):
    """AI-CONTEXT: throttling signal for the two unauthenticated hashing routes.

    THE NAME NO LONGER TELLS THE WHOLE TRUTH, and it is kept anyway: `kind` now
    discriminates `'login'` from `'register'`, so this table holds two signals. Renaming it
    would be churn across a migration, a model, three queries and their indexes to fix a
    noun — the docstring is cheaper and this paragraph is the fix.

    The two counters must not share a bucket. A registration flood from a carrier NAT would
    otherwise fill the per-IP window and lock honest drivers out of LOGIN on the same
    address — the exact false positive `LOGIN_MAX_PER_IP`'s own comment exists to avoid.

    They also record differently, and that asymmetry is deliberate. Login stores only
    FAILURES (a success clears the identifier's rows). Registration stores EVERY attempt,
    successful or not: what is being rationed there is the Argon2 work and the probing, and
    a successful registration costs exactly as much CPU as a failed one.

    Originally: failed authentications, which nothing anywhere counted (audit F-07).

    In POSTGRES rather than Redis, deliberately. `core/events.py` states the rule for
    Redis in this codebase — it is not a system of record, and `publish` swallows a
    failure so the product keeps working. That is right for a live channel and wrong
    for a security control: a throttle that disappears when Redis is unreachable fails
    OPEN, silently, which is the built-and-inert shape this project has now been taught
    five times. This one survives a restart and cannot quietly stop counting.

    Only FAILURES are stored. A successful login clears the identifier's rows, so the
    table holds exactly the attempts an attacker is making and nothing about ordinary
    use — and rows older than the window are deleted on write, because a table that
    only grows is F-09 in a second place.

    `identifier` is the SUBMITTED email, normalised, recorded whether or not an account
    exists. Counting only real accounts would make the throttle itself an account-
    existence oracle: "throttled after 5" versus "never throttled" answers the question
    the 401 is careful not to.
    """

    __tablename__ = "login_attempt"
    __table_args__ = (
        # `kind` sits in the MIDDLE: every query filters identifier/ip AND kind, then
        # windows on time. Migration 0069 replaced the two-column pair rather than adding
        # beside it — this is the one table that takes a row per attack attempt, so an
        # index that only ever costs writes is not free here.
        Index("ix_login_attempt_identifier_kind_time", "identifier", "kind", "occurred_at"),
        Index("ix_login_attempt_ip_kind_time", "client_ip", "kind", "occurred_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    identifier: Mapped[str] = mapped_column(String(320))
    # 'login' | 'register'. Server-defaulted so every pre-0069 row reads as what it was —
    # this table has only ever held login failures — with no backfill rewriting history.
    kind: Mapped[str] = mapped_column(String(20), default="login", server_default="login")
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Organization(Base):
    __tablename__ = "organization"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_type: Mapped[OrgType] = mapped_column(Enum(OrgType, name="org_type", schema=SCHEMA))
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    memberships: Mapped[list["OrgMembership"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class OrgMembership(Base):
    __tablename__ = "org_membership"
    __table_args__ = (
        UniqueConstraint("org_id", "account_id", name="uq_org_membership_org_account"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.organization.id", ondelete="CASCADE"), index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.account.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped[Organization] = relationship(back_populates="memberships")


class RoleAttachment(Base):
    __tablename__ = "role_attachment"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "role", "org_id", name="uq_role_attachment_account_role_org"
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.account.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[Role] = mapped_column(Enum(Role, name="role", schema=SCHEMA))
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.organization.id", ondelete="CASCADE"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped[Account] = relationship(back_populates="roles")


class DriverProfile(Base):
    __tablename__ = "driver_profile"
    __table_args__ = {"schema": SCHEMA}

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.account.id", ondelete="CASCADE"), primary_key=True
    )
    authority_type: Mapped[AuthorityType | None] = mapped_column(
        Enum(AuthorityType, name="authority_type", schema=SCHEMA), nullable=True
    )
    mc_number: Mapped[str | None] = mapped_column(String(12), nullable=True)
    dot_number: Mapped[str | None] = mapped_column(String(12), nullable=True)
    legal_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    authority_verify_status: Mapped[VerifyStatus] = mapped_column(
        Enum(VerifyStatus, name="verify_status", schema=SCHEMA),
        default=VerifyStatus.unverified,
        server_default=VerifyStatus.unverified.value,
    )
    authority_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    truck_length_ft: Mapped[int | None] = mapped_column(nullable=True)
    truck_height_in: Mapped[int | None] = mapped_column(nullable=True)
    gross_weight_lbs: Mapped[int | None] = mapped_column(nullable=True)
    trailer_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    equipment_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # AI-CONTEXT: E2 equipment registration — SELF-REPORTED, never verified (§11.7).
    # Plate + unit ride on M6 bookings and M13-FR7 service callouts; VIN is
    # format-validated only (no decode service, PRD extension §E2).
    plate_state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    plate_number: Mapped[str | None] = mapped_column(String(12), nullable=True)
    unit_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    vin: Mapped[str | None] = mapped_column(String(17), nullable=True)
    home_timezone: Mapped[str] = mapped_column(String(60), default="UTC")
    locale: Mapped[str] = mapped_column(String(12), default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    account: Mapped[Account] = relationship(back_populates="profile")

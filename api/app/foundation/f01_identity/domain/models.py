import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

from .enums import AuthorityType, MethodType, OrgType, Role

SCHEMA = "f01"


class Account(Base):
    __tablename__ = "account"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
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
    truck_length_ft: Mapped[int | None] = mapped_column(nullable=True)
    truck_height_in: Mapped[int | None] = mapped_column(nullable=True)
    gross_weight_lbs: Mapped[int | None] = mapped_column(nullable=True)
    trailer_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    equipment_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    home_timezone: Mapped[str] = mapped_column(String(60), default="UTC")
    locale: Mapped[str] = mapped_column(String(12), default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    account: Mapped[Account] = relationship(back_populates="profile")

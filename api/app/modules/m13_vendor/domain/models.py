import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

from .enums import (
    AppearanceStatus,
    DocumentKind,
    DocumentReviewStatus,
    MemberRole,
    VendorStatus,
    VendorType,
    VendorVerifyStatus,
)

SCHEMA = "m13"
ACCOUNT_FK = "f01.account.id"
FACILITY_FK = "f02.facility.id"
DOCUMENT_FK = "f06.document.id"


class Vendor(Base):
    __tablename__ = "vendor"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    vendor_type: Mapped[VendorType] = mapped_column(
        Enum(VendorType, name="vendor_type", schema=SCHEMA)
    )
    name: Mapped[str] = mapped_column(String(160))
    # Q-5 blocking keys: normalized name + metro and phone are how a duplicate
    # registration is caught before a driver ever sees the same cook twice
    name_normalized: Mapped[str] = mapped_column(String(160), index=True)
    metro: Mapped[str] = mapped_column(String(80), default="", index=True)
    contact_phone: Mapped[str] = mapped_column(String(20), default="", index=True)

    categories: Mapped[list] = mapped_column(JSON, default=list)
    languages: Mapped[list] = mapped_column(JSON, default=list)
    # Q-4: "we source from a halal butcher" and "no halal claim" are both complete
    # answers; a BLANK is not. The boolean is what the publish floor checks, so a
    # vendor can honestly decline to claim halal without being blocked.
    halal_disclosure: Mapped[str | None] = mapped_column(Text, nullable=True)
    halal_answered: Mapped[bool] = mapped_column(Boolean, default=False)

    verify_status: Mapped[VendorVerifyStatus] = mapped_column(
        Enum(VendorVerifyStatus, name="vendor_verify_status", schema=SCHEMA),
        default=VendorVerifyStatus.unverified,
        server_default=VendorVerifyStatus.unverified.value,
    )
    status: Mapped[VendorStatus] = mapped_column(
        Enum(VendorStatus, name="vendor_status", schema=SCHEMA),
        default=VendorStatus.active,
        server_default=VendorStatus.active.value,
        index=True,
    )
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.vendor.id", ondelete="SET NULL"), nullable=True
    )

    # Q-2: three consecutive unconfirmed appearances suspend publishing pending F14
    # review. The counter is consecutive-only — one confirmed show-up clears it.
    consecutive_no_shows: Mapped[int] = mapped_column(Integer, default=0)
    publish_suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    # Q-1: a vendor with no publish in 28 days leaves discovery (the profile stays)
    last_published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    is_dev: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    members: Mapped[list["VendorMember"]] = relationship(
        back_populates="vendor", cascade="all, delete-orphan"
    )
    documents: Mapped[list["VendorDocument"]] = relationship(
        back_populates="vendor", cascade="all, delete-orphan"
    )


class VendorMember(Base):
    __tablename__ = "vendor_member"
    __table_args__ = (
        UniqueConstraint("vendor_id", "account_id", name="uq_vendor_member"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.vendor.id", ondelete="CASCADE"), index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    member_role: Mapped[MemberRole] = mapped_column(
        Enum(MemberRole, name="member_role", schema=SCHEMA), default=MemberRole.helper
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    vendor: Mapped[Vendor] = relationship(back_populates="members")


class VendorDocument(Base):
    __tablename__ = "vendor_document"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.vendor.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(DOCUMENT_FK, ondelete="CASCADE"))
    doc_kind: Mapped[DocumentKind] = mapped_column(
        Enum(DocumentKind, name="vendor_document_kind", schema=SCHEMA)
    )
    review_status: Mapped[DocumentReviewStatus] = mapped_column(
        Enum(DocumentReviewStatus, name="vendor_document_review", schema=SCHEMA),
        default=DocumentReviewStatus.pending,
        server_default=DocumentReviewStatus.pending.value,
    )
    moderation_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    vendor: Mapped[Vendor] = relationship(back_populates="documents")


class Appearance(Base):
    """AI-CONTEXT: one vendor at one facility for one time window. A weekly schedule
    MATERIALIZES concrete occurrence rows sharing a series_id rather than expanding a
    rule at query time, because Q-1 (expiry) and Q-2 (show-up rate) both count
    per-occurrence — a rule can't be marked lapsed or scored."""

    __tablename__ = "appearance"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.vendor.id", ondelete="CASCADE"), index=True
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(FACILITY_FK, ondelete="CASCADE"), index=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[AppearanceStatus] = mapped_column(
        Enum(AppearanceStatus, name="appearance_status", schema=SCHEMA),
        default=AppearanceStatus.scheduled,
        server_default=AppearanceStatus.scheduled.value,
        index=True,
    )
    # {"weekly": [0, 2, 4]} — ISO weekdays this series repeats on. Set on every
    # occurrence of the series so a cancel-series can find its siblings.
    recurrence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    series_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    # the vendor attests written permission from the property; ranks above
    # unapproved (Q-3). PRD §17 Q11 asks whether attestation should become upload.
    property_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    # Q-2: did the crowd actually confirm this vendor showed up? Set by the sweep
    # when the window closes, and the denominator of the show-up rate.
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    offerings: Mapped[list["Offering"]] = relationship(
        back_populates="appearance", cascade="all, delete-orphan"
    )


class Offering(Base):
    """A menu line. `price_cents` is INFORMATION ONLY — Phase A processes no
    payments and the platform sells nothing (PRD extension §E1.1)."""

    __tablename__ = "offering"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    appearance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.appearance.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    price_cents: Mapped[int] = mapped_column(Integer)
    portions: Mapped[int | None] = mapped_column(Integer, nullable=True)

    appearance: Mapped[Appearance] = relationship(back_populates="offerings")

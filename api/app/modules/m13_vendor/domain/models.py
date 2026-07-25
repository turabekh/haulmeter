import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
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
    ClaimStatus,
    DocumentKind,
    DocumentReviewStatus,
    MemberRole,
    ModerationReason,
    PromotionScope,
    PromotionStatus,
    ReviewStatus,
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
    menu_items: Mapped[list["MenuItem"]] = relationship(
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
    # unapproved (Q-3). PRD §17 Q11 RESOLVED (2026-07-25): the self-attestation is
    # sufficient — no consent document is required — because a demonstrated FALSE
    # attestation is actionable through the Q-8 moderation path
    # (ModerationReason.false_property_attestation). The honesty of the ranking
    # boost rests on that consequence existing, so the two ship together.
    property_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    # Q-2: did the crowd actually confirm this vendor showed up? Set by the sweep
    # when the window closes, and the denominator of the show-up rate.
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    offerings: Mapped[list["Offering"]] = relationship(
        back_populates="appearance", cascade="all, delete-orphan"
    )


class Offering(Base):
    """A menu line AS PUBLISHED for one appearance. `price_cents` is INFORMATION
    ONLY — Phase A processes no payments and the platform sells nothing (PRD
    extension §E1.1).

    AI-CONTEXT: this stays keyed to the APPEARANCE, not to the vendor, and that is
    the point. It is a SNAPSHOT of what was advertised for that window. A cook who
    raises a price today must not silently rewrite what a driver was shown last
    Tuesday — the past is what the reliability and review record are about, and a
    menu that rewrote history would make both unauditable. `MenuItem` below is the
    editable list; publishing COPIES it into rows here."""

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


class MenuItem(Base):
    """AI-CONTEXT: the vendor's STANDING menu — what they usually sell, and for how
    much. Offerings hung off appearances alone, so a cook retyped every dish and
    every price for every window; this is the list they keep.

    It is deliberately NOT what a driver reads. Publishing copies these rows into
    per-appearance `Offering` snapshots, so editing the menu changes what will be
    advertised NEXT, never what was advertised before. `price_cents` is information
    only, exactly as on Offering — nothing here moves money."""

    __tablename__ = "menu_item"
    __table_args__ = (
        UniqueConstraint("vendor_id", "name", name="uq_menu_item_vendor_name"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.vendor.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    price_cents: Mapped[int] = mapped_column(Integer)
    # how many the cook usually brings; carried onto the appearance as the starting
    # portion count. None means "they don't count portions", not "zero".
    portions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # off the menu without losing it — a seasonal dish comes back, and deleting it
    # would take its price history with it
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    vendor: Mapped[Vendor] = relationship(back_populates="menu_items")


class VendorReview(Base):
    """FR5. Distinct-REVIEWER counting is the §11.7 discipline here: a driver who
    reviews the same vendor again replaces their earlier verdict rather than adding
    a second voice, so "12 drivers" always means twelve people."""

    __tablename__ = "vendor_review"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.vendor.id", ondelete="CASCADE"), index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    rating: Mapped[int] = mapped_column(Integer)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, name="vendor_review_status", schema=SCHEMA),
        default=ReviewStatus.visible,
        server_default=ReviewStatus.visible.value,
        index=True,
    )
    moderation_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Promotion(Base):
    """FR6 / PRD §17 Q10. A promotion is vendor-supplied text in a LABELLED slot. It
    is deliberately unreachable from the ranking path: `rank_entries` takes no
    promotion argument and this table is read by a separate function, so Q-3's
    "promotions never reorder organic results" holds structurally rather than by
    reviewer vigilance. Free in Phase A; no price, bid, or billing column exists."""

    __tablename__ = "promotion"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.vendor.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(String(140))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    scope: Mapped[PromotionScope] = mapped_column(
        Enum(PromotionScope, name="promotion_scope", schema=SCHEMA),
        default=PromotionScope.own_appearances,
        server_default=PromotionScope.own_appearances.value,
    )
    status: Mapped[PromotionStatus] = mapped_column(
        Enum(PromotionStatus, name="promotion_status", schema=SCHEMA),
        default=PromotionStatus.active,
        server_default=PromotionStatus.active.value,
        index=True,
    )
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    moderation_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FacilityClaim(Base):
    """FR7. Curated facts live HERE, never written back to f02.facility: a claim can
    only ever ADD to what ingestion knows, so E3.2's union discipline ("a claim edit
    cannot erase ingested facts") holds by construction instead of by care."""

    __tablename__ = "facility_claim"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.vendor.id", ondelete="CASCADE"), index=True
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(FACILITY_FK, ondelete="CASCADE"), index=True
    )
    claimed_name: Mapped[str] = mapped_column(String(160))
    name_match_score: Mapped[float] = mapped_column(Float, default=0.0)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(DOCUMENT_FK, ondelete="SET NULL"), nullable=True
    )
    status: Mapped[ClaimStatus] = mapped_column(
        Enum(ClaimStatus, name="claim_status", schema=SCHEMA),
        default=ClaimStatus.pending,
        server_default=ClaimStatus.pending.value,
        index=True,
    )
    moderation_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    # curated additions — additive only, unioned over the ingested facts on read
    services_added: Mapped[list] = mapped_column(JSON, default=list)
    hours: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ContentReport(Base):
    """Q-8. One row per reporting driver, so a vendor listing can require reports
    from N DISTINCT drivers before it is hidden — a single report must not become a
    competitor's kill switch on someone's livelihood."""

    __tablename__ = "content_report"
    __table_args__ = (
        UniqueConstraint(
            "content_kind", "content_ref", "account_id", name="uq_report_content_account"
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    content_kind: Mapped[str] = mapped_column(String(40), index=True)
    content_ref: Mapped[uuid.UUID] = mapped_column(index=True)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.vendor.id", ondelete="CASCADE"), index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    reason: Mapped[ModerationReason] = mapped_column(
        Enum(ModerationReason, name="moderation_reason", schema=SCHEMA)
    )
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    upheld: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # None until decided
    # a moderator's third verdict: the report itself was the abuse. Counts toward the
    # REPORTER's record, not the reported party's (Admin Console 2.0 decision 4c).
    frivolous: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # a report from the vendor's own owner/member is RECORDED (so a moderator can see
    # the attempt) but excluded from the distinct-driver hide count — dropping it
    # silently would hide the abuse from the only person able to act on it
    self_reported: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

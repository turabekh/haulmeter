import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

from .enums import ReviewStatus

SCHEMA = "m02"
ACCOUNT_FK = "f01.account.id"
FACILITY_FK = "f02.facility.id"


class FacilityProfile(Base):
    __tablename__ = "facility_profile"
    __table_args__ = {"schema": SCHEMA}

    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(FACILITY_FK, ondelete="CASCADE"), primary_key=True
    )
    check_in_procedure: Mapped[str | None] = mapped_column(Text, nullable=True)
    ppe_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    restrooms: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    overnight_parking: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    backing_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    hazards: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FacilityReview(Base):
    __tablename__ = "facility_review"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(FACILITY_FK, ondelete="CASCADE"), index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    ratings: Mapped[dict] = mapped_column(JSON, default=dict)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, name="review_status", schema=SCHEMA),
        default=ReviewStatus.pending,
        index=True,
    )
    moderation_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

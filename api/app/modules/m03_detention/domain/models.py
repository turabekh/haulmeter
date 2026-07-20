import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

from .enums import ClaimMode, ClaimState, DetentionTrigger

SCHEMA = "m03"
ACCOUNT_FK = "f01.account.id"


class DetentionClaim(Base):
    __tablename__ = "detention_claim"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    stop_ref: Mapped[uuid.UUID] = mapped_column(index=True)
    facility_ref: Mapped[uuid.UUID] = mapped_column()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    counterparty_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    mode: Mapped[ClaimMode] = mapped_column(Enum(ClaimMode, name="claim_mode", schema=SCHEMA))
    trigger: Mapped[DetentionTrigger] = mapped_column(
        Enum(DetentionTrigger, name="detention_trigger", schema=SCHEMA),
        default=DetentionTrigger.arrival,
    )
    free_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detention_rate_cents_per_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detention_seconds: Mapped[int] = mapped_column(Integer, default=0)
    amount_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    evidence_log_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    receivable_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    state: Mapped[ClaimState] = mapped_column(
        Enum(ClaimState, name="claim_state", schema=SCHEMA), default=ClaimState.open
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

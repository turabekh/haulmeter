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
    start_notice_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # AI-CONTEXT: the DRIVER's two alerts, deliberately separate from
    # `start_notice_sent_at` above — which records the BROKER's notice (§23 entry 106).
    # Two audiences, two records: one column would have made "the driver has been told"
    # mean "the counterparty was emailed", and those come from different code paths at
    # different times. Each is set when the alert is DISPATCHED, not delivered, so a
    # notification F8 suppresses is not re-offered every minute until one gets through.
    driver_start_alert_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    driver_warning_alert_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # AI-CONTEXT: when this claim began watching the stop (§23 entry 73). The clock may
    # not start before it, which is what keeps a previous visit to the same dock out of
    # this load's money. Explicit rather than read off `created_at`: the anchor the
    # amount depends on should be statable by a caller and printable on the invoice.
    clock_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    state: Mapped[ClaimState] = mapped_column(
        Enum(ClaimState, name="claim_state", schema=SCHEMA), default=ClaimState.open
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

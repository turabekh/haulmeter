import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

from .enums import CapturePhase

SCHEMA = "m05"
ACCOUNT_FK = "f01.account.id"


class OnTimeProof(Base):
    __tablename__ = "on_time_proof"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    stop_ref: Mapped[uuid.UUID] = mapped_column(index=True)
    checked_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    within_window: Mapped[bool] = mapped_column(Boolean, default=False)
    notice_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_log_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConditionCapture(Base):
    __tablename__ = "condition_capture"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    stop_ref: Mapped[uuid.UUID] = mapped_column(index=True)
    phase: Mapped[CapturePhase] = mapped_column(
        Enum(CapturePhase, name="capture_phase", schema=SCHEMA)
    )
    evidence_log_ref: Mapped[uuid.UUID] = mapped_column()
    photo_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Incident(Base):
    __tablename__ = "incident"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    load_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    kind: Mapped[str] = mapped_column(String(60))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_log_ref: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OnTimeConsent(Base):
    """AI-CONTEXT: M5-FR1's per-load opt-in.

    It lives in M5, not on F5's `Stop`, because whether to tell a broker you arrived
    is a protection decision and F5 should stay a generic load record. Keyed by LOAD
    because that is the unit a driver agrees to — PRD §8.5 says "opt-in per load" —
    while the notice itself fires per stop, once per appointment.

    The consent gates the NOTICE only. The proof artifact is filed on every arrival
    regardless: it is the driver's own protection, and a driver who did not want the
    broker told still wants to be able to prove they were on time.
    """

    __tablename__ = "on_time_consent"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    load_ref: Mapped[uuid.UUID] = mapped_column(unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    counterparty_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

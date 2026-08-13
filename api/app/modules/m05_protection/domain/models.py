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
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

from .enums import CapturePhase, StopPacketState

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
    # AI-CONTEXT: `notice_sent` means the counterparty was REACHED, and it is written by
    # the delivery sweep rather than by the request that files the proof. Sending is
    # asynchronous now (2.5 s of SMTP inside a handler, holding a pooled DB connection —
    # §23 records that outage), so at file time nothing has gone out and this is False.
    #
    # `notice_message_ref` is what lets it ever become True: it points at the F8 row, and
    # `reconcile_on_time_notices` stamps this the moment that row actually lands. Without
    # the ref there is nothing to reconcile AGAINST, and the column would have been
    # permanently False — a stored field that always lies, which is the F-06 defect with
    # the sign flipped.
    notice_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    notice_message_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
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


class StopPacket(Base):
    """AI-CONTEXT: A1 — the paperwork handed to a dispatcher after a stop.

    It exists as a ROW because it is drafted by one actor (an EXIT event) and sent by
    another (the driver), and everything in between is waiting. A packet held only in
    memory could not be reviewed, which is the requirement.

    ONE PER STOP, enforced. Geofences bounce, and two drafts for one stop is two
    documents a driver has to reject — the second of which teaches them the queue is
    noise, which is how a review step becomes a rubber stamp.
    """

    __tablename__ = "stop_packet"
    __table_args__ = (
        UniqueConstraint("stop_ref", name="uq_stop_packet_stop"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    stop_ref: Mapped[uuid.UUID] = mapped_column(index=True)
    counterparty_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    state: Mapped[StopPacketState] = mapped_column(
        Enum(StopPacketState, name="stop_packet_state", schema=SCHEMA),
        default=StopPacketState.draft,
    )
    drafted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # the decision's own timestamp. Separate from `sent_at` because "the driver declined
    # this on Tuesday" and "this reached a dispatcher on Tuesday" are different facts,
    # and a column doing both jobs could not say which one happened (§23 entry 133's
    # lesson, one table over).
    discarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shared_pack_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

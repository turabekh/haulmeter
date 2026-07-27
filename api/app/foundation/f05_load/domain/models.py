import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

from .enums import CounterpartyKind, LoadSource, LoadStatus, StopStatus, StopType

SCHEMA = "f05"
ACCOUNT_FK = "f01.account.id"
FACILITY_FK = "f02.facility.id"


class Counterparty(Base):
    __tablename__ = "counterparty"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(300))
    kind: Mapped[CounterpartyKind] = mapped_column(
        Enum(CounterpartyKind, name="counterparty_kind", schema=SCHEMA)
    )
    mc_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    payment_behavior: Mapped[dict] = mapped_column(JSON, default=dict)
    claim_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Load(Base):
    __tablename__ = "load"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    counterparty_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.counterparty.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reference_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    rate_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detention_rate_cents_per_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    free_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accessorial_terms: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[LoadSource] = mapped_column(
        Enum(LoadSource, name="load_source", schema=SCHEMA), default=LoadSource.manual
    )
    status: Mapped[LoadStatus] = mapped_column(
        Enum(LoadStatus, name="load_status", schema=SCHEMA), default=LoadStatus.draft
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    counterparty: Mapped[Counterparty | None] = relationship()
    stops: Mapped[list["Stop"]] = relationship(
        back_populates="load", cascade="all, delete-orphan", order_by="Stop.sequence"
    )


class Stop(Base):
    __tablename__ = "stop"
    __table_args__ = (
        UniqueConstraint("load_id", "sequence", name="uq_stop_load_sequence"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    load_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.load.id", ondelete="CASCADE"), index=True
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(FACILITY_FK, ondelete="RESTRICT"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    stop_type: Mapped[StopType] = mapped_column(Enum(StopType, name="stop_type", schema=SCHEMA))
    appointment_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    appointment_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # AI-CONTEXT: provenance of THIS window, not of the load it belongs to. M5-FR1
    # shows it so a driver can weigh a machine read against a value they typed; it was
    # being reported from `load.source`, a different fact about a different object.
    appointment_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    free_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detention_rate_cents_per_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[StopStatus] = mapped_column(
        Enum(StopStatus, name="stop_status", schema=SCHEMA), default=StopStatus.pending
    )
    geofence_armed: Mapped[bool] = mapped_column(default=False)
    evidence_log_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    departed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    load: Mapped[Load] = relationship(back_populates="stops")

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

from .enums import ArtifactType, RecordType

SCHEMA = "f04"
ACCOUNT_FK = "f01.account.id"


class EvidenceLog(Base):
    __tablename__ = "evidence_log"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    stop_ref: Mapped[uuid.UUID | None] = mapped_column(index=True, nullable=True)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    records: Mapped[list["EvidenceRecord"]] = relationship(
        back_populates="log", cascade="all, delete-orphan", order_by="EvidenceRecord.seq"
    )
    artifacts: Mapped[list["EvidenceArtifact"]] = relationship(
        back_populates="log", cascade="all, delete-orphan"
    )


class EvidenceRecord(Base):
    __tablename__ = "evidence_record"
    __table_args__ = (
        UniqueConstraint("log_id", "seq", name="uq_evidence_record_log_seq"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    log_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.evidence_log.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    record_type: Mapped[RecordType] = mapped_column(
        Enum(RecordType, name="record_type", schema=SCHEMA)
    )
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    prev_hash: Mapped[str] = mapped_column(String(64))
    record_hash: Mapped[str] = mapped_column(String(64), index=True)

    log: Mapped[EvidenceLog] = relationship(back_populates="records")


class EvidenceArtifact(Base):
    __tablename__ = "evidence_artifact"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    log_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.evidence_log.id", ondelete="CASCADE"), index=True
    )
    record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.evidence_record.id", ondelete="CASCADE"), index=True
    )
    artifact_type: Mapped[ArtifactType] = mapped_column(
        Enum(ArtifactType, name="artifact_type", schema=SCHEMA)
    )
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    exif: Mapped[dict] = mapped_column(JSON, default=dict)
    gps_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    log: Mapped[EvidenceLog] = relationship(back_populates="artifacts")


class ChainAnchor(Base):
    __tablename__ = "chain_anchor"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    log_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.evidence_log.id", ondelete="CASCADE"), index=True
    )
    head_seq: Mapped[int] = mapped_column(Integer)
    head_hash: Mapped[str] = mapped_column(String(64))
    external_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)
    anchored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

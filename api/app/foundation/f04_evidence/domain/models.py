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


class SharedPack(Base):
    """AI-CONTEXT: what was actually sent to a counterparty, pinned.

    Rendering is deterministic, so a pack can always be regenerated — but a pack
    shared at 14:00 and regenerated at 16:00 after another photo lands is a DIFFERENT
    document. In a dispute the question is "what did we send them", so the bytes are
    stored and hashed at the moment of sharing and the link serves those bytes
    forever. The chain is free to grow afterwards; that is precisely why this exists.

    `content_hash` and `storage_key` outlive revocation: closing a link does not
    unsend a document, and the record of what was sent must survive the decision to
    stop hosting it.
    """

    __tablename__ = "shared_pack"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    log_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.evidence_log.id", ondelete="CASCADE"), index=True
    )
    template: Mapped[str] = mapped_column(String(40))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(500))
    # opaque and random rather than signed: we store the row anyway for the hash and
    # the key, so lookup is free and revocation is one column instead of a denylist
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    shared_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="SET NULL"), nullable=True
    )
    recipient: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # AI-CONTEXT: these are metadata about a URL, NOT evidence about a party (F4-1).
    # The comment here used to say "they opened it on the 12th is evidence" and the chain
    # carried an append saying so — but mail-security scanners fetch links before a human
    # sees the mail, so the only honest reading is "the link was reached". The append is
    # gone; these keep counting, and the driver's screen states the caveat.
    opened_count: Mapped[int] = mapped_column(Integer, default=0)
    first_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

from .enums import DocType, ExtractionStatus

SCHEMA = "f06"
ACCOUNT_FK = "f01.account.id"


class Document(Base):
    __tablename__ = "document"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    doc_type: Mapped[DocType] = mapped_column(Enum(DocType, name="doc_type", schema=SCHEMA))
    storage_key: Mapped[str] = mapped_column(String(600))
    filename: Mapped[str | None] = mapped_column(String(300), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    byte_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)

    issued_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    sent_reminders: Mapped[list] = mapped_column(JSON, default=list)

    extraction: Mapped[dict] = mapped_column(JSON, default=dict)
    extraction_status: Mapped[ExtractionStatus] = mapped_column(
        Enum(ExtractionStatus, name="extraction_status", schema=SCHEMA),
        default=ExtractionStatus.pending,
    )

    subject_kind: Mapped[str | None] = mapped_column(String(40), nullable=True)
    subject_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

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

    # AI-CONTEXT: whether the derivative has been ATTEMPTED, which is the only thing a
    # column is needed for — the key itself is `<storage_key>.thumb.jpg`, always
    # derivable, and storing it too would be a second fact to keep in step with the first.
    # NULL means the job has not reached this row yet; "none" means it tried and there is
    # no image here (a PDF rate con is the normal case, not a failure), so a scanned
    # contract is never re-decoded every five minutes forever.
    thumbnail_state: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)

    issued_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    sent_reminders: Mapped[list] = mapped_column(JSON, default=list)

    extraction: Mapped[dict] = mapped_column(JSON, default=dict)
    extraction_status: Mapped[ExtractionStatus] = mapped_column(
        Enum(ExtractionStatus, name="extraction_status", schema=SCHEMA),
        default=ExtractionStatus.pending,
    )

    # AI-CONTEXT: a credential is REPLACED, never overwritten. §17 Q16 forbids hard
    # delete, and an old CDL is still evidence of what the driver held on the date of
    # an inspection six months ago — destroying it would destroy the answer to a
    # question someone may yet ask. So a new one archives the old and points back at
    # it, and the chain of what was held when stays walkable.
    #
    # WHY it was archived is a different fact from THAT it was, and the archive list
    # has to say which: "replaced by your new CDL" and "you removed this" read
    # differently to the driver deciding whether to restore it. `superseded` is not
    # restorable while its replacement is live; `removed_by_driver` always is.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archive_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    subject_kind: Mapped[str | None] = mapped_column(String(40), nullable=True)
    subject_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

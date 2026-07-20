import hashlib
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .enums import DocType, ExtractionStatus
from .models import Document
from .storage import ObjectStorage, default_storage

REMINDER_OFFSETS = [30, 14, 3]


def _content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def store_document(
    db: Session,
    account_id,
    doc_type: DocType,
    content: bytes,
    filename: str | None = None,
    content_type: str | None = None,
    issued_on: date | None = None,
    expires_on: date | None = None,
    subject_kind: str | None = None,
    subject_ref=None,
    storage: ObjectStorage | None = None,
) -> Document:
    storage = storage or default_storage()
    document_id = uuid.uuid4()
    key = f"{account_id}/{document_id}/{filename or 'file'}"
    storage.put(key, content, content_type)

    document = Document(
        id=document_id,
        account_id=account_id,
        doc_type=doc_type,
        storage_key=key,
        filename=filename,
        content_type=content_type,
        byte_size=len(content),
        content_hash=_content_hash(content),
        issued_on=issued_on,
        expires_on=expires_on,
        subject_kind=subject_kind,
        subject_ref=subject_ref,
        sent_reminders=[],
        extraction={},
        extraction_status=ExtractionStatus.pending,
    )
    db.add(document)
    db.flush()
    return document


def get_document_bytes(
    db: Session, document: Document, storage: ObjectStorage | None = None
) -> bytes:
    storage = storage or default_storage()
    return storage.get(document.storage_key)


def apply_extraction(db: Session, document: Document, extraction: dict) -> Document:
    document.extraction = extraction
    document.extraction_status = ExtractionStatus.extracted
    db.flush()
    return document


def mark_extraction_failed(db: Session, document: Document) -> Document:
    document.extraction_status = ExtractionStatus.failed
    db.flush()
    return document


def documents_for_account(
    db: Session, account_id, doc_type: DocType | None = None
) -> list[Document]:
    stmt = select(Document).where(Document.account_id == account_id)
    if doc_type is not None:
        stmt = stmt.where(Document.doc_type == doc_type)
    return list(db.scalars(stmt.order_by(Document.uploaded_at.desc())))


def active_reminder_offset(expires_on: date, as_of: date) -> int | None:
    days_until = (expires_on - as_of).days
    if days_until < 0:
        return None
    lower = -1
    for offset in sorted(REMINDER_OFFSETS):
        if lower < days_until <= offset:
            return offset
        lower = offset
    return None


def due_reminders(db: Session, as_of: date, account_id=None) -> list[tuple[Document, int]]:
    stmt = select(Document).where(Document.expires_on.is_not(None))
    if account_id is not None:
        stmt = stmt.where(Document.account_id == account_id)
    due: list[tuple[Document, int]] = []
    for document in db.scalars(stmt):
        offset = active_reminder_offset(document.expires_on, as_of)
        if offset is not None and offset not in (document.sent_reminders or []):
            due.append((document, offset))
    return due


def mark_reminder_sent(db: Session, document: Document, offset: int) -> Document:
    sent = list(document.sent_reminders or [])
    if offset not in sent:
        sent.append(offset)
    document.sent_reminders = sent
    db.flush()
    return document

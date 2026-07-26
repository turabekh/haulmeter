import hashlib
import uuid
from datetime import UTC, date, datetime

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
    db: Session,
    account_id,
    doc_type: DocType | None = None,
    include_archived: bool = False,
) -> list[Document]:
    """Archived documents are excluded by DEFAULT. The wallet's job is to produce the
    credential a driver holds now; a superseded CDL surfacing beside the current one
    at a roadside inspection is exactly the confusion this must not create. They are
    still reachable — `include_archived` — because §17 Q16 keeps them."""
    stmt = select(Document).where(Document.account_id == account_id)
    if doc_type is not None:
        stmt = stmt.where(Document.doc_type == doc_type)
    if not include_archived:
        stmt = stmt.where(Document.archived_at.is_(None))
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


def supersede_document(db: Session, old: Document, new: Document, now: datetime | None = None):
    """Archive `old` in favour of `new`. Nothing is deleted and no bytes are touched —
    what changes is which document the wallet PRODUCES, which is the only thing a
    driver or an inspector cares about."""
    old.archived_at = now or datetime.now(UTC)
    old.superseded_by_id = new.id
    db.flush()
    return old


def update_document_meta(
    db: Session,
    document: Document,
    doc_type: DocType | None = None,
    expires_on: date | None = None,
) -> Document:
    """Correct what was recorded ABOUT a document — a mistyped expiry, a credential
    filed under the wrong type. The bytes are never edited: replacing the image is a
    new capture, which supersedes, so that the thing a driver files and the thing an
    inspector sees can never quietly diverge."""
    if doc_type is not None:
        document.doc_type = doc_type
    if expires_on is not None:
        document.expires_on = expires_on
        # the reminder ladder is recomputed from the new date: a corrected expiry
        # whose 30-day rung was already "sent" against the wrong one would go silent
        document.sent_reminders = []
    db.flush()
    return document


def documents_for_subject(db: Session, subject_kind: str, subject_ref, doc_type=None) -> list:
    """What is attached to one thing — a stop, a load, a claim. The columns existed
    from the start and nothing could query them, so a caller wanting "is there a BOL
    for this stop" had to load every document the account owns and filter in Python."""
    stmt = select(Document).where(
        Document.subject_kind == subject_kind,
        Document.subject_ref == subject_ref,
    )
    if doc_type is not None:
        stmt = stmt.where(Document.doc_type == doc_type)
    return list(db.scalars(stmt.order_by(Document.uploaded_at)))


def due_reminders(db: Session, as_of: date, account_id=None) -> list[tuple[Document, int]]:
    # an archived credential has been replaced; warning about its expiry would send a
    # driver to renew something they already renewed
    stmt = select(Document).where(Document.expires_on.is_not(None), Document.archived_at.is_(None))
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

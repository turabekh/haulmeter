"""AI-CONTEXT: the 30-day audio retention class and its sweep (E3 §E3.4.3, D14 signed).

THE SWEEP SHIPS WITH THE CLASS, and that is the whole reason this file is not just a
column. A retention class with no job that acts on it deletes nothing, ever — and the
validation law is explicit that *a deferral that cannot fail is indistinguishable from a
finished feature*. The clock is not hypothetical either: the gate window is 45 days and
the promise is 30, so a class-without-sweep guarantees the platform holds a driver's voice
past the line the owner signed.

WHAT THE SWEEP MAY TOUCH, stated as a rule rather than a filter: **only rows whose
`retention_class` column says so.** Never a MIME type, never a module, never a path
prefix. A guard that infers is a guard that will one day infer wrong about somebody's CDL,
and the cost of that mistake is not symmetrical with the cost of keeping an extra file.
`delete_bytes` refuses a `permanent` row even when asked directly, so the rule holds for
callers that are not the sweep.

WHAT IS DELETED AND WHAT IS NOT. The object's BYTES go. The `f06.document` row stays, with
`bytes_deleted_at` set — so "a recording existed, for this turn, until this date" remains
answerable. `m15.turn` keeps its transcript, confidence and scores, which E3 requires:
"derived transcripts, scores, and skill state persist". A driver loses the recording of
their voice; nobody loses the record that they practised.

WHAT THIS FILE DELIBERATELY DOES NOT DO: there is no driver-facing "delete my audio" UI
and no notification when a sweep runs. The first rides Session B's consent flow; the
second would be a new notification class, which is a §22.2 never-improvise category and
stops for the owner. `delete_bytes` is the service-level early delete, so Session B adds
an affordance rather than a mechanism.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import storage as storage_mod
from .enums import RetentionClass
from .models import Document

# E3 §E3.4.3: "a retention TTL class (30-day, driver-deletable)".
AUDIO_TTL = timedelta(days=30)


class RetentionClassRefused(ValueError):
    """Something asked to delete bytes that are not in a deletable class."""


def _now(now: datetime | None = None) -> datetime:
    return now or datetime.now(UTC)


def classify_audio_30d(document: Document, *, now: datetime | None = None) -> Document:
    """Mark a document's bytes as raw driver audio: sweepable 30 days from now.

    Called at write time by the caller that knows what the object IS. F6 cannot tell a
    driver's recording from a synthesized officer line by looking at the bytes, and
    guessing is exactly what the column exists to prevent.
    """
    document.retention_class = RetentionClass.audio_30d
    document.bytes_expire_at = _now(now) + AUDIO_TTL
    return document


def bytes_available(document: Document) -> bool:
    return document.bytes_deleted_at is None


def delete_bytes(
    db: Session, document: Document, *, now: datetime | None = None, storage=None
) -> bool:
    """Delete the object's bytes. Returns False if they were already gone.

    Refuses a `permanent` row. This is the early-delete path a driver's request will use
    in Session B and the path the sweep uses now — one code path, so the refusal cannot
    be true of one and not the other.
    """
    if document.retention_class is not RetentionClass.audio_30d:
        raise RetentionClassRefused(
            f"document {document.id} is {document.retention_class.value}; only "
            f"{RetentionClass.audio_30d.value} bytes may be deleted. This refuses rather "
            "than obeying because the caller may be wrong about what this object is."
        )
    if document.bytes_deleted_at is not None:
        return False

    store = storage or storage_mod.default_storage()
    try:
        store.delete(document.storage_key)
    except Exception as exc:  # noqa: BLE001
        # AI-CONTEXT: an object already absent is SUCCESS, not failure. A sweep that
        # raises on a missing object stops at the first one and every later row keeps its
        # bytes — the failure mode is silent retention, which is the thing this whole
        # file exists to prevent.
        if not storage_mod.is_missing_object(exc):
            raise
    document.bytes_deleted_at = _now(now)
    db.flush()
    return True


def due_for_sweep(db: Session, *, now: datetime | None = None, limit: int = 500) -> list[Document]:
    """Rows whose audio bytes are past their TTL and still present.

    The SELECT is the guard: `retention_class == audio_30d` is a column comparison, so no
    row of any other class can appear here however it was stored or named.
    """
    return list(
        db.scalars(
            select(Document)
            .where(
                Document.retention_class == RetentionClass.audio_30d,
                Document.bytes_deleted_at.is_(None),
                Document.bytes_expire_at.is_not(None),
                Document.bytes_expire_at <= _now(now),
            )
            .limit(limit)
        )
    )


def sweep(db: Session, *, now: datetime | None = None, storage=None, limit: int = 500) -> int:
    """Delete the bytes of every expired audio object. Returns how many were deleted."""
    deleted = 0
    for document in due_for_sweep(db, now=now, limit=limit):
        if delete_bytes(db, document, now=now, storage=storage):
            deleted += 1
    return deleted

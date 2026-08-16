"""AI-CONTEXT: the 30-day audio retention class and its sweep (E3 §E3.4.3, D14).

The test that matters most is `test_a_permanent_document_can_never_have_its_bytes_deleted`.
Everything else here checks that the sweep works; that one checks it cannot reach a
driver's CDL. The costs are not symmetrical — keeping an extra audio file a while longer
is a broken promise, and deleting a credential is a destroyed answer to a question
somebody may yet need to ask — so the refusal gets the sharper test.

`test_the_sweep_selects_on_the_column_not_on_the_content_type` is the second half of that:
a permanent document stored WITH an audio content type must stay invisible to the sweep,
because the sweep is forbidden from inferring.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f06_documents import public as documents
from app.foundation.f06_documents.domain import retention
from app.foundation.f06_documents.domain.enums import DocType, RetentionClass


class _Store:
    """A storage double that records what was asked of it."""

    def __init__(self, missing: bool = False):
        self.deleted: list[str] = []
        self._missing = missing

    def delete(self, key: str) -> None:
        self.deleted.append(key)
        if self._missing:
            # KeyError is how `is_missing_object` spells "the bytes are not there" for
            # the in-memory store; MinIO says it with an S3Error carrying NoSuchKey. The
            # first draft of this double raised FileNotFoundError, which `delete_bytes`
            # correctly re-raised as a store problem — the double was wrong, not the code.
            raise KeyError(key)


def _account(db, email="retention@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _doc(db, account, *, content_type="audio/webm", doc_type=DocType.other):
    return documents.store_document(
        db,
        account_id=account.id,
        doc_type=doc_type,
        content=b"0123456789" * 10,
        filename="turn.webm",
        content_type=content_type,
    )


# --- classification ------------------------------------------------------------------


def test_everything_defaults_to_permanent(db):
    """The safety property: a caller who forgets to classify is outside the sweep."""
    account = _account(db)
    doc = _doc(db, account)
    assert doc.retention_class is RetentionClass.permanent
    assert doc.bytes_expire_at is None


def test_classifying_audio_sets_a_thirty_day_window(db):
    account = _account(db)
    doc = _doc(db, account)
    now = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)

    retention.classify_audio_30d(doc, now=now)

    assert doc.retention_class is RetentionClass.audio_30d
    assert doc.bytes_expire_at == now + timedelta(days=30)
    assert retention.AUDIO_TTL == timedelta(days=30)


# --- the refusal, which is the point ------------------------------------------------


def test_a_permanent_document_can_never_have_its_bytes_deleted(db):
    """A CDL is not sweepable, and asking directly does not change that.

    This refuses rather than obeying because the caller may be wrong about what the object
    is — and the asymmetry is the argument: an extra audio file kept is a broken promise,
    a deleted credential is a destroyed answer.
    """
    account = _account(db)
    cdl = _doc(db, account, doc_type=DocType.cdl, content_type="image/jpeg")
    store = _Store()

    with pytest.raises(documents.RetentionClassRefused):
        retention.delete_bytes(db, cdl, storage=store)

    assert store.deleted == [], "the store must not even be asked"
    assert cdl.bytes_deleted_at is None


def test_the_sweep_selects_on_the_column_not_on_the_content_type(db):
    """A permanent document that happens to BE audio stays invisible to the sweep.

    The sweep is forbidden from inferring, and this is what that forbiddance looks like
    from the outside: same MIME type, same bytes, different column, different fate.
    """
    account = _account(db)
    permanent_audio = _doc(db, account, content_type="audio/webm")
    permanent_audio.bytes_expire_at = datetime(2020, 1, 1, tzinfo=UTC)  # long past
    db.flush()

    due = retention.due_for_sweep(db, now=datetime(2026, 8, 16, tzinfo=UTC))
    assert permanent_audio.id not in [d.id for d in due]


# --- the sweep ------------------------------------------------------------------------


def test_the_sweep_deletes_expired_audio_and_keeps_the_row(db):
    """Bytes go; the row, and the fact a recording existed, stay."""
    account = _account(db)
    doc = _doc(db, account)
    issued = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
    retention.classify_audio_30d(doc, now=issued)
    db.flush()
    store = _Store()

    after = issued + timedelta(days=31)
    deleted = retention.sweep(db, now=after, storage=store)

    assert deleted == 1
    assert store.deleted == [doc.storage_key]
    assert doc.bytes_deleted_at == after
    assert retention.bytes_available(doc) is False
    # the row survives: "a recording existed, until this date" stays answerable
    assert db.get(documents.Document, doc.id) is not None


def test_audio_inside_its_window_is_left_alone(db):
    account = _account(db)
    doc = _doc(db, account)
    issued = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
    retention.classify_audio_30d(doc, now=issued)
    db.flush()
    store = _Store()

    deleted = retention.sweep(db, now=issued + timedelta(days=29), storage=store)

    assert deleted == 0
    assert store.deleted == []
    assert retention.bytes_available(doc) is True


def test_the_sweep_is_idempotent(db):
    account = _account(db)
    doc = _doc(db, account)
    issued = datetime(2026, 8, 16, tzinfo=UTC)
    retention.classify_audio_30d(doc, now=issued)
    db.flush()
    store = _Store()
    after = issued + timedelta(days=31)

    assert retention.sweep(db, now=after, storage=store) == 1
    assert retention.sweep(db, now=after, storage=store) == 0
    assert store.deleted == [doc.storage_key], "a second sweep must not re-ask the store"


def test_an_already_missing_object_is_success_not_failure(db):
    """A sweep that raises on a missing object stops, and every later row keeps its bytes.

    The failure mode of getting this wrong is SILENT RETENTION, which is the exact thing
    the class exists to prevent — so an absent object counts as done.
    """
    account = _account(db)
    doc = _doc(db, account)
    issued = datetime(2026, 8, 16, tzinfo=UTC)
    retention.classify_audio_30d(doc, now=issued)
    db.flush()

    deleted = retention.sweep(
        db, now=issued + timedelta(days=31), storage=_Store(missing=True)
    )
    assert deleted == 1
    assert doc.bytes_deleted_at is not None


def test_one_bad_row_does_not_leave_the_rest_retained(db):
    """A sweep over many rows must not be stopped by the first missing object."""
    account = _account(db)
    issued = datetime(2026, 8, 16, tzinfo=UTC)
    docs = []
    for i in range(3):
        doc = _doc(db, account)
        doc.filename = f"turn-{i}.webm"
        retention.classify_audio_30d(doc, now=issued)
        docs.append(doc)
    db.flush()

    deleted = retention.sweep(
        db, now=issued + timedelta(days=31), storage=_Store(missing=True)
    )
    assert deleted == 3
    assert all(d.bytes_deleted_at is not None for d in docs)


def test_deletion_is_irreversible_and_separate_from_archiving(db):
    """`restore_document` must never resurrect bytes it cannot bring back.

    A restore that cleared this would leave a row claiming to have audio behind a URL that
    404s — worse than a row saying plainly the recording no longer exists.
    """
    account = _account(db)
    doc = _doc(db, account)
    issued = datetime(2026, 8, 16, tzinfo=UTC)
    retention.classify_audio_30d(doc, now=issued)
    db.flush()
    retention.sweep(db, now=issued + timedelta(days=31), storage=_Store())
    stamp = doc.bytes_deleted_at

    documents.archive_document(db, doc, reason=documents.ARCHIVE_REMOVED)
    documents.restore_document(db, doc)
    db.flush()
    db.refresh(doc)

    assert doc.bytes_deleted_at == stamp, "a restore must not claim the bytes are back"

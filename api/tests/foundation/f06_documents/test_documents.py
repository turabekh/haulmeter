import hashlib
from datetime import date, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f06_documents import public as documents


def _account(db, email="driver@example.com"):
    return identity.register_account(db, email, "pw-123456")


def test_store_and_read_document_roundtrip(db):
    account = _account(db)
    storage = documents.InMemoryObjectStorage()
    content = b"%PDF-1.4 rate confirmation bytes"
    doc = documents.store_document(
        db,
        account.id,
        documents.DocType.rate_con,
        content,
        filename="rate_con.pdf",
        content_type="application/pdf",
        storage=storage,
    )
    assert doc.byte_size == len(content)
    assert doc.content_hash == hashlib.sha256(content).hexdigest()
    assert doc.extraction_status == documents.ExtractionStatus.pending
    assert documents.get_document_bytes(db, doc, storage=storage) == content


def test_extraction_seam(db):
    account = _account(db)
    storage = documents.InMemoryObjectStorage()
    doc = documents.store_document(
        db, account.id, documents.DocType.settlement, b"settlement", storage=storage
    )
    documents.apply_extraction(db, doc, {"gross": 250000, "detention": 7500})
    assert doc.extraction_status == documents.ExtractionStatus.extracted
    assert doc.extraction["detention"] == 7500

    doc2 = documents.store_document(
        db, account.id, documents.DocType.other, b"junk", storage=storage
    )
    documents.mark_extraction_failed(db, doc2)
    assert doc2.extraction_status == documents.ExtractionStatus.failed


def test_documents_for_account_filter(db):
    account = _account(db)
    storage = documents.InMemoryObjectStorage()
    documents.store_document(db, account.id, documents.DocType.cdl, b"cdl", storage=storage)
    documents.store_document(db, account.id, documents.DocType.bol, b"bol", storage=storage)
    cdls = documents.documents_for_account(db, account.id, doc_type=documents.DocType.cdl)
    assert len(cdls) == 1
    assert cdls[0].doc_type == documents.DocType.cdl
    assert len(documents.documents_for_account(db, account.id)) == 2


def test_active_reminder_offset_windows(db):
    expiry = date(2026, 9, 1)
    assert documents.active_reminder_offset(expiry, expiry - timedelta(days=31)) is None
    assert documents.active_reminder_offset(expiry, expiry - timedelta(days=30)) == 30
    assert documents.active_reminder_offset(expiry, expiry - timedelta(days=20)) == 30
    assert documents.active_reminder_offset(expiry, expiry - timedelta(days=14)) == 14
    assert documents.active_reminder_offset(expiry, expiry - timedelta(days=10)) == 14
    assert documents.active_reminder_offset(expiry, expiry - timedelta(days=3)) == 3
    assert documents.active_reminder_offset(expiry, expiry) == 3
    assert documents.active_reminder_offset(expiry, expiry + timedelta(days=1)) is None


def test_due_reminders_and_idempotent_marking(db):
    account = _account(db)
    storage = documents.InMemoryObjectStorage()
    expiry = date(2026, 9, 1)
    doc = documents.store_document(
        db,
        account.id,
        documents.DocType.med_card,
        b"med card",
        expires_on=expiry,
        storage=storage,
    )

    as_of_30 = expiry - timedelta(days=20)
    due = documents.due_reminders(db, as_of_30, account_id=account.id)
    assert [(d.id, off) for d, off in due] == [(doc.id, 30)]

    documents.mark_reminder_sent(db, doc, 30)
    assert documents.due_reminders(db, as_of_30, account_id=account.id) == []

    as_of_14 = expiry - timedelta(days=14)
    due2 = documents.due_reminders(db, as_of_14, account_id=account.id)
    assert [off for _, off in due2] == [14]


def test_no_reminder_without_expiry_or_when_expired(db):
    account = _account(db)
    storage = documents.InMemoryObjectStorage()
    documents.store_document(
        db, account.id, documents.DocType.permit, b"permit-no-expiry", storage=storage
    )
    documents.store_document(
        db,
        account.id,
        documents.DocType.insurance,
        b"expired",
        expires_on=date(2026, 1, 1),
        storage=storage,
    )
    due = documents.due_reminders(db, date(2026, 7, 20), account_id=account.id)
    assert due == []

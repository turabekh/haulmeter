from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f12_offline import public as offline

T0 = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _account(db, email="driver@example.com"):
    return identity.register_account(db, email, "pw-123456")


def test_first_ingest_applies_and_records_times(db):
    account = _account(db)
    receipt = offline.ingest(
        db, account.id, "evt-1", "status_report", {"status": "full"},
        occurred_at=T0, client_skew_ms=300,
    )
    assert receipt.applied is True
    assert receipt.envelope.occurred_at == T0
    assert receipt.envelope.received_at is not None
    assert receipt.envelope.client_skew_ms == 300


def test_duplicate_key_is_not_reapplied(db):
    account = _account(db)
    calls = []

    def handler(envelope):
        calls.append(envelope.id)

    first = offline.ingest(
        db, account.id, "evt-1", "photo", {"key": "a"}, occurred_at=T0, handler=handler
    )
    second = offline.ingest(
        db, account.id, "evt-1", "photo", {"key": "a"}, occurred_at=T0, handler=handler
    )
    assert first.applied is True
    assert second.applied is False
    assert first.envelope.id == second.envelope.id
    assert len(calls) == 1  # handler ran exactly once despite two syncs


def test_different_keys_apply_independently(db):
    account = _account(db)
    r1 = offline.ingest(db, account.id, "evt-1", "photo", {}, occurred_at=T0)
    r2 = offline.ingest(
        db, account.id, "evt-2", "photo", {}, occurred_at=T0 + timedelta(minutes=1)
    )
    assert r1.applied and r2.applied
    assert r1.envelope.id != r2.envelope.id


def test_same_key_scoped_per_account(db):
    a = _account(db, "a@example.com")
    b = _account(db, "b@example.com")
    ra = offline.ingest(db, a.id, "shared-key", "photo", {}, occurred_at=T0)
    rb = offline.ingest(db, b.id, "shared-key", "photo", {}, occurred_at=T0)
    assert ra.applied and rb.applied
    assert ra.envelope.id != rb.envelope.id


def test_get_receipt_and_list(db):
    account = _account(db)
    offline.ingest(db, account.id, "evt-1", "geofence_ack", {}, occurred_at=T0)
    offline.ingest(
        db, account.id, "evt-2", "claim_action", {}, occurred_at=T0 + timedelta(minutes=1)
    )
    assert offline.get_receipt(db, account.id, "evt-1") is not None
    assert len(offline.list_for_account(db, account.id)) == 2
    assert len(offline.list_for_account(db, account.id, kind="geofence_ack")) == 1

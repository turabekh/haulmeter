from datetime import UTC, date, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f04_evidence import public as evidence
from app.foundation.f05_load import public as loads
from app.foundation.f06_documents import public as documents
from app.foundation.f08_notifications import public as notify
from app.foundation.f13_flags import public as flags
from app.modules.m05_protection import public as m5

DALLAS = (32.7767, -96.7970)
T0 = datetime(2026, 7, 20, 7, 0, tzinfo=UTC)


def _account(db, email="driver@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _stop(db, account, appt_start=T0, appt_end=None):
    fac = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Dock", *DALLAS)
    load = loads.create_load(db, account.id)
    return loads.add_stop(
        db,
        load,
        fac.id,
        loads.StopType.delivery,
        appointment_start=appt_start,
        appointment_end=appt_end,
    )


def test_register_module(db):
    m5.register_module(db)
    assert flags.is_enabled(db, "m05_protection") is False


def test_on_time_proof_within_window_and_notice(db):
    account = _account(db)
    stop = _stop(db, account, appt_start=T0, appt_end=T0 + timedelta(hours=1))
    gateway = notify.RecordingNotificationGateway()
    proof = m5.file_on_time_proof(
        db,
        stop,
        account.id,
        checked_in_at=T0 + timedelta(minutes=30),
        notify_counterparty=True,
        counterparty_email="ap@acme.com",
        gateway=gateway,
    )
    assert proof.within_window is True
    assert proof.notice_sent is True
    assert gateway.sent[0].channel == "email"


def test_on_time_proof_late_no_notice(db):
    account = _account(db)
    stop = _stop(db, account, appt_start=T0, appt_end=T0 + timedelta(hours=1))
    gateway = notify.RecordingNotificationGateway()
    proof = m5.file_on_time_proof(
        db,
        stop,
        account.id,
        checked_in_at=T0 + timedelta(hours=2),
        notify_counterparty=True,
        gateway=gateway,
    )
    assert proof.within_window is False
    assert proof.notice_sent is False
    assert gateway.sent == []


def test_cargo_condition_capture_is_hash_chained(db):
    account = _account(db)
    stop = _stop(db, account)
    assert m5.condition_sequence()[0] == "trailer_exterior"
    capture = m5.start_condition_capture(db, stop, account.id, m5.CapturePhase.pickup)
    m5.add_condition_photo(
        db, capture, prompt="trailer_exterior", content=b"photo-1", captured_at=T0
    )
    m5.add_condition_photo(db, capture, prompt="seals", content=b"photo-2", captured_at=T0)
    assert capture.photo_count == 2
    log = db.get(evidence.EvidenceLog, capture.evidence_log_ref)
    assert evidence.verify_chain(db, log).valid is True


def test_document_wallet_expiry_status(db):
    account = _account(db)
    storage = documents.InMemoryObjectStorage()
    documents.store_document(db, account.id, documents.DocType.cdl, b"cdl", storage=storage)
    documents.store_document(
        db,
        account.id,
        documents.DocType.med_card,
        b"mc",
        expires_on=date(2026, 8, 1),
        storage=storage,
    )
    documents.store_document(
        db,
        account.id,
        documents.DocType.insurance,
        b"ins",
        expires_on=date(2026, 1, 1),
        storage=storage,
    )
    result = m5.wallet(db, account.id, as_of=date(2026, 7, 20))
    statuses = {d["doc_type"]: d["status"] for d in result["documents"]}
    assert statuses["cdl"] == "ok"
    assert statuses["med_card"] == "expiring"  # 12 days out
    assert statuses["insurance"] == "expired"
    assert len(result["expiring"]) == 2


def test_inspection_mode_filters_credential_types(db):
    account = _account(db)
    storage = documents.InMemoryObjectStorage()
    documents.store_document(db, account.id, documents.DocType.cdl, b"cdl", storage=storage)
    documents.store_document(db, account.id, documents.DocType.rate_con, b"rc", storage=storage)
    types = {d["doc_type"] for d in m5.inspection_mode(db, account.id)}
    assert "cdl" in types
    assert "rate_con" not in types  # not an inspection credential


def test_incident_capture_produces_shareable_pack(db):
    account = _account(db)
    incident = m5.capture_incident(db, account.id, kind="cargo_damage", note="corner crushed")
    m5.add_incident_photo(db, incident, content=b"damage-photo", captured_at=T0)
    pack = m5.incident_pack(db, incident)
    assert pack.verification["chain_valid"] is True


def test_protection_summary_flags_missing(db):
    account = _account(db)
    stop = _stop(db, account)
    m5.file_on_time_proof(db, stop, account.id, checked_in_at=T0)
    summary = m5.protection_summary(db, stop)
    assert summary["documented"]["on_time_proof"] is True
    assert "pickup_photos" in summary["missing"]
    assert "delivery_photos" in summary["missing"]

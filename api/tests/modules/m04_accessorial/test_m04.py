from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f05_load import public as loads
from app.foundation.f07_ledger import public as ledger
from app.foundation.f09_ai_gateway import public as ai
from app.foundation.f13_flags import public as flags
from app.modules.m04_accessorial import public as m4

DALLAS = (32.7767, -96.7970)
FAR = (32.9000, -96.8000)
T0 = datetime(2026, 7, 20, 20, 0, tzinfo=UTC)  # evening (for overnight layover)


def _setup(db, email="oo@example.com"):
    account = identity.register_account(db, email, "pw-123456")
    identity.upsert_driver_profile(db, account, authority_type=identity.AuthorityType.own_mc)
    receiver = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Dock", *DALLAS)
    broker = loads.create_counterparty(
        db, "Acme", loads.CounterpartyKind.broker, contact_email="ap@acme.com"
    )
    load = loads.create_load(db, account.id, counterparty_id=broker.id, rate_cents=250000)
    stop = loads.add_stop(db, load, receiver.id, loads.StopType.delivery)
    return account, broker, load, stop


def test_register_module_seeds_flag_and_prompt(db):
    m4.register_module(db)
    assert flags.is_enabled(db, "m04_accessorial") is False
    assert ai.get_active_prompt(db, "lumper_ocr") is not None


def test_tonu_files_receivable(db):
    account, broker, load, stop = _setup(db)
    claim = m4.file_tonu(db, load, amount_cents=30000, stop=stop)
    assert claim.kind == m4.AccessorialKind.tonu
    receivable = db.get(ledger.Receivable, claim.receivable_ref)
    assert receivable.kind == ledger.ReceivableKind.tonu
    assert receivable.amount_cents == 30000


def test_layover_requires_overnight(db):
    account, broker, load, stop = _setup(db)
    location.arm_geofence(db, account.id, stop.facility_id)
    # same-day dwell -> not a layover
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0)
    location.evaluate_ping(db, account.id, *FAR, occurred_at=T0 + timedelta(hours=2))
    with pytest.raises(m4.NoLayover):
        m4.file_layover(db, stop, layover_rate_cents=15000)


def test_layover_overnight_files_receivable(db):
    account, broker, load, stop = _setup(db)
    location.arm_geofence(db, account.id, stop.facility_id)
    # arrive 20:00, leave next morning -> crosses midnight
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0)
    location.evaluate_ping(db, account.id, *FAR, occurred_at=T0 + timedelta(hours=12))
    claim = m4.file_layover(db, stop, layover_rate_cents=15000)
    assert claim.kind == m4.AccessorialKind.layover
    receivable = db.get(ledger.Receivable, claim.receivable_ref)
    assert receivable.amount_cents == 15000


def test_lumper_ocr_to_reimbursement(db):
    account, broker, load, stop = _setup(db)
    m4.register_module(db)  # registers the lumper_ocr prompt
    provider = ai.FakeModelProvider(structured_output={"amount_cents": 12500})
    claim = m4.file_lumper(db, load, provider, receipt_bytes=b"receipt-image")
    assert claim.kind == m4.AccessorialKind.lumper
    assert claim.document_ref is not None
    receivable = db.get(ledger.Receivable, claim.receivable_ref)
    assert receivable.kind == ledger.ReceivableKind.lumper
    assert receivable.amount_cents == 12500


def test_check_accessorial_terms_flags_silence(db):
    account, broker, load, stop = _setup(db)
    result = m4.check_accessorial_terms(load)
    assert result["silent"] is True
    assert "detention" in result["missing"]
    assert "tonu" in result["missing"]


def test_money_owed_unifies_m3_and_m4(db):
    account, broker, load, stop = _setup(db)
    m4.register_module(db)  # registers the lumper_ocr prompt
    m4.file_tonu(db, load, amount_cents=30000, stop=stop)
    m4.file_lumper(
        db, load, ai.FakeModelProvider(structured_output={"amount_cents": 5000}), receipt_bytes=b"r"
    )
    owed = m4.money_owed(db, account.id, now=datetime.now(UTC))
    kinds = {row["kind"] for row in owed}
    assert "tonu" in kinds and "lumper" in kinds
    lumper_row = next(r for r in owed if r["kind"] == "lumper")
    assert lumper_row["is_reimbursement"] is True
    assert all("aging_days" in r for r in owed)

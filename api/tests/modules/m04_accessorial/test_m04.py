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
from app.modules.m04_accessorial.domain import service as m4_service

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
    # AI-CONTEXT: the appointment is what anchors a layover to ONE visit (F-21). Without
    # it these fixtures placed the geofence events three weeks BEFORE the load was
    # created — a sequence the product cannot produce, since a load exists before it is
    # driven — and that unreality is part of why the unscoped resolver went unnoticed
    # for nine sessions. A layover claim comes off a rate confirmation, which carries an
    # appointment; the fixture now says so.
    stop = loads.add_stop(
        db, load, receiver.id, loads.StopType.delivery, appointment_start=T0
    )
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


# --- F-21: §23 entry 73's defect, which M3 was cured of and M4 kept ---
#
# The audit's own note on why nine green suites missed this: "a fixture with one visit
# cannot distinguish the two implementations." So these use TWO, and the second is the
# one being claimed for.
def test_a_second_load_to_the_same_dock_does_not_invent_a_layover(db):
    # THE defect, and it is worse than M3's was. M3's version produced a wrong AMOUNT on
    # a real claim; this one decides whether a claim EXISTS. Earliest-ENTER-ever plus
    # latest-EXIT-ever gives an arrival from three weeks ago and a departure from today,
    # the dates differ, NoLayover is not raised — and a layover invoice is filed for a
    # stop that was never overnight, then sent to a broker under the driver's name.
    account, broker, load, stop = _setup(db)

    # visit one, three weeks earlier: an overnight stay on a previous load
    old = T0 - timedelta(days=21)
    location.arm_geofence(db, account.id, stop.facility_id)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=old)
    location.evaluate_ping(db, account.id, *FAR, occurred_at=old + timedelta(hours=12))

    # visit two, this load: arrive 20:00, leave 22:00 — same calendar day, NOT a layover
    location.arm_geofence(db, account.id, stop.facility_id)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0)
    location.evaluate_ping(db, account.id, *FAR, occurred_at=T0 + timedelta(hours=2))

    with pytest.raises(m4.NoLayover):
        m4.file_layover(db, stop, layover_rate_cents=15000)


def test_the_claim_is_measured_from_this_visit_not_the_first_one(db):
    # the same shape, but where a layover IS owed: the answer must come from visit two
    account, broker, load, stop = _setup(db)

    old = T0 - timedelta(days=21)
    location.arm_geofence(db, account.id, stop.facility_id)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=old)
    location.evaluate_ping(db, account.id, *FAR, occurred_at=old + timedelta(hours=1))

    location.arm_geofence(db, account.id, stop.facility_id)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0)
    location.evaluate_ping(db, account.id, *FAR, occurred_at=T0 + timedelta(hours=12))

    claim = m4.file_layover(db, stop, layover_rate_cents=15000)
    assert claim.kind == m4.AccessorialKind.layover
    arrival, departure = m4_service._arrival_departure(
        db, account.id, stop.facility_id, m4_service._visit_anchor(load, stop)
    )
    assert arrival == T0, "the arrival must be THIS visit's, not the one three weeks ago"
    assert departure == T0 + timedelta(hours=12)

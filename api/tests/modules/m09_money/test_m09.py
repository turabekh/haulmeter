from datetime import UTC, date, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f07_ledger import public as ledger
from app.foundation.f09_ai_gateway import public as ai
from app.foundation.f13_flags import public as flags
from app.modules.m07_fuel import public as m7
from app.modules.m09_money import public as m9

PERIOD_START = date(2026, 7, 13)
PERIOD_END = date(2026, 7, 20)


def _driver(db, email="driver@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _owe(db, account_id, kind, amount, on=None):
    """A receivable dated INSIDE the settlement period unless told otherwise.

    AI-CONTEXT: these fixtures used to leave the receivable at "now" while the period was
    a fixed date weeks earlier, and nothing noticed because `audit_settlement` compared a
    period-scoped `paid` against an all-time `owed` (F-23). The two dates never had to
    correspond, so the test could not have caught the defect. Now the relationship is the
    thing under test, so it is stated.
    """
    receivable = ledger.create_receivable(db, account_id, kind, amount)
    at = on or PERIOD_START + timedelta(days=1)
    receivable.created_at = datetime(at.year, at.month, at.day, 12, 0, tzinfo=UTC)
    db.flush()
    return receivable


def test_flag_registers(db):
    m9.register_module(db)
    assert flags.can_activate(db, "m09_money") is True  # no external gates


def test_upload_and_audit_flags_missed_detention(db):
    driver = _driver(db)
    # the driver's own GPS-backed receivables say detention $150, lumper $125 owed
    _owe(db, driver.id, ledger.ReceivableKind.detention, 15000)
    _owe(db, driver.id, ledger.ReceivableKind.lumper, 12500)
    # the carrier settlement paid detention only $50, lumper in full
    settlement = m9.upload_settlement(
        db,
        driver.id,
        "Acme Carrier",
        PERIOD_START,
        PERIOD_END,
        lines=[
            {"kind": "linehaul", "amount_cents": 200000},
            {"kind": "detention", "amount_cents": 5000},
            {"kind": "lumper", "amount_cents": 12500},
        ],
    )
    discrepancies = m9.audit_settlement(db, settlement)
    assert len(discrepancies) == 1  # detention short; lumper paid in full
    d = discrepancies[0]
    assert d.kind == "detention"
    assert d.owed_cents == 15000
    assert d.paid_cents == 5000
    assert d.missed_cents == 10000
    assert d.evidence_ref is not None  # anchored to the GPS-backed receivable
    assert d.status == m9.DiscrepancyStatus.flagged


def test_parse_settlement_lines_via_f9_seam(db):
    driver = _driver(db)
    m9.register_module(db)  # registers the F9 prompt
    provider = ai.FakeModelProvider(
        structured_output={"lines": [{"kind": "detention", "amount_cents": 5000}]}
    )
    lines = m9.parse_settlement_lines(db, provider, doc_ref="settlement-doc", account_id=driver.id)
    assert lines == [{"kind": "detention", "amount_cents": 5000}]


def test_earnings_dashboard_is_ddd(db):
    driver = _driver(db)
    # recovered: a detention receivable moved to recovered
    rec = _owe(db, driver.id, ledger.ReceivableKind.detention, 15000)
    ledger.transition_receivable(db, rec, ledger.ReceivableState.recovered)
    # fuel saved: one settled network fuel purchase
    station = facility.create_facility(db, facility.FacilityType.fuel_station, "Pilot", 32.8, -96.8)
    merchant = m7.register_merchant(db, "FuelCo")
    m7.set_station_pricing(
        db,
        station.id,
        419,
        discount_cents_per_gal=25,
        spread_cents_per_gal=4,
        merchant_id=merchant.id,
    )
    m7.settle(db, m7.issue_pump_code(db, driver.id, station.id, gallons=100))  # saves 25c*100 = $25
    # flagged: an unpaid layover the auditor caught
    _owe(db, driver.id, ledger.ReceivableKind.layover, 20000)
    settlement = m9.upload_settlement(
        db,
        driver.id,
        "Acme",
        PERIOD_START,
        PERIOD_END,
        lines=[{"kind": "layover", "amount_cents": 0}],
    )
    m9.audit_settlement(db, settlement)

    summary = m9.earnings_dashboard(db, driver.id)
    assert summary.recovered_cents == 15000
    assert summary.fuel_saved_cents == 2500
    assert summary.flagged_cents == 20000
    assert summary.ddd_cents == 15000 + 2500 + 20000


def test_expense_capture_and_summary(db):
    driver = _driver(db)
    m9.add_receipt(db, driver.id, "fuel", 45000, date(2026, 3, 1), receipt_bytes=b"img")
    m9.add_receipt(db, driver.id, "meals", 3200, date(2026, 3, 2))
    m9.add_receipt(db, driver.id, "fuel", 41000, date(2026, 4, 1))
    m9.add_receipt(db, driver.id, "meals", 2800, date(2025, 12, 1))  # prior year, excluded

    summary = m9.expense_summary(db, driver.id, 2026)
    assert summary.by_category == {"fuel": 86000, "meals": 3200}
    assert summary.total_cents == 89200
    assert summary.receipt_count == 3


def test_ifta_and_per_diem_are_honest_seams(db):
    driver = _driver(db)
    ifta = m9.ifta_summary(
        db,
        driver.id,
        legs=[{"miles": 100, "jurisdiction": "TX"}, {"miles": 50, "jurisdiction": "OK"}],
    )
    assert ifta.total_miles == 150
    assert ifta.by_jurisdiction == {"TX": 100, "OK": 50}
    assert ifta.basis == "legs"

    empty = m9.ifta_summary(db, driver.id)
    assert empty.total_miles == 0
    assert empty.basis == "no_data"

    pd = m9.per_diem_days(db, driver.id, 2026)
    assert pd.nights_away is None
    assert pd.basis == "needs_account_traces"


# --- F-23: `paid` was scoped to one settlement, `owed` was every receivable ever ---
def test_a_receivable_from_another_period_is_not_a_discrepancy(db):
    """Consequence one: false discrepancies.

    A lumper receivable from a load this settlement does not cover was reported as
    "missed" — telling the driver their broker underpaid on money that broker had never
    been billed for. A wrong figure on the Money tab is §11.7's honesty failure pointed
    at the driver rather than the counterparty.
    """
    driver = _driver(db)
    _owe(db, driver.id, ledger.ReceivableKind.lumper, 12500, on=PERIOD_START - timedelta(days=30))
    settlement = m9.upload_settlement(
        db,
        driver.id,
        "Acme Carrier",
        PERIOD_START,
        PERIOD_END,
        lines=[{"kind": "linehaul", "amount_cents": 200000}],
    )
    assert m9.audit_settlement(db, settlement) == []


def test_an_unpaid_balance_is_not_re_flagged_on_every_later_settlement(db):
    """Consequence two: repeat flagging.

    A receivable stays owed until somebody taps *the broker paid this* — driver-initiated,
    and until a second actor exists the only path to `recovered`. So the same balance was
    flagged again on every subsequent settlement and `_flagged_total` summed the
    duplicates into the earnings dashboard, a number adjacent to the North Star.
    """
    driver = _driver(db)
    _owe(db, driver.id, ledger.ReceivableKind.detention, 15000)

    first = m9.upload_settlement(
        db, driver.id, "Acme", PERIOD_START, PERIOD_END, lines=[]
    )
    assert len(m9.audit_settlement(db, first)) == 1  # correctly flagged, once

    next_start = PERIOD_END + timedelta(days=1)
    second = m9.upload_settlement(
        db, driver.id, "Acme", next_start, next_start + timedelta(days=7), lines=[]
    )
    assert m9.audit_settlement(db, second) == [], "the same money must not be flagged twice"

    # and the dashboard total counts it once, not once per settlement
    assert m9.earnings_dashboard(db, driver.id).flagged_cents == 15000

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f07_ledger import public as ledger


def _account(db, email="oo@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _usd(db, kind, name):
    return ledger.create_account(db, kind, name, currency=ledger.Currency.usd)


def _points(db, kind, name):
    return ledger.create_account(db, kind, name, currency=ledger.Currency.points)


def test_balanced_entry_posts_and_balances(db):
    cash = _usd(db, ledger.LedgerAccountKind.cash_clearing, "cash")
    revenue = _usd(db, ledger.LedgerAccountKind.platform_revenue, "rev")
    ledger.post_entry(
        db,
        ledger.EntryType.booking_payment,
        [
            ledger.Posting(cash.id, ledger.Direction.debit, 2500),
            ledger.Posting(revenue.id, ledger.Direction.credit, 2500),
        ],
    )
    assert ledger.balance(db, cash) == 2500
    assert ledger.balance(db, revenue) == -2500


def test_unbalanced_entry_rejected(db):
    a = _usd(db, ledger.LedgerAccountKind.cash_clearing, "a")
    b = _usd(db, ledger.LedgerAccountKind.platform_revenue, "b")
    with pytest.raises(ledger.UnbalancedEntry):
        ledger.post_entry(
            db,
            ledger.EntryType.adjustment,
            [
                ledger.Posting(a.id, ledger.Direction.debit, 100),
                ledger.Posting(b.id, ledger.Direction.credit, 90),
            ],
        )


def test_single_posting_rejected(db):
    a = _usd(db, ledger.LedgerAccountKind.cash_clearing, "a")
    with pytest.raises(ledger.UnbalancedEntry):
        ledger.post_entry(
            db, ledger.EntryType.adjustment, [ledger.Posting(a.id, ledger.Direction.debit, 100)]
        )


def test_points_are_closed_loop(db):
    driver_pts = _points(db, ledger.LedgerAccountKind.points_balance, "driver points")
    pool = _points(db, ledger.LedgerAccountKind.points_pool, "points pool")
    ledger.post_entry(
        db,
        ledger.EntryType.points_earn,
        [
            ledger.Posting(driver_pts.id, ledger.Direction.debit, 500),
            ledger.Posting(pool.id, ledger.Direction.credit, 500),
        ],
        currency=ledger.Currency.points,
    )
    assert ledger.balance(db, driver_pts) == 500


def test_cannot_mix_currencies_in_one_entry(db):
    usd_cash = _usd(db, ledger.LedgerAccountKind.cash_clearing, "usd")
    driver_pts = _points(db, ledger.LedgerAccountKind.points_balance, "pts")
    with pytest.raises(ledger.CurrencyMismatch):
        ledger.post_entry(
            db,
            ledger.EntryType.adjustment,
            [
                ledger.Posting(usd_cash.id, ledger.Direction.debit, 100),
                ledger.Posting(driver_pts.id, ledger.Direction.credit, 100),
            ],
            currency=ledger.Currency.usd,
        )


def test_receivable_valid_transitions(db):
    account = _account(db)
    r = ledger.create_receivable(
        db, account.id, ledger.ReceivableKind.detention, 15000
    )
    assert r.state == ledger.ReceivableState.invoiced
    ledger.transition_receivable(db, r, ledger.ReceivableState.disputed)
    ledger.transition_receivable(db, r, ledger.ReceivableState.escalated)
    ledger.transition_receivable(db, r, ledger.ReceivableState.recovered)
    assert r.state == ledger.ReceivableState.recovered


def test_receivable_invalid_transition_rejected(db):
    account = _account(db)
    r = ledger.create_receivable(db, account.id, ledger.ReceivableKind.tonu, 30000)
    ledger.transition_receivable(db, r, ledger.ReceivableState.recovered)
    with pytest.raises(ledger.InvalidTransition):
        ledger.transition_receivable(db, r, ledger.ReceivableState.disputed)


def test_record_recovery_posts_split_and_recovers(db):
    account = _account(db)
    r = ledger.create_receivable(db, account.id, ledger.ReceivableKind.detention, 15000)
    cash = _usd(db, ledger.LedgerAccountKind.cash_clearing, "cash")
    driver_payable = _usd(db, ledger.LedgerAccountKind.driver_payable, "driver payable")
    contingency = _usd(db, ledger.LedgerAccountKind.contingency_revenue, "contingency")

    entry = ledger.record_recovery(
        db,
        r,
        recovered_amount_cents=15000,
        contingency_fee_cents=3000,
        cash_clearing_account=cash,
        driver_payable_account=driver_payable,
        contingency_revenue_account=contingency,
    )
    assert r.state == ledger.ReceivableState.recovered
    assert r.entry_id == entry.id
    assert ledger.balance(db, cash) == 15000
    assert ledger.balance(db, driver_payable) == -12000
    assert ledger.balance(db, contingency) == -3000


def test_record_recovery_zero_fee(db):
    account = _account(db)
    r = ledger.create_receivable(db, account.id, ledger.ReceivableKind.lumper, 8000)
    cash = _usd(db, ledger.LedgerAccountKind.cash_clearing, "cash")
    driver_payable = _usd(db, ledger.LedgerAccountKind.driver_payable, "driver payable")
    contingency = _usd(db, ledger.LedgerAccountKind.contingency_revenue, "contingency")
    ledger.record_recovery(
        db, r, 8000, 0, cash, driver_payable, contingency
    )
    assert ledger.balance(db, driver_payable) == -8000
    assert ledger.balance(db, contingency) == 0


def test_payment_gateway_is_a_seam(db):
    gateway = ledger.StubPaymentGateway()
    with pytest.raises(NotImplementedError):
        gateway.create_payment_intent(2500, "booking-123")

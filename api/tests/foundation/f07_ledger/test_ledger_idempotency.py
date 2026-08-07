"""F-05 — the ledger is not idempotent.

`external_ref` carried no constraint, so the same real-world event could be posted twice.
A duplicate entry still BALANCES: the double-entry invariant holds while a driver's
payable is doubled, which is why the reconciliation test you would naturally write cannot
see it. These tests assert the database refuses, not that the service remembers to check.
"""

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f07_ledger import public as ledger


def _accounts(db):
    account = identity.register_account(db, "ledger@example.com", "pw-123456")
    cash = ledger.get_or_create_account(
        db, ledger.LedgerAccountKind.cash_clearing, "cash:test", ledger.Currency.usd
    )
    payable = ledger.get_or_create_account(
        db,
        ledger.LedgerAccountKind.owner_payable,
        f"owner:{account.id}",
        ledger.Currency.usd,
        owner_ref=account.id,
    )
    return cash, payable


def _post(db, cash, payable, ref, entry_type=ledger.EntryType.booking_payment):
    return ledger.post_entry(
        db,
        entry_type,
        [
            ledger.Posting(cash.id, ledger.Direction.debit, 4800),
            ledger.Posting(payable.id, ledger.Direction.credit, 4800),
        ],
        external_ref=ref,
    )


def test_the_same_ref_cannot_be_posted_twice(db):
    cash, payable = _accounts(db)
    _post(db, cash, payable, "booking:abc")
    with pytest.raises(ledger.DuplicateEntry):
        _post(db, cash, payable, "booking:abc")


def test_the_duplicate_is_refused_by_the_database_not_by_a_service_check(db):
    # posting the row directly, with no service logic in the way at all: if the constraint
    # is missing this insert succeeds and the test fails, which is the whole point
    from sqlalchemy.exc import IntegrityError

    from app.foundation.f07_ledger.domain.models import JournalEntry

    db.add(
        JournalEntry(
            entry_type=ledger.EntryType.booking_payment,
            currency=ledger.Currency.usd,
            external_ref="booking:direct",
        )
    )
    db.flush()
    db.add(
        JournalEntry(
            entry_type=ledger.EntryType.booking_payment,
            currency=ledger.Currency.usd,
            external_ref="booking:direct",
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()


def test_a_refused_duplicate_leaves_the_transaction_usable(db):
    # the SAVEPOINT is what makes DuplicateEntry catchable. Without it the IntegrityError
    # poisons the session and every later statement in the request dies too.
    cash, payable = _accounts(db)
    _post(db, cash, payable, "booking:xyz")
    with pytest.raises(ledger.DuplicateEntry):
        _post(db, cash, payable, "booking:xyz")

    later = _post(db, cash, payable, "booking:later")
    assert later.id is not None
    assert ledger.balance(db, cash) == 9600  # exactly two entries, not three


def test_the_same_ref_under_a_different_entry_type_is_allowed(db):
    # the key is (entry_type, external_ref), following F2's uq_source_record_kind_ref
    cash, payable = _accounts(db)
    _post(db, cash, payable, "shared-ref", entry_type=ledger.EntryType.booking_payment)
    other = _post(db, cash, payable, "shared-ref", entry_type=ledger.EntryType.adjustment)
    assert other.id is not None


def test_entries_without_a_ref_never_collide(db):
    # the index is partial; most entries legitimately carry no ref and must stay free
    cash, payable = _accounts(db)
    for _ in range(3):
        _post(db, cash, payable, None)
    assert ledger.balance(db, cash) == 14400

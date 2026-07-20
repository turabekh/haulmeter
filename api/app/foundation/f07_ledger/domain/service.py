from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .enums import (
    Currency,
    Direction,
    EntryType,
    LedgerAccountKind,
    ReceivableKind,
    ReceivableState,
)
from .models import JournalEntry, LedgerAccount, LedgerPosting, Receivable


class UnbalancedEntry(Exception):
    pass


class CurrencyMismatch(Exception):
    pass


class InvalidTransition(Exception):
    pass


ALLOWED_TRANSITIONS: dict[ReceivableState, set[ReceivableState]] = {
    ReceivableState.invoiced: {
        ReceivableState.acknowledged,
        ReceivableState.disputed,
        ReceivableState.recovered,
        ReceivableState.written_off,
    },
    ReceivableState.acknowledged: {
        ReceivableState.disputed,
        ReceivableState.recovered,
        ReceivableState.written_off,
    },
    ReceivableState.disputed: {
        ReceivableState.escalated,
        ReceivableState.recovered,
        ReceivableState.written_off,
    },
    ReceivableState.escalated: {
        ReceivableState.recovered,
        ReceivableState.written_off,
    },
    ReceivableState.recovered: set(),
    ReceivableState.written_off: set(),
}


@dataclass
class Posting:
    account_id: object
    direction: Direction
    amount_cents: int


def create_account(
    db: Session,
    kind: LedgerAccountKind,
    name: str,
    currency: Currency = Currency.usd,
    owner_ref=None,
) -> LedgerAccount:
    account = LedgerAccount(kind=kind, name=name, currency=currency, owner_ref=owner_ref)
    db.add(account)
    db.flush()
    return account


def post_entry(
    db: Session,
    entry_type: EntryType,
    postings: list[Posting],
    currency: Currency = Currency.usd,
    description: str | None = None,
    external_ref: str | None = None,
) -> JournalEntry:
    if len(postings) < 2:
        raise UnbalancedEntry("an entry needs at least two postings")
    if any(p.amount_cents <= 0 for p in postings):
        raise UnbalancedEntry("posting amounts must be positive")

    account_ids = {p.account_id for p in postings}
    accounts = {
        a.id: a
        for a in db.scalars(select(LedgerAccount).where(LedgerAccount.id.in_(account_ids)))
    }
    for posting in postings:
        account = accounts.get(posting.account_id)
        if account is None:
            raise CurrencyMismatch(f"unknown ledger account {posting.account_id}")
        if account.currency != currency:
            raise CurrencyMismatch(
                f"account {account.id} is {account.currency.value}, entry is {currency.value}"
            )

    debits = sum(p.amount_cents for p in postings if p.direction == Direction.debit)
    credits = sum(p.amount_cents for p in postings if p.direction == Direction.credit)
    if debits != credits:
        raise UnbalancedEntry(f"debits {debits} != credits {credits}")

    entry = JournalEntry(
        entry_type=entry_type,
        currency=currency,
        description=description,
        external_ref=external_ref,
    )
    db.add(entry)
    db.flush()
    for posting in postings:
        db.add(
            LedgerPosting(
                entry_id=entry.id,
                ledger_account_id=posting.account_id,
                direction=posting.direction,
                amount_cents=posting.amount_cents,
            )
        )
    db.flush()
    return entry


def balance(db: Session, account: LedgerAccount) -> int:
    def _sum(direction: Direction) -> int:
        return db.scalar(
            select(func.coalesce(func.sum(LedgerPosting.amount_cents), 0)).where(
                LedgerPosting.ledger_account_id == account.id,
                LedgerPosting.direction == direction,
            )
        )

    return _sum(Direction.debit) - _sum(Direction.credit)


# --- Receivables ---
def create_receivable(
    db: Session,
    account_id,
    kind: ReceivableKind,
    amount_cents: int,
    counterparty_ref=None,
    external_ref: str | None = None,
) -> Receivable:
    receivable = Receivable(
        account_id=account_id,
        kind=kind,
        amount_cents=amount_cents,
        counterparty_ref=counterparty_ref,
        external_ref=external_ref,
        state=ReceivableState.invoiced,
    )
    db.add(receivable)
    db.flush()
    return receivable


def transition_receivable(
    db: Session, receivable: Receivable, new_state: ReceivableState
) -> Receivable:
    if new_state not in ALLOWED_TRANSITIONS[receivable.state]:
        raise InvalidTransition(f"{receivable.state.value} -> {new_state.value}")
    receivable.state = new_state
    db.flush()
    return receivable


def record_recovery(
    db: Session,
    receivable: Receivable,
    recovered_amount_cents: int,
    contingency_fee_cents: int,
    cash_clearing_account: LedgerAccount,
    driver_payable_account: LedgerAccount,
    contingency_revenue_account: LedgerAccount,
) -> JournalEntry:
    if contingency_fee_cents < 0 or contingency_fee_cents > recovered_amount_cents:
        raise UnbalancedEntry("contingency fee must be between 0 and the recovered amount")
    entry = post_entry(
        db,
        EntryType.claim_recovery,
        [
            Posting(cash_clearing_account.id, Direction.debit, recovered_amount_cents),
            Posting(
                driver_payable_account.id,
                Direction.credit,
                recovered_amount_cents - contingency_fee_cents,
            ),
            Posting(contingency_revenue_account.id, Direction.credit, contingency_fee_cents),
        ]
        if contingency_fee_cents > 0
        else [
            Posting(cash_clearing_account.id, Direction.debit, recovered_amount_cents),
            Posting(driver_payable_account.id, Direction.credit, recovered_amount_cents),
        ],
        currency=Currency.usd,
        description=f"recovery for receivable {receivable.id}",
    )
    receivable.entry_id = entry.id
    transition_receivable(db, receivable, ReceivableState.recovered)
    return entry

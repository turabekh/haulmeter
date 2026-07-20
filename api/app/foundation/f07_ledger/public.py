"""AI-CONTEXT: Public interface for F7 Ledger & Payments.

The ONLY import surface other packages may use to reach F7 (import-linter
enforced). One double-entry ledger for all value flows; every entry balances.
Points are a closed-loop currency (no cash-out). Consumed by M3, M4, M6, M7,
M10, M12.
"""
from .domain.enums import (
    Currency,
    Direction,
    EntryType,
    LedgerAccountKind,
    ReceivableKind,
    ReceivableState,
)
from .domain.gateway import PaymentGateway, StubPaymentGateway
from .domain.models import JournalEntry, LedgerAccount, LedgerPosting, Receivable
from .domain.service import (
    ALLOWED_TRANSITIONS,
    CurrencyMismatch,
    InvalidTransition,
    Posting,
    UnbalancedEntry,
    balance,
    create_account,
    create_receivable,
    post_entry,
    record_recovery,
    transition_receivable,
)

__all__ = [
    "Currency",
    "Direction",
    "EntryType",
    "LedgerAccountKind",
    "ReceivableKind",
    "ReceivableState",
    "PaymentGateway",
    "StubPaymentGateway",
    "JournalEntry",
    "LedgerAccount",
    "LedgerPosting",
    "Receivable",
    "ALLOWED_TRANSITIONS",
    "CurrencyMismatch",
    "InvalidTransition",
    "Posting",
    "UnbalancedEntry",
    "balance",
    "create_account",
    "create_receivable",
    "post_entry",
    "record_recovery",
    "transition_receivable",
]

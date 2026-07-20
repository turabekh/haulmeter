import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

from .enums import (
    Currency,
    Direction,
    EntryType,
    LedgerAccountKind,
    ReceivableKind,
    ReceivableState,
)

SCHEMA = "f07"
ACCOUNT_FK = "f01.account.id"

CURRENCY_ENUM = Enum(Currency, name="currency", schema=SCHEMA)


class LedgerAccount(Base):
    __tablename__ = "ledger_account"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[LedgerAccountKind] = mapped_column(
        Enum(LedgerAccountKind, name="ledger_account_kind", schema=SCHEMA)
    )
    name: Mapped[str] = mapped_column(String(200))
    currency: Mapped[Currency] = mapped_column(CURRENCY_ENUM, default=Currency.usd)
    owner_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JournalEntry(Base):
    __tablename__ = "journal_entry"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    entry_type: Mapped[EntryType] = mapped_column(Enum(EntryType, name="entry_type", schema=SCHEMA))
    currency: Mapped[Currency] = mapped_column(CURRENCY_ENUM)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    external_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    postings: Mapped[list["LedgerPosting"]] = relationship(
        back_populates="entry", cascade="all, delete-orphan"
    )


class LedgerPosting(Base):
    __tablename__ = "ledger_posting"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.journal_entry.id", ondelete="CASCADE"), index=True
    )
    ledger_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.ledger_account.id", ondelete="RESTRICT"), index=True
    )
    direction: Mapped[Direction] = mapped_column(Enum(Direction, name="direction", schema=SCHEMA))
    amount_cents: Mapped[int] = mapped_column(BigInteger)

    entry: Mapped[JournalEntry] = relationship(back_populates="postings")


class Receivable(Base):
    __tablename__ = "receivable"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    counterparty_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    kind: Mapped[ReceivableKind] = mapped_column(
        Enum(ReceivableKind, name="receivable_kind", schema=SCHEMA)
    )
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[Currency] = mapped_column(CURRENCY_ENUM, default=Currency.usd)
    state: Mapped[ReceivableState] = mapped_column(
        Enum(ReceivableState, name="receivable_state", schema=SCHEMA),
        default=ReceivableState.invoiced,
    )
    entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.journal_entry.id", ondelete="SET NULL"), nullable=True
    )
    external_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

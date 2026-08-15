import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

from .enums import DiscrepancyStatus

SCHEMA = "m09"
ACCOUNT_FK = "f01.account.id"


class Settlement(Base):
    """AI-CONTEXT: ONE settlement per driver, carrier and pay period (§23 entry 154).

    Measured before the fix: pressing "Run audit" three times on the same period produced
    three settlements, three sets of flagged discrepancies, and a `flagged_cents` of
    **15000 → 30000 → 45000** on the Money tab. A driver correcting a typo in what they
    were paid tripled the money the app told them they were owed.

    Audit F-23 fixed the neighbouring version of this — an all-time `owed` compared
    against a period-scoped `paid`, so the same balance was re-flagged on every LATER
    settlement. Re-running the SAME period was left, and it is the one a driver actually
    does, because the figures are typed by hand.

    The constraint is declared on the MODEL as well as in migration 0077 deliberately:
    the test database is built by `Base.metadata.create_all`, so a migration-only
    constraint is invisible to the entire suite (HANDOFF-125 §4.10).
    """

    __tablename__ = "settlement"
    __table_args__ = (
        UniqueConstraint(
            "driver_account_id",
            "carrier",
            "period_start",
            "period_end",
            name="uq_settlement_driver_carrier_period",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    driver_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    carrier: Mapped[str] = mapped_column(String(200))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    gross_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    doc_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True)  # F6 document
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lines: Mapped[list["SettlementLine"]] = relationship(
        back_populates="settlement", cascade="all, delete-orphan"
    )
    discrepancies: Mapped[list["Discrepancy"]] = relationship(
        back_populates="settlement", cascade="all, delete-orphan"
    )


class SettlementLine(Base):
    __tablename__ = "settlement_line"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    settlement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.settlement.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(40))  # linehaul / detention / layover / lumper / bonus
    amount_cents: Mapped[int] = mapped_column(BigInteger)

    settlement: Mapped[Settlement] = relationship(back_populates="lines")


class Discrepancy(Base):
    __tablename__ = "discrepancy"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    settlement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.settlement.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(40))
    owed_cents: Mapped[int] = mapped_column(BigInteger)
    paid_cents: Mapped[int] = mapped_column(BigInteger)
    missed_cents: Mapped[int] = mapped_column(BigInteger)
    evidence_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True)  # GPS-backed receivable
    status: Mapped[DiscrepancyStatus] = mapped_column(
        Enum(DiscrepancyStatus, name="discrepancy_status", schema=SCHEMA),
        default=DiscrepancyStatus.flagged,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    settlement: Mapped[Settlement] = relationship(back_populates="discrepancies")


class ExpenseReceipt(Base):
    __tablename__ = "expense_receipt"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    driver_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(40))  # fuel / meals / repair / toll / other
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    occurred_on: Mapped[date] = mapped_column(Date)
    doc_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True)  # F6 receipt photo
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

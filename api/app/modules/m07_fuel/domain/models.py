import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

from .enums import FuelTxnState, PriceSource

SCHEMA = "m07"
ACCOUNT_FK = "f01.account.id"


class Merchant(Base):
    __tablename__ = "merchant"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    settlement_terms: Mapped[str] = mapped_column(String(80), default="net_15")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StationPricing(Base):
    __tablename__ = "station_pricing"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # one pricing row per F2 fuel_station facility (soft ref, unique)
    facility_ref: Mapped[uuid.UUID] = mapped_column(unique=True, index=True)
    merchant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.merchant.id", ondelete="SET NULL"), nullable=True, index=True
    )
    gross_cents_per_gal: Mapped[int] = mapped_column(Integer)
    discount_cents_per_gal: Mapped[int] = mapped_column(Integer, default=0)  # driver-facing
    spread_cents_per_gal: Mapped[int] = mapped_column(Integer, default=0)  # platform margin
    source: Mapped[PriceSource] = mapped_column(
        Enum(PriceSource, name="price_source", schema=SCHEMA), default=PriceSource.feed
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FuelTransaction(Base):
    __tablename__ = "fuel_transaction"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    driver_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    station_ref: Mapped[uuid.UUID] = mapped_column(index=True)  # F2 fuel_station facility
    merchant_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    gallons_milli: Mapped[int] = mapped_column(
        Integer
    )  # thousandths of a gallon (integer discipline)
    gross_cents_per_gal: Mapped[int] = mapped_column(Integer)
    net_cents_per_gal: Mapped[int] = mapped_column(Integer)
    spread_cents_per_gal: Mapped[int] = mapped_column(Integer)
    gross_cents: Mapped[int] = mapped_column(BigInteger)
    net_cents: Mapped[int] = mapped_column(BigInteger)  # what the driver pays
    spread_cents: Mapped[int] = mapped_column(BigInteger)  # what the platform retains
    pump_code: Mapped[str] = mapped_column(String(16))
    state: Mapped[FuelTxnState] = mapped_column(
        Enum(FuelTxnState, name="fuel_txn_state", schema=SCHEMA), default=FuelTxnState.code_issued
    )
    entry_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

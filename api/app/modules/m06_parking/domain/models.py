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
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

from .enums import BookingState

SCHEMA = "m06"
ACCOUNT_FK = "f01.account.id"


class ParkingProperty(Base):
    __tablename__ = "parking_property"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    facility_ref: Mapped[uuid.UUID] = mapped_column(index=True)  # F2 facility (parking_property)
    vetted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    spots: Mapped[list["ParkingSpot"]] = relationship(
        back_populates="property", cascade="all, delete-orphan"
    )


class ParkingSpot(Base):
    __tablename__ = "parking_spot"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    property_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.parking_property.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(80))
    price_cents_per_night: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    property: Mapped[ParkingProperty] = relationship(back_populates="spots")


class Booking(Base):
    """AI-CONTEXT: the no-overlap rule lives in Postgres, not in service.book(). A Python
    pre-check reads rows that a concurrent transaction has not committed yet, so two
    requests for the same spot and window both pass it and both insert — and each posts
    its own balanced journal entry, crediting the owner twice for one night. An EXCLUDE
    constraint makes that impossible rather than unlikely, and unlike _overlaps it still
    holds with a second API replica. Canceled and refunded bookings are excluded: they
    free the window. Requires the btree_gist extension for the `spot_id WITH =` operand."""

    __tablename__ = "booking"
    __table_args__ = (
        ExcludeConstraint(
            ("spot_id", "="),
            (text("tstzrange(start_at, end_at)"), "&&"),
            name="ex_booking_no_overlap",
            using="gist",
            where=text("state IN ('booked', 'checked_in', 'checked_out')"),
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    spot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.parking_spot.id", ondelete="CASCADE"), index=True
    )
    driver_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    nights: Mapped[int] = mapped_column(Integer)
    price_cents: Mapped[int] = mapped_column(BigInteger)
    take_cents: Mapped[int] = mapped_column(BigInteger)
    owner_payout_cents: Mapped[int] = mapped_column(BigInteger)
    state: Mapped[BookingState] = mapped_column(
        Enum(BookingState, name="booking_state", schema=SCHEMA), default=BookingState.booked
    )
    entry_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    refund_entry_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checked_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

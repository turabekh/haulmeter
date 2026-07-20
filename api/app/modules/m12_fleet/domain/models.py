import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

from .enums import FleetRole, MembershipState

SCHEMA = "m12"
ACCOUNT_FK = "f01.account.id"


class FleetMembership(Base):
    """Fleet identity is an F1 Organization (type=fleet); M12 owns membership so
    it can carry EXPLICIT consent (M12-FR1) that F1's OrgMembership lacks."""

    __tablename__ = "fleet_membership"
    __table_args__ = (
        UniqueConstraint("fleet_org_id", "driver_account_id", name="uq_fleet_member"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    fleet_org_id: Mapped[uuid.UUID] = mapped_column(index=True)  # F1 organization (soft ref)
    driver_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    role: Mapped[FleetRole] = mapped_column(Enum(FleetRole, name="fleet_role", schema=SCHEMA))
    consent: Mapped[bool] = mapped_column(Boolean, default=False)  # explicit, at join
    state: Mapped[MembershipState] = mapped_column(
        Enum(MembershipState, name="membership_state", schema=SCHEMA),
        default=MembershipState.invited,
    )
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ParkingBenefit(Base):
    """M12-FR2 shared parking benefit: monthly allowance + booking policy."""

    __tablename__ = "parking_benefit"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    fleet_org_id: Mapped[uuid.UUID] = mapped_column(unique=True, index=True)
    monthly_allowance_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    policy: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BenefitUsage(Base):
    """Per-driver monthly spend against the fleet allowance (completes M6-FR8)."""

    __tablename__ = "benefit_usage"
    __table_args__ = (
        UniqueConstraint("fleet_org_id", "driver_account_id", "month", name="uq_benefit_usage"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    fleet_org_id: Mapped[uuid.UUID] = mapped_column(index=True)
    driver_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    month: Mapped[date] = mapped_column(Date)  # first of month
    spent_cents: Mapped[int] = mapped_column(BigInteger, default=0)


class DataSubscription(Base):
    """M12-FR5 data-product access — aggregate, anonymized benchmarks only."""

    __tablename__ = "data_subscription"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    subscriber_ref: Mapped[str] = mapped_column(String(200), unique=True)  # buyer identifier
    tier: Mapped[str] = mapped_column(String(40), default="standard")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

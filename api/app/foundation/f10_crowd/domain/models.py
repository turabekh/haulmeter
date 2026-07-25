import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

from .enums import SignalType

SCHEMA = "f10"
ACCOUNT_FK = "f01.account.id"
FACILITY_FK = "f02.facility.id"

SIGNAL_TYPE_ENUM = Enum(SignalType, name="signal_type", schema=SCHEMA)


class Submission(Base):
    __tablename__ = "submission"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # nullable: authoritative feed submissions (e.g. TPIMS) have no driver account
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True, nullable=True
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(FACILITY_FK, ondelete="CASCADE"), index=True
    )
    signal_type: Mapped[SignalType] = mapped_column(SIGNAL_TYPE_ENUM, index=True)
    # AI-CONTEXT: what the signal is ABOUT within the facility, when a facility-wide
    # reading isn't the unit of truth. Parking/fuel/weigh-station describe the whole
    # site and leave this EMPTY; a vendor-presence signal names the vendor, so two
    # cooks at one truck stop can't tally against each other. Empty string (never
    # NULL) so the belief uniqueness constraint keeps biting on facility-wide rows.
    subject_ref: Mapped[str] = mapped_column(String(64), default="", server_default="", index=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    presence_proven: Mapped[bool] = mapped_column(default=False)
    # an authoritative feed (TPIMS) outranks crowd at equal freshness (PRD §12)
    authoritative: Mapped[bool] = mapped_column(default=False)
    # 80 chars: a feed name is short ("tpims"), but a subject-scoped source carries
    # an id ("vendor:<uuid>" is 43) — provenance is never truncated to fit
    source: Mapped[str | None] = mapped_column(String(80), nullable=True)
    trust_weight: Mapped[float] = mapped_column(Float, default=1.0)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # true only for submissions that actually issued points; the award cooldown
    # anchors on the last AWARD, never on a merely-recorded (cooled-down) report
    awarded: Mapped[bool] = mapped_column(default=False)


class ContributorTrust(Base):
    __tablename__ = "contributor_trust"
    __table_args__ = {"schema": SCHEMA}

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), primary_key=True
    )
    score: Mapped[float] = mapped_column(Float, default=1.0)
    confirmed_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Belief(Base):
    __tablename__ = "belief"
    __table_args__ = (
        UniqueConstraint(
            "facility_id", "signal_type", "subject_ref", name="uq_belief_facility_signal"
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(FACILITY_FK, ondelete="CASCADE"), index=True
    )
    signal_type: Mapped[SignalType] = mapped_column(SIGNAL_TYPE_ENUM)
    # see Submission.subject_ref — empty for facility-wide beliefs
    subject_ref: Mapped[str] = mapped_column(String(64), default="", server_default="")
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    freshest_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

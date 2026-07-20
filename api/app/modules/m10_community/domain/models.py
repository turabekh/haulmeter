import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

from .enums import HandoffState

SCHEMA = "m10"
ACCOUNT_FK = "f01.account.id"


class ContributionLog(Base):
    """Every M10 points earn — the source for rate limits, streaks, reputation,
    and leaderboards (anti-gaming + M10-FR3)."""

    __tablename__ = "contribution_log"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(40))  # review / handoff / answer / price_confirm
    points: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Handoff(Base):
    """M10-FR2 spot handoff relay — free-lot only, geofence-proven both ends."""

    __tablename__ = "handoff"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    facility_ref: Mapped[uuid.UUID] = mapped_column(index=True)  # F2 public facility
    broadcaster_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    claimer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="SET NULL"), nullable=True
    )
    leaving_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[HandoffState] = mapped_column(
        Enum(HandoffState, name="handoff_state", schema=SCHEMA), default=HandoffState.open
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FacilityQuestion(Base):
    """M10-FR4 moderated facility Q&A, pinned to the M2 facility page."""

    __tablename__ = "facility_question"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    facility_ref: Mapped[uuid.UUID] = mapped_column(index=True)
    asker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(ACCOUNT_FK, ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    answers: Mapped[list["FacilityAnswer"]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )


class FacilityAnswer(Base):
    __tablename__ = "facility_answer"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.facility_question.id", ondelete="CASCADE"), index=True
    )
    answerer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(ACCOUNT_FK, ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text)
    presence_proven: Mapped[bool] = mapped_column(Boolean, default=False)  # answered on-site
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    question: Mapped[FacilityQuestion] = relationship(back_populates="answers")

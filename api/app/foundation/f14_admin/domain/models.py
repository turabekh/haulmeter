import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

from .enums import ModerationStatus

SCHEMA = "f14"
ACCOUNT_FK = "f01.account.id"


class AnalyticsEvent(Base):
    __tablename__ = "analytics_event"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_name: Mapped[str] = mapped_column(String(120), index=True)
    module: Mapped[str] = mapped_column(String(40), index=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="SET NULL"), nullable=True, index=True
    )
    properties: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdminAction(Base):
    __tablename__ = "admin_action"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    actor_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(80), index=True)
    target_kind: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # a stable id for the thing acted on, so the log can be filtered to one subject.
    # Some subjects are keyed by string (a flag key, a config key) rather than a
    # UUID, hence `target_key` alongside it — both nullable, at most one used.
    target_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    target_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    # AI-CONTEXT: what changed, not merely that something changed. An audit log
    # without before/after can tell you a flag was toggled but not what it was
    # toggled FROM — which is exactly the question asked after an incident.
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # AI-CONTEXT: clock_timestamp(), NOT now(). In PostgreSQL now() is the
    # TRANSACTION start time, so several entries written in one transaction share a
    # timestamp and "who touched this last" becomes non-deterministic — the one
    # question an audit log exists to answer. clock_timestamp() is the real moment
    # each row was written, which is also what an auditor means by "when".
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), index=True
    )


class ModerationItem(Base):
    __tablename__ = "moderation_item"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    content_kind: Mapped[str] = mapped_column(String(60), index=True)
    content_ref: Mapped[uuid.UUID] = mapped_column(index=True)
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="SET NULL"), nullable=True
    )
    status: Mapped[ModerationStatus] = mapped_column(
        Enum(ModerationStatus, name="moderation_status", schema=SCHEMA),
        default=ModerationStatus.pending,
        index=True,
    )
    moderator_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AdminView(Base):
    __tablename__ = "admin_view"
    __table_args__ = (
        UniqueConstraint("key", name="uq_admin_view_key"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(120))
    module: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(200))
    path: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JobRun(Base):
    """AI-CONTEXT: worker job telemetry (Admin Console 2.0 Overview).

    Jobs previously logged to stdout only, which means the operator's first
    question every morning — "did the feeds run, and is anything stuck?" — could
    only be answered by reading container logs. One row per ATTEMPT (not per
    success) so a failure streak is visible as history rather than inferred from a
    counter, and `next_run_at` makes the backoff legible instead of mysterious.

    Deliberately a table rather than an F13 config row: config holds settings an
    operator sets, and quietly reusing it as a telemetry sink is the kind of shortcut
    that never gets undone.
    """

    __tablename__ = "job_run"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_name: Mapped[str] = mapped_column(String(60), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # the streak AT THIS ATTEMPT, so history reads without recomputation
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

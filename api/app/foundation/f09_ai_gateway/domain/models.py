import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

from .enums import AiTask
from .provider import EMBED_DIM

SCHEMA = "f09"
ACCOUNT_FK = "f01.account.id"

AI_TASK_ENUM = Enum(AiTask, name="ai_task", schema=SCHEMA)


class Prompt(Base):
    __tablename__ = "prompt"
    __table_args__ = (
        UniqueConstraint("key", "version", name="uq_prompt_key_version"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    task: Mapped[AiTask] = mapped_column(AI_TASK_ENUM)
    template: Mapped[str] = mapped_column(Text)
    model_hint: Mapped[str | None] = mapped_column(String(120), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PromptFixture(Base):
    __tablename__ = "prompt_fixture"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    prompt_key: Mapped[str] = mapped_column(String(120), index=True)
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    expected: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModuleBudget(Base):
    """AI-CONTEXT: a MONTHLY spend ceiling per module. The word is in the column name on
    purpose (audit F-18).

    `budget_micros` summed every call ever made, so crossing the number blocked the
    module permanently until a human raised it — on a box with no monitoring, a silent
    outage that looks exactly like a broken feature. Nothing said which it was, and
    "budget" everywhere else in this codebase means a RECURRING allowance: F8's
    `p1_budget_used`, §13.1's two-per-day. A future session reading
    `set_module_budget(db, "m04", 5_000_000)` would reasonably assume it renews.

    So it renews, and the name says so. Micros are millionths of a US dollar — the two
    token constants in service.py are $3/MTok in and $15/MTok out — so 25_000_000 is
    $25 per module per calendar month, in UTC.
    """

    __tablename__ = "module_budget"
    __table_args__ = {"schema": SCHEMA}

    module: Mapped[str] = mapped_column(String(40), primary_key=True)
    monthly_budget_micros: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AiCall(Base):
    __tablename__ = "ai_call"
    # the budget read is "what has this module spent since the start of the month", so
    # the index carries the time as well as the module — a bare `module` index makes the
    # database scan every call that module has EVER made to answer a question about 30
    # days. Added before volume rather than after (F-18).
    __table_args__ = (
        Index("ix_ai_call_module_time", "module", "created_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # no `index=True`: the composite above leads with `module`, so a single-column index
    # would be a redundant copy of its prefix, paid for on every insert
    module: Mapped[str] = mapped_column(String(40))
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="SET NULL"), nullable=True
    )
    task: Mapped[AiTask] = mapped_column(AI_TASK_ENUM)
    prompt_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model: Mapped[str] = mapped_column(String(120))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_micros: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Embedding(Base):
    __tablename__ = "embedding"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_kind: Mapped[str] = mapped_column(String(40), index=True)
    owner_ref: Mapped[uuid.UUID] = mapped_column(index=True)
    model: Mapped[str] = mapped_column(String(120))
    vector: Mapped[list[float]] = mapped_column(Vector(EMBED_DIM))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

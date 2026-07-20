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
    __tablename__ = "module_budget"
    __table_args__ = {"schema": SCHEMA}

    module: Mapped[str] = mapped_column(String(40), primary_key=True)
    budget_micros: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AiCall(Base):
    __tablename__ = "ai_call"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    module: Mapped[str] = mapped_column(String(40), index=True)
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

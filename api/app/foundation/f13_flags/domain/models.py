import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

SCHEMA = "f13"


class FeatureFlag(Base):
    __tablename__ = "feature_flag"
    __table_args__ = {"schema": SCHEMA}

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # AI-CONTEXT: audit F-02 — `enabled` was doing TWO jobs, and that is the whole bug.
    #
    # It carried both "this capability ships on" (a fact about the CODE) and "an operator
    # switched this" (a fact about this BOX). `register_all` wrote it by assignment to
    # express the first, which meant `enable()` — the only function in F13 that consults
    # validation gates — was never on the path. Six gates across M3, M6 and M7 had
    # therefore never been read: measured on the running box, all six `false`, all three
    # flags `true`.
    #
    # They are separate columns now:
    #
    #   default_on  the CODE's declaration. Refreshes on every boot, exactly like
    #               `description` does, because it is a fact about the shipped software.
    #   enabled     the OPERATOR's decision, and NULL means they have not made one.
    #               `enable()` and `disable()` are the only writers, and `enable()` still
    #               refuses on an unsatisfied gate — so the gate now governs every
    #               deliberate activation instead of nothing.
    #
    # The effective state is `enabled` when an operator has decided and `default_on`
    # otherwise; `service._effective` is the one place that resolves it, which is what
    # closes F-12 (two predicates that used to compute it separately).
    default_on: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)
    kill_switch: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    gates: Mapped[list["ValidationGate"]] = relationship(
        back_populates="flag", cascade="all, delete-orphan"
    )


class ValidationGate(Base):
    __tablename__ = "validation_gate"
    __table_args__ = (
        UniqueConstraint("flag_key", "name", name="uq_validation_gate_flag_name"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    flag_key: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.feature_flag.key", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    satisfied: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    satisfied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    flag: Mapped[FeatureFlag] = relationship(back_populates="gates")


class ConfigDeclaration(Base):
    """AI-CONTEXT: what is configurable, as opposed to what has been configured.

    `ConfigEntry` holds rows that EXIST, and `/admin/config` lists exactly those — so a
    key nobody had set yet appeared nowhere, and its own endpoint promised an operator
    "never has to guess a scope name to discover what is configurable" while guessing
    the KEY remained the only way in.

    Declaring is deliberately NOT setting. Seeding the default into a ConfigEntry would
    pin it at the moment the box first booted, and every later change to the code
    default would silently fail to apply anywhere that had ever run.
    """

    __tablename__ = "config_declaration"
    __table_args__ = {"schema": SCHEMA}

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    scope: Mapped[str] = mapped_column(String(60), index=True, default="global")
    default_value: Mapped[dict] = mapped_column(JSON, default=dict)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    declared_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ConfigEntry(Base):
    __tablename__ = "config_entry"
    __table_args__ = {"schema": SCHEMA}

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    scope: Mapped[str] = mapped_column(String(60), index=True, default="global")
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

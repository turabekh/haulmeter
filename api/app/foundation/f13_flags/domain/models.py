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
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
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

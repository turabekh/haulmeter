import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SCHEMA = "f15"


class MessageCatalog(Base):
    __tablename__ = "message_catalog"
    __table_args__ = (
        UniqueConstraint("key", "locale", name="uq_message_catalog_key_locale"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(160), index=True)
    locale: Mapped[str] = mapped_column(String(12), index=True)
    text: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GlossaryTerm(Base):
    __tablename__ = "glossary_term"
    __table_args__ = {"schema": SCHEMA}

    term: Mapped[str] = mapped_column(String(80), primary_key=True)
    keep_english: Mapped[bool] = mapped_column(Boolean, default=True)
    definition: Mapped[str | None] = mapped_column(String(400), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

import uuid
from datetime import datetime, time

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

from .enums import (
    MessageDirection,
    NotificationChannel,
    NotificationStatus,
    NotificationTier,
    SuppressReason,
    TemplateAudience,
)

SCHEMA = "f08"
ACCOUNT_FK = "f01.account.id"


class NotificationPrefs(Base):
    __tablename__ = "notification_prefs"
    __table_args__ = {"schema": SCHEMA}

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), primary_key=True
    )
    timezone: Mapped[str] = mapped_column(String(60), default="UTC")
    quiet_start: Mapped[time] = mapped_column(Time, default=time(22, 0))
    quiet_end: Mapped[time] = mapped_column(Time, default=time(6, 0))


class NotificationClassPref(Base):
    """AI-CONTEXT: per-account opt-in for an OPT-IN notification class (design-prd
    §23 E-D1). Absence of a row means NOT opted in — the class defaults OFF and a
    driver's silence is never read as consent. `muted_subjects` holds the one-tap
    per-subject mutes (e.g. a specific vendor) that the class's anti-spam laws
    require. The class definitions themselves live in code (service.py), like the
    tier table; only the per-driver choice is data."""

    __tablename__ = "notification_class_pref"
    __table_args__ = (
        UniqueConstraint("account_id", "class_key", name="uq_class_pref_account_class"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    class_key: Mapped[str] = mapped_column(String(60), index=True)
    opted_in: Mapped[bool] = mapped_column(Boolean, default=False)
    muted_subjects: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Notification(Base):
    __tablename__ = "notification"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    tier: Mapped[NotificationTier] = mapped_column(
        Enum(NotificationTier, name="notification_tier", schema=SCHEMA)
    )
    category: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String(500))
    deep_link: Mapped[str] = mapped_column(String(300))
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, name="notification_status", schema=SCHEMA),
        default=NotificationStatus.pending,
    )
    channel: Mapped[NotificationChannel | None] = mapped_column(
        Enum(NotificationChannel, name="notification_channel", schema=SCHEMA), nullable=True
    )
    suppress_reason: Mapped[SuppressReason | None] = mapped_column(
        Enum(SuppressReason, name="suppress_reason", schema=SCHEMA), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    dispatched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class NotificationTemplate(Base):
    __tablename__ = "notification_template"
    __table_args__ = (
        UniqueConstraint("key", "locale", "version", name="uq_template_key_locale_version"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(120), index=True)
    locale: Mapped[str] = mapped_column(String(12), default="en")
    version: Mapped[int] = mapped_column(Integer, default=1)
    audience: Mapped[TemplateAudience] = mapped_column(
        Enum(TemplateAudience, name="template_audience", schema=SCHEMA)
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="notification_channel", schema=SCHEMA)
    )
    subject_template: Mapped[str | None] = mapped_column(String(300), nullable=True)
    body_template: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutboundThread(Base):
    __tablename__ = "outbound_thread"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    counterparty_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    subject: Mapped[str] = mapped_column(String(300))
    template_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reply_to: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    messages: Mapped[list["OutboundMessage"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan", order_by="OutboundMessage.created_at"
    )


class OutboundMessage(Base):
    __tablename__ = "outbound_message"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.outbound_thread.id", ondelete="CASCADE"), index=True
    )
    direction: Mapped[MessageDirection] = mapped_column(
        Enum(MessageDirection, name="message_direction", schema=SCHEMA)
    )
    body: Mapped[str] = mapped_column(Text)
    provider_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    thread: Mapped[OutboundThread] = relationship(back_populates="messages")

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
    # the positive half of the same idea: subjects this account asked to hear ABOUT.
    # `muted_subjects` suppresses at dispatch; this one is read by callers choosing an
    # audience, which is why F8 also exposes the reverse lookup.
    followed_subjects: Mapped[list] = mapped_column(JSON, default=list)
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
    # AI-CONTEXT: delivery and attention are different events. `status` records what
    # the SYSTEM did (sent / suppressed / digested); this records that the DRIVER
    # opened it. A notification pushed at 3 a.m. and never read is `sent` either way,
    # so a single column would make "unread" quietly mean "undelivered".
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PushSubscription(Base):
    """AI-CONTEXT: a browser's Web Push endpoint, the thing that makes §13 reach a
    phone in a pocket (§23 entry 111).

    ONE ROW PER BROWSER, not per driver: a driver with a phone and a cab tablet has
    two, and both should buzz. `endpoint` is the push service's own URL for that
    browser instance and is therefore the natural key — it is unique across the world,
    and a re-subscribe from the same browser must UPDATE rather than accumulate, or a
    driver who clears their site data collects duplicate pushes forever.

    `p256dh` and `auth` are the subscription's public key material. They are not
    secrets of ours — they are how the payload is encrypted TO that browser (RFC 8291),
    so the push service relays ciphertext it cannot read.

    A subscription DIES on the far side without telling us: the browser is uninstalled,
    the user revokes permission, the push service expires it. That shows up as 404/410
    at send time, which is the only honest moment to learn it, so the gateway prunes
    on that response rather than pretending a stored row proves reachability.
    """

    __tablename__ = "push_subscription"
    __table_args__ = (
        UniqueConstraint("endpoint", name="uq_push_subscription_endpoint"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    endpoint: Mapped[str] = mapped_column(String(500))
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
    # AI-CONTEXT: who this was addressed to. The recipient was passed to the gateway and
    # then forgotten — neither the thread nor the message recorded it — so the database
    # could say a notice was sent and not say to whom. A retry needs the address, and so
    # does anyone reconstructing what a broker was actually told.
    to_ref: Mapped[str | None] = mapped_column(String(320), nullable=True)
    provider_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # AI-CONTEXT: `sent_at` means IT WENT OUT, and until now it did not (audit F-06).
    #
    # It was set unconditionally beside a `smtp-failed-…` ref, so the row asserted a
    # delivery it never got — the same shape as U-07's queue reporting "synced" over a
    # dropped write, and as F-01's F8 row claiming a notice was sent. NULL now means the
    # send has not succeeded, which is what makes the unsent ones findable at all.
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # bounded, so a permanently undeliverable address cannot be retried forever
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    thread: Mapped[OutboundThread] = relationship(back_populates="messages")

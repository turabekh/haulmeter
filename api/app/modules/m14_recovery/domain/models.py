import uuid
from datetime import datetime

from sqlalchemy import (
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

from .enums import ConnectorStatus, Provider

SCHEMA = "m14"
ACCOUNT_FK = "f01.account.id"


class Connector(Base):
    """A fleet's read-only link to its own telematics provider (M14-FR2).

    AI-CONTEXT: THE KEY IS ENCRYPTED AT REST, and that is an owner decision rather than
    a default (2026-08-15). The kickoff put the pasted key in a column and said a better
    home is a handoff note, not an improvisation — so it was asked.

    The reasoning that settled it: this repo is public, and more to the point the
    database is dumped nightly to an offsite bucket (`scripts/backup_db.sh`, A12). A
    plaintext column means every backup carries a working key to somebody else's fleet
    telematics. Ciphertext means a leaked dump yields nothing without `M14_CONNECTOR_KEY`,
    which lives only in `infra/.env` — `0600 root:root` on the VM, excluded by
    `deploy.sh`, and never in `.env.example` with a real value.

    `key_last4` exists so the portal can show *which* key is installed without the
    ciphertext ever leaving the server. It is four characters of a provider-issued token
    and is deliberately the only part that renders.
    """

    __tablename__ = "connector"
    __table_args__ = (
        # one connector per fleet per provider: a second row for the same pair is a
        # re-paste, which must replace rather than accumulate (the 0077 lesson, one
        # session old — a document that exists once should be unique in Postgres)
        UniqueConstraint("fleet_id", "provider", name="uq_connector_fleet_provider"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    fleet_id: Mapped[uuid.UUID] = mapped_column(index=True)
    provider: Mapped[Provider] = mapped_column(
        Enum(Provider, name="connector_provider", schema=SCHEMA)
    )
    # AES-GCM ciphertext of the pasted key. Never rendered, never logged, never returned
    # by any route — `key_last4` is what a screen is allowed to see.
    key_ciphertext: Mapped[str] = mapped_column(Text)
    key_last4: Mapped[str] = mapped_column(String(4))
    status: Mapped[ConnectorStatus] = mapped_column(
        Enum(ConnectorStatus, name="connector_status", schema=SCHEMA),
        default=ConnectorStatus.active,
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # the provider's own words when it refused us, so a revoked key is legible without a
    # log dive. Cleared on the next success — a stale error beside a healthy connector is
    # the "never ran / switched off / failing" collapse this module is careful about.
    health_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VehicleMap(Base):
    """provider vehicle → driver account. The whole trick of the slice lives here.

    AI-CONTEXT: `evaluate_ping` is ACCOUNT-centric — it locks a cursor for one account
    and walks that account's active armings. So an ELD breadcrumb becomes a first-class
    F3 ping the moment it can name an account, and the geofence engine, the dwell ticks
    and M3's arming consume it with no knowledge that a phone was not involved.

    An unmapped vehicle is SKIPPED AND COUNTED, never guessed. Guessing here would
    attribute one driver's dwell to another driver's claim, which is the worst available
    failure in a module whose output is an invoice.
    """

    __tablename__ = "vehicle_map"
    __table_args__ = (
        UniqueConstraint(
            "connector_id", "provider_vehicle_ref", name="uq_vehicle_map_connector_vehicle"
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    connector_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.connector.id", ondelete="CASCADE"), index=True
    )
    provider_vehicle_ref: Mapped[str] = mapped_column(String(120))
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TraceImport(Base):
    """The per-vehicle watermark that makes ingest idempotent.

    AI-CONTEXT: polling means the same breadcrumb arrives repeatedly — an overlapping
    window is the normal case, not an edge one. Without a watermark every poll would
    replay the last window into `evaluate_ping`, and a replayed ping is not inert: it
    advances dwell state and can re-fire an edge. The watermark is per (connector,
    vehicle) because vehicles are polled independently and one lagging truck must not
    hold back the others' progress.

    `last_seen_at` is the PROVIDER's timestamp, not ours. Comparing our clock against
    their breadcrumbs would drop records whenever the two disagree, which is exactly the
    disagreement F12 records deliberately elsewhere in this codebase.
    """

    __tablename__ = "trace_import"
    __table_args__ = (
        UniqueConstraint("connector_id", "provider_vehicle_ref", name="uq_trace_import_vehicle"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    connector_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.connector.id", ondelete="CASCADE"), index=True
    )
    provider_vehicle_ref: Mapped[str] = mapped_column(String(120))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pings_imported: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

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

from .enums import ConnectorStatus, HoldState, Provider

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


class HeldClaim(Base):
    """An ELD-derived claim waiting for a human (M14-FR4, E2 slice 1).

    AI-CONTEXT: M14 DOES NOT FORK M3 AND DOES NOT EXTEND ITS STATE MACHINE. The claim
    itself is an ordinary `m03.DetentionClaim` in its ordinary `open` state, reached
    through `m03.public.start_claim` — same states, same templates, same ledger. This row
    is M14's own record of a decision M3 has no concept of: *nobody has approved this
    yet*. Adding a `held` state to `ClaimState` would have made every M3 reader handle a
    case that is not M3's business.

    WHY `approved` AND `sent` ARE SEPARATE. A fleet admin approving while D13 is
    unanswered has genuinely approved, and the claim has genuinely not gone anywhere.
    Collapsing the two is precisely F-01: F8 recorded `sent_at` for notices that reached a
    container, and everything downstream believed them. `send_blocked_by` names the gate.

    ONE HOLD PER CLAIM, in Postgres. A second poll that re-drafts the same stop must find
    this row rather than queue the claim twice — a fleet admin seeing one detention twice
    would approve it twice, and `generate_pack` is the only thing standing between that
    and two invoices to one broker.
    """

    __tablename__ = "held_claim"
    __table_args__ = (
        UniqueConstraint("claim_ref", name="uq_held_claim_claim"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    fleet_id: Mapped[uuid.UUID] = mapped_column(index=True)
    # the m03 claim this is holding. NOT a ForeignKey: m14 sits above m03 in the spine and
    # a database-level dependency pointing down would outlive any import-linter contract.
    claim_ref: Mapped[uuid.UUID] = mapped_column(index=True)
    stop_ref: Mapped[uuid.UUID] = mapped_column(index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    # DERIVED from the ping sources backing the claim window, never asserted by a caller
    evidence_class: Mapped[str] = mapped_column(String(20), default="eld_derived")
    state: Mapped[HoldState] = mapped_column(
        Enum(HoldState, name="hold_state", schema=SCHEMA), default=HoldState.held
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # which gate refused the send, so the screen can say WHY rather than "not sent"
    send_blocked_by: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

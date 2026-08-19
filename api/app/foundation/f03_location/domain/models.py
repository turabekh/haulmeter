import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

from .enums import GeofenceEventType, LocationMode

SCHEMA = "f03"
ACCOUNT_FK = "f01.account.id"
FACILITY_FK = "f02.facility.id"


class LocationPing(Base):
    __tablename__ = "location_ping"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True)
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    client_skew_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gps_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    gps_time_divergent: Mapped[bool] = mapped_column(Boolean, default=False)
    accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_mps: Mapped[float | None] = mapped_column(Float, nullable=True)
    mode: Mapped[LocationMode] = mapped_column(
        Enum(LocationMode, name="location_mode", schema=SCHEMA),
        default=LocationMode.significant_change,
    )
    # AI-CONTEXT: WHAT PRODUCED THIS READING (M14-FR2/FR3, migration 0078).
    #
    # Free text, not an enum, and that is deliberate: the value is `device` or
    # `eld:<provider>`, and a new provider must not require a migration to be ingestible.
    # An enum here would make adding Samsara a schema change to a FOUNDATION table.
    #
    # It exists because the evidence pack has to declare its basis. The pack currently
    # says "Location data as reported by the driver's device" — true for every ping
    # before this column and false for every ELD one — and the class it prints is derived
    # from these values rather than asserted by a caller (`m14.evidence_class_for`).
    # Backfilled to `device`, which is what every existing row actually is.
    source: Mapped[str] = mapped_column(String(40), default="device", server_default="device")


class GeofenceArming(Base):
    __tablename__ = "geofence_arming"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(FACILITY_FK, ondelete="CASCADE"), index=True
    )
    radius_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    armed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    disarmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FacilityGeofence(Base):
    __tablename__ = "facility_geofence"
    __table_args__ = {"schema": SCHEMA}

    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(FACILITY_FK, ondelete="CASCADE"), primary_key=True
    )
    radius_m: Mapped[float] = mapped_column(Float)
    confirmed_arrivals: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GeofencePresence(Base):
    """AI-CONTEXT: ONE active presence per (account, facility), enforced in Postgres.

    The ENTER branch is check-then-act — it reads `_active_presence` and inserts if it
    finds none — over rows a concurrent transaction has not committed yet. Two first-pings
    arriving together (two devices, or two parallel offline flushes) therefore both missed
    and both inserted. EXIT closes one; the other keeps its old `entered_at` forever, and
    `visit_window` can hand that stale arrival to a LATER load as the moment its detention
    clock starts. Migration 0068.

    `evaluation_cursor`'s row lock is what normally prevents this; the index is the backstop
    for the one case a lock cannot cover — a cursor row that does not exist yet on two
    connections at once.
    """

    __tablename__ = "geofence_presence"
    __table_args__ = (
        Index(
            "uq_geofence_presence_active",
            "account_id",
            "facility_id",
            unique=True,
            postgresql_where=text("active"),
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(FACILITY_FK, ondelete="CASCADE"), index=True
    )
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_tick_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    exited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # AI-CONTEXT: consecutive pings observed OUTSIDE the fence (F3-4). The exit debounce
    # counts them and fires EXIT only at `f03.exit_confirm_pings`; an inside ping resets it.
    # The config ships at 1, which is exactly today's single-ping exit, so this column
    # changes nothing until an operator decides otherwise.
    outside_streak: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # AI-CONTEXT: set when the DRIVER said "I am here" (§23 entry 227). NULL means the
    # geofence opened this visit and the geofence may close it; a timestamp means a person
    # made a statement, and a fix that contradicts it implausibly does not get to win.
    attested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GeofenceEvent(Base):
    __tablename__ = "geofence_event"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(FACILITY_FK, ondelete="CASCADE"), index=True
    )
    event_type: Mapped[GeofenceEventType] = mapped_column(
        Enum(GeofenceEventType, name="geofence_event_type", schema=SCHEMA)
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True)
    )


class EvaluationCursor(Base):
    """AI-CONTEXT: the high-water mark of evaluated time, per account (F3-3).

    Two jobs in one row, and both matter.

    SERIALISATION. `evaluate_ping` takes this row `FOR UPDATE` before it touches the state
    machine, so an account's pings are evaluated one at a time however many connections are
    flushing them. That is the mechanism that kills the duplicate-presence race at its
    source rather than catching it afterwards.

    ORDERING. The offline outbox exists precisely to deliver pings LATE, and the machine
    applied every ping to current state at the ping's own timestamp — so a late inside-ping
    arriving after its visit's EXIT re-opened a presence that never closes, and a late
    outside-ping after an ENTER closed the visit at a moment before it began. A ping at or
    before `last_evaluated_at` is now recorded to the trail and not evaluated.

    A ping from the FUTURE deliberately does not advance this. A device with a broken clock
    would otherwise set the mark years ahead and silently discard every real ping after it.
    """

    __tablename__ = "evaluation_cursor"
    __table_args__ = {"schema": SCHEMA}

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), primary_key=True
    )
    last_evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

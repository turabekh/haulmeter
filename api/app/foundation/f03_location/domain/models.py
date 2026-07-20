import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    func,
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
    __tablename__ = "geofence_presence"
    __table_args__ = {"schema": SCHEMA}

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

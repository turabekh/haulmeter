import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

from .enums import FacilityStatus, FacilityType, SourceKind

SCHEMA = "f02"


class Facility(Base):
    __tablename__ = "facility"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    facility_type: Mapped[FacilityType] = mapped_column(
        Enum(FacilityType, name="facility_type", schema=SCHEMA)
    )
    status: Mapped[FacilityStatus] = mapped_column(
        Enum(FacilityStatus, name="facility_status", schema=SCHEMA),
        default=FacilityStatus.confirmed,
    )
    name: Mapped[str] = mapped_column(String(300))
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True)
    )
    lot_polygon: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=True), nullable=True
    )
    geohash: Mapped[str | None] = mapped_column(String(12), index=True, nullable=True)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    hours: Mapped[dict] = mapped_column(JSON, default=dict)
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.facility.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    sources: Mapped[list["FacilitySource"]] = relationship(
        back_populates="facility", cascade="all, delete-orphan"
    )


class FacilitySource(Base):
    __tablename__ = "facility_source"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.facility.id", ondelete="CASCADE"), index=True
    )
    source_kind: Mapped[SourceKind] = mapped_column(
        Enum(SourceKind, name="source_kind", schema=SCHEMA)
    )
    external_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    facility: Mapped[Facility] = relationship(back_populates="sources")

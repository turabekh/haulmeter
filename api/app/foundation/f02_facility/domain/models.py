import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
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
    # 0..1, recomputed from the count + priority of contributing sources (PRD §12)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
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
    __table_args__ = (
        # one provenance row per (source, external id) — makes ingest idempotent and
        # keeps OSM-derived rows separable for ODbL compliance (PRD §12)
        UniqueConstraint(
            "source_kind", "external_ref", name="uq_facility_source_kind_ref"
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.facility.id", ondelete="CASCADE"), index=True
    )
    source_kind: Mapped[SourceKind] = mapped_column(
        Enum(SourceKind, name="source_kind", schema=SCHEMA)
    )
    external_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # this source's own contributed claim (name/amenities/capacity) — retained so
    # conflicts resolve deterministically by source priority, not by ingest order
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    facility: Mapped[Facility] = relationship(back_populates="sources")


class SourceRecord(Base):
    """AI-CONTEXT: F2 ingestion staging (PRD §12 / §7.2). Every external source
    lands here first — raw payload retained — then normalize → geohash blocking +
    fuzzy dedupe → canonical facility upsert. One table, `source_kind` discriminator
    (single-table staging, owner-approved). Unique (source_kind, external_ref) makes
    re-runs idempotent; `batch_id` groups a pull for observability."""

    __tablename__ = "source_record"
    __table_args__ = (
        UniqueConstraint("source_kind", "external_ref", name="uq_source_record_kind_ref"),
        Index("ix_source_record_geohash", "geohash"),
        Index("ix_source_record_kind_batch", "source_kind", "batch_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_kind: Mapped[SourceKind] = mapped_column(
        Enum(SourceKind, name="source_kind", schema=SCHEMA)
    )
    external_ref: Mapped[str] = mapped_column(String(300))
    batch_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)  # retained verbatim
    normalized: Mapped[dict] = mapped_column(JSON, default=dict)  # after normalize()
    name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    geohash: Mapped[str | None] = mapped_column(String(12), nullable=True)
    facility_type: Mapped[FacilityType | None] = mapped_column(
        Enum(FacilityType, name="facility_type", schema=SCHEMA), nullable=True
    )
    canonical_facility_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

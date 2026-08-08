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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

from .enums import FacilityStatus, FacilityType, SourceKind

SCHEMA = "f02"


class Facility(Base):
    __tablename__ = "facility"
    # AI-CONTEXT: A9 §4 — the GEOGRAPHY index, declared here and not only in a migration.
    #
    # `spatial_index=True` on `geom` gives a GiST index on the GEOMETRY. Every distance
    # query in this package casts to geography — `ST_DWithin(geom::geography, ...)` — and
    # a geometry index cannot answer that, so all six were sequential scans. Measured on
    # the box: 6,512 rows examined to return 26, in 28 ms. With this index, 30 rows and
    # 13.5 ms. The halving is not the point; a seq scan is LINEAR and A9 multiplies this
    # table by roughly six.
    #
    # Declared on the MODEL because the test database is built by `create_all`, not by
    # alembic — an index that lives only in a migration is invisible to every test, which
    # is its own small version of the defect this session kept finding.
    __table_args__ = (
        Index("ix_facility_geog", text("(geom::geography)"), postgresql_using="gist"),
        {"schema": SCHEMA},
    )

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
    # AI-CONTEXT: the IANA zone this place keeps its calendar in (audit F-14 + F-22).
    #
    # Nothing in the product knew a facility's local time, so two money questions were
    # being asked of UTC instants: how many NIGHTS a parking stay covers, and whether a
    # dwell was OVERNIGHT. Both are calendar-day questions, and a calendar day belongs to
    # a place. In a US-only product spanning four zones that is not a rounding error —
    # 8pm→4am in Dallas is one UTC day, so a real layover was refused outright.
    #
    # Nullable and resolved lazily by `facility_timezone`, which stores what it finds.
    # That covers the 4,800-odd rows already in the registry and any facility a driver
    # creates at a dock, without a backfill migration that could half-finish.
    timezone: Mapped[str | None] = mapped_column(String(60), nullable=True)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    hours: Mapped[dict] = mapped_column(JSON, default=dict)
    # 0..1, recomputed from the count + priority of contributing sources (PRD §12)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    # DEV_SEED field-test facilities: shown on the map, but excluded from real-data
    # dedupe + confidence so they never merge with or pollute NTAD/OSM/TPIMS records
    is_dev: Mapped[bool] = mapped_column(default=False)
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
        UniqueConstraint("source_kind", "external_ref", name="uq_facility_source_kind_ref"),
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

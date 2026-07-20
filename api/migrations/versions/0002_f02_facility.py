"""F2 canonical facility registry — facilities, sources, dedup, PostGIS geometry

Revision ID: 0002_f02_facility
Revises: 0001_f01_identity
Create Date: 2026-07-20
"""
from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "0002_f02_facility"
down_revision: str | None = "0001_f01_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f02"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    facility_type = sa.Enum(
        "truck_stop", "rest_area", "shipper_receiver", "parking_property", "scale",
        "weigh_station", "fuel_station", "repair", "composite",
        name="facility_type", schema=SCHEMA,
    )
    facility_status = sa.Enum(
        "candidate", "confirmed", "merged", name="facility_status", schema=SCHEMA
    )
    source_kind = sa.Enum(
        "osm", "fhwa", "tpims", "chain_list", "user_checkin", "admin",
        name="source_kind", schema=SCHEMA,
    )

    op.create_table(
        "facility",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("facility_type", facility_type, nullable=False),
        sa.Column("status", facility_status, nullable=False, server_default="confirmed"),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column(
            "lot_polygon",
            geoalchemy2.Geometry(geometry_type="POLYGON", srid=4326, spatial_index=False),
            nullable=True,
        ),
        sa.Column("geohash", sa.String(12), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=True),
        sa.Column("hours", sa.JSON(), nullable=True),
        sa.Column("merged_into_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["merged_into_id"], [f"{SCHEMA}.facility.id"], ondelete="SET NULL",
            name="fk_facility_merged_into_id_facility",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_facility_geohash", "facility", ["geohash"], schema=SCHEMA)
    op.execute(f"CREATE INDEX ix_facility_geom ON {SCHEMA}.facility USING gist (geom)")
    op.execute(
        f"CREATE INDEX ix_facility_lot_polygon ON {SCHEMA}.facility USING gist (lot_polygon)"
    )

    op.create_table(
        "facility_source",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("source_kind", source_kind, nullable=False),
        sa.Column("external_ref", sa.String(300), nullable=True),
        sa.Column("reported_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["facility_id"], [f"{SCHEMA}.facility.id"], ondelete="CASCADE",
            name="fk_facility_source_facility_id_facility",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_facility_source_facility_id", "facility_source", ["facility_id"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_table("facility_source", schema=SCHEMA)
    op.drop_table("facility", schema=SCHEMA)
    for enum_name in ("source_kind", "facility_status", "facility_type"):
        op.execute(f"DROP TYPE IF EXISTS {SCHEMA}.{enum_name}")
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")

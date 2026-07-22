"""F2 real-data ingestion — staging table, confidence, provenance attributes

Adds the `source_record` staging table (raw payload retained), `facility.confidence`,
`facility_source.attributes` + idempotency unique constraint, the `ntad` source kind,
and blocking/batch indexes. Extends the F2 pipeline for real POI sources (PRD §12).

Revision ID: 0027_f02_ingestion
Revises: 0026_f09_real_embeddings
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_f02_ingestion"
down_revision: str | None = "0026_f09_real_embeddings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f02"


def upgrade() -> None:
    # new source kind (append-only; safe to use next txn — this migration only adds it)
    op.execute(f"ALTER TYPE {SCHEMA}.source_kind ADD VALUE IF NOT EXISTS 'ntad'")

    op.add_column(
        "facility",
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        schema=SCHEMA,
    )
    op.add_column(
        "facility_source",
        sa.Column("attributes", sa.JSON(), nullable=False, server_default="{}"),
        schema=SCHEMA,
    )
    op.create_unique_constraint(
        "uq_facility_source_kind_ref", "facility_source", ["source_kind", "external_ref"],
        schema=SCHEMA,
    )

    facility_type = postgresql.ENUM(name="facility_type", schema=SCHEMA, create_type=False)
    source_kind = postgresql.ENUM(name="source_kind", schema=SCHEMA, create_type=False)
    op.create_table(
        "source_record",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_kind", source_kind, nullable=False),
        sa.Column("external_ref", sa.String(length=300), nullable=False),
        sa.Column("batch_id", sa.String(length=60), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("normalized", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("name", sa.String(length=300), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("geohash", sa.String(length=12), nullable=True),
        sa.Column("facility_type", facility_type, nullable=True),
        sa.Column("canonical_facility_id", sa.Uuid(), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source_kind", "external_ref", name="uq_source_record_kind_ref"),
        schema=SCHEMA,
    )
    op.create_index("ix_source_record_geohash", "source_record", ["geohash"], schema=SCHEMA)
    op.create_index(
        "ix_source_record_kind_batch", "source_record", ["source_kind", "batch_id"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_source_record_kind_batch", table_name="source_record", schema=SCHEMA)
    op.drop_index("ix_source_record_geohash", table_name="source_record", schema=SCHEMA)
    op.drop_table("source_record", schema=SCHEMA)
    op.drop_constraint("uq_facility_source_kind_ref", "facility_source", schema=SCHEMA)
    op.drop_column("facility_source", "attributes", schema=SCHEMA)
    op.drop_column("facility", "confidence", schema=SCHEMA)
    # enum value 'ntad' is left in place (Postgres cannot drop enum values cleanly)

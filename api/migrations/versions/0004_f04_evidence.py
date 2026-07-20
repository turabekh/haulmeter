"""F4 evidence engine — hash-chained records, artifacts, chain anchors

Revision ID: 0004_f04_evidence
Revises: 0003_f03_location
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_f04_evidence"
down_revision: str | None = "0003_f03_location"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f04"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    record_type = sa.Enum(
        "GEOFENCE",
        "PHOTO",
        "DOCUMENT",
        "USER_ACTION",
        "NOTIFICATION",
        "SYSTEM",
        name="record_type",
        schema=SCHEMA,
    )
    artifact_type = sa.Enum(
        "photo", "pdf", "document", "other", name="artifact_type", schema=SCHEMA
    )

    op.create_table(
        "evidence_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("stop_ref", sa.Uuid(), nullable=True),
        sa.Column("label", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["f01.account.id"],
            ondelete="CASCADE",
            name="fk_evidence_log_account_id_account",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_evidence_log_account_id", "evidence_log", ["account_id"], schema=SCHEMA)
    op.create_index("ix_evidence_log_stop_ref", "evidence_log", ["stop_ref"], schema=SCHEMA)

    op.create_table(
        "evidence_record",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("log_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("record_type", record_type, nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("record_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["log_id"],
            [f"{SCHEMA}.evidence_log.id"],
            ondelete="CASCADE",
            name="fk_evidence_record_log_id_evidence_log",
        ),
        sa.UniqueConstraint("log_id", "seq", name="uq_evidence_record_log_seq"),
        schema=SCHEMA,
    )
    op.create_index("ix_evidence_record_log_id", "evidence_record", ["log_id"], schema=SCHEMA)
    op.create_index(
        "ix_evidence_record_record_hash", "evidence_record", ["record_hash"], schema=SCHEMA
    )

    op.create_table(
        "evidence_artifact",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("log_id", sa.Uuid(), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_type", artifact_type, nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("exif", sa.JSON(), nullable=True),
        sa.Column("gps_lat", sa.Float(), nullable=True),
        sa.Column("gps_lon", sa.Float(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["log_id"],
            [f"{SCHEMA}.evidence_log.id"],
            ondelete="CASCADE",
            name="fk_evidence_artifact_log_id_evidence_log",
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            [f"{SCHEMA}.evidence_record.id"],
            ondelete="CASCADE",
            name="fk_evidence_artifact_record_id_evidence_record",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_evidence_artifact_log_id", "evidence_artifact", ["log_id"], schema=SCHEMA)
    op.create_index(
        "ix_evidence_artifact_record_id", "evidence_artifact", ["record_id"], schema=SCHEMA
    )
    op.create_index(
        "ix_evidence_artifact_content_hash", "evidence_artifact", ["content_hash"], schema=SCHEMA
    )

    op.create_table(
        "chain_anchor",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("log_id", sa.Uuid(), nullable=False),
        sa.Column("head_seq", sa.Integer(), nullable=False),
        sa.Column("head_hash", sa.String(64), nullable=False),
        sa.Column("external_ref", sa.String(300), nullable=True),
        sa.Column("anchored_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["log_id"],
            [f"{SCHEMA}.evidence_log.id"],
            ondelete="CASCADE",
            name="fk_chain_anchor_log_id_evidence_log",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_chain_anchor_log_id", "chain_anchor", ["log_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("chain_anchor", schema=SCHEMA)
    op.drop_table("evidence_artifact", schema=SCHEMA)
    op.drop_table("evidence_record", schema=SCHEMA)
    op.drop_table("evidence_log", schema=SCHEMA)
    for enum_name in ("artifact_type", "record_type"):
        op.execute(f"DROP TYPE IF EXISTS {SCHEMA}.{enum_name}")
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")

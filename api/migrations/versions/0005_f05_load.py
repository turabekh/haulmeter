"""F5 load & stop context — counterparties, loads, stops

Revision ID: 0005_f05_load
Revises: 0004_f04_evidence
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_f05_load"
down_revision: str | None = "0004_f04_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f05"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    counterparty_kind = sa.Enum(
        "broker", "shipper", "receiver", "carrier", name="counterparty_kind", schema=SCHEMA
    )
    load_source = sa.Enum(
        "manual", "rate_con_parse", "tms_push", name="load_source", schema=SCHEMA
    )
    load_status = sa.Enum(
        "draft", "active", "completed", "canceled", name="load_status", schema=SCHEMA
    )
    stop_type = sa.Enum("pickup", "delivery", name="stop_type", schema=SCHEMA)
    stop_status = sa.Enum(
        "pending", "armed", "arrived", "departed", "canceled", name="stop_status", schema=SCHEMA
    )

    op.create_table(
        "counterparty",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("kind", counterparty_kind, nullable=False),
        sa.Column("mc_number", sa.String(40), nullable=True),
        sa.Column("contact_email", sa.String(320), nullable=True),
        sa.Column("contact_phone", sa.String(40), nullable=True),
        sa.Column("payment_behavior", sa.JSON(), nullable=True),
        sa.Column("claim_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        schema=SCHEMA,
    )

    op.create_table(
        "load",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("counterparty_id", sa.Uuid(), nullable=True),
        sa.Column("reference_number", sa.String(120), nullable=True),
        sa.Column("rate_cents", sa.Integer(), nullable=True),
        sa.Column("detention_rate_cents_per_hour", sa.Integer(), nullable=True),
        sa.Column("free_time_minutes", sa.Integer(), nullable=True),
        sa.Column("accessorial_terms", sa.JSON(), nullable=True),
        sa.Column("source", load_source, nullable=False, server_default="manual"),
        sa.Column("status", load_status, nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["account_id"], ["f01.account.id"], ondelete="CASCADE",
            name="fk_load_account_id_account",
        ),
        sa.ForeignKeyConstraint(
            ["counterparty_id"], [f"{SCHEMA}.counterparty.id"], ondelete="SET NULL",
            name="fk_load_counterparty_id_counterparty",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_load_account_id", "load", ["account_id"], schema=SCHEMA)
    op.create_index("ix_load_counterparty_id", "load", ["counterparty_id"], schema=SCHEMA)

    op.create_table(
        "stop",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("load_id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("stop_type", stop_type, nullable=False),
        sa.Column("appointment_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("appointment_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("free_time_minutes", sa.Integer(), nullable=True),
        sa.Column("detention_rate_cents_per_hour", sa.Integer(), nullable=True),
        sa.Column("status", stop_status, nullable=False, server_default="pending"),
        sa.Column("geofence_armed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("evidence_log_id", sa.Uuid(), nullable=True),
        sa.Column("arrived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("departed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["load_id"], [f"{SCHEMA}.load.id"], ondelete="CASCADE",
            name="fk_stop_load_id_load",
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"], ["f02.facility.id"], ondelete="RESTRICT",
            name="fk_stop_facility_id_facility",
        ),
        sa.UniqueConstraint("load_id", "sequence", name="uq_stop_load_sequence"),
        schema=SCHEMA,
    )
    op.create_index("ix_stop_load_id", "stop", ["load_id"], schema=SCHEMA)
    op.create_index("ix_stop_facility_id", "stop", ["facility_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("stop", schema=SCHEMA)
    op.drop_table("load", schema=SCHEMA)
    op.drop_table("counterparty", schema=SCHEMA)
    for enum_name in (
        "stop_status", "stop_type", "load_status", "load_source", "counterparty_kind"
    ):
        op.execute(f"DROP TYPE IF EXISTS {SCHEMA}.{enum_name}")
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")

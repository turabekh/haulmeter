"""F10 crowd data pipeline — submissions, contributor trust, beliefs

Revision ID: 0010_f10_crowd
Revises: 0009_f09_ai_gateway
Create Date: 2026-07-20

AI-CONTEXT: self-contained local MetaData + create_all (decision #27): `signal_type`
is shared by two tables. Reference-only stubs for f01.account and f02.facility
resolve the cross-schema FKs (use_alter).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_f10_crowd"
down_revision: str | None = "0009_f09_ai_gateway"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f10"


def _tables():
    meta = sa.MetaData()
    signal_type = sa.Enum(
        "parking_fullness", "weigh_station_status", "fuel_price", "facility_attribute",
        name="signal_type", schema=SCHEMA,
    )

    sa.Table("account", meta, sa.Column("id", sa.Uuid(), primary_key=True), schema="f01")
    sa.Table("facility", meta, sa.Column("id", sa.Uuid(), primary_key=True), schema="f02")

    submission = sa.Table(
        "submission",
        meta,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("signal_type", signal_type, nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("presence_proven", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("trust_weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["account_id"], ["f01.account.id"], ondelete="CASCADE",
            name="fk_submission_account_id_account", use_alter=True,
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"], ["f02.facility.id"], ondelete="CASCADE",
            name="fk_submission_facility_id_facility", use_alter=True,
        ),
        sa.Index("ix_submission_account_id", "account_id"),
        sa.Index("ix_submission_facility_id", "facility_id"),
        sa.Index("ix_submission_signal_type", "signal_type"),
        sa.Index("ix_submission_submitted_at", "submitted_at"),
        schema=SCHEMA,
    )

    contributor_trust = sa.Table(
        "contributor_trust",
        meta,
        sa.Column("account_id", sa.Uuid(), primary_key=True),
        sa.Column("score", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("confirmed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["account_id"], ["f01.account.id"], ondelete="CASCADE",
            name="fk_contributor_trust_account_id_account", use_alter=True,
        ),
        schema=SCHEMA,
    )

    belief = sa.Table(
        "belief",
        meta,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("signal_type", signal_type, nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("freshest_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["facility_id"], ["f02.facility.id"], ondelete="CASCADE",
            name="fk_belief_facility_id_facility", use_alter=True,
        ),
        sa.UniqueConstraint("facility_id", "signal_type", name="uq_belief_facility_signal"),
        sa.Index("ix_belief_facility_id", "facility_id"),
        schema=SCHEMA,
    )
    return meta, [submission, contributor_trust, belief]


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    meta, tables = _tables()
    meta.create_all(op.get_bind(), tables=tables)


def downgrade() -> None:
    meta, tables = _tables()
    meta.drop_all(op.get_bind(), tables=tables)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")

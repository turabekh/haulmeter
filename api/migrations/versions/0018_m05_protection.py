"""M5 protection & document wallet — on-time proof, condition capture, incident

Revision ID: 0018_m05_protection
Revises: 0017_m04_accessorial
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_m05_protection"
down_revision: str | None = "0017_m04_accessorial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "m05"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    capture_phase = sa.Enum("pickup", "delivery", name="capture_phase", schema=SCHEMA)

    op.create_table(
        "on_time_proof",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("stop_ref", sa.Uuid(), nullable=False),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("within_window", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notice_sent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("evidence_log_ref", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["f01.account.id"],
            ondelete="CASCADE",
            name="fk_on_time_proof_account_id_account",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_on_time_proof_account_id", "on_time_proof", ["account_id"], schema=SCHEMA)
    op.create_index("ix_on_time_proof_stop_ref", "on_time_proof", ["stop_ref"], schema=SCHEMA)

    op.create_table(
        "condition_capture",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("stop_ref", sa.Uuid(), nullable=False),
        sa.Column("phase", capture_phase, nullable=False),
        sa.Column("evidence_log_ref", sa.Uuid(), nullable=False),
        sa.Column("photo_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["f01.account.id"],
            ondelete="CASCADE",
            name="fk_condition_capture_account_id_account",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_condition_capture_account_id", "condition_capture", ["account_id"], schema=SCHEMA
    )
    op.create_index(
        "ix_condition_capture_stop_ref", "condition_capture", ["stop_ref"], schema=SCHEMA
    )

    op.create_table(
        "incident",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("load_ref", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(60), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("evidence_log_ref", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["f01.account.id"],
            ondelete="CASCADE",
            name="fk_incident_account_id_account",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_incident_account_id", "incident", ["account_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("incident", schema=SCHEMA)
    op.drop_table("condition_capture", schema=SCHEMA)
    op.drop_table("on_time_proof", schema=SCHEMA)
    op.execute(f"DROP TYPE IF EXISTS {SCHEMA}.capture_phase")
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")

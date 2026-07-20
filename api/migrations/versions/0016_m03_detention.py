"""M3 detention tracker — detention claims

Revision ID: 0016_m03_detention
Revises: 0015_m02_facility_intel
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_m03_detention"
down_revision: str | None = "0015_m02_facility_intel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "m03"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    claim_mode = sa.Enum("invoice", "evidence_only", name="claim_mode", schema=SCHEMA)
    detention_trigger = sa.Enum("appointment", "arrival", name="detention_trigger", schema=SCHEMA)
    claim_state = sa.Enum(
        "open", "packaged", "invoiced", "exported", "escalated", name="claim_state", schema=SCHEMA
    )

    op.create_table(
        "detention_claim",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("stop_ref", sa.Uuid(), nullable=False),
        sa.Column("facility_ref", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("counterparty_ref", sa.Uuid(), nullable=True),
        sa.Column("mode", claim_mode, nullable=False),
        sa.Column("trigger", detention_trigger, nullable=False, server_default="arrival"),
        sa.Column("free_time_minutes", sa.Integer(), nullable=True),
        sa.Column("detention_rate_cents_per_hour", sa.Integer(), nullable=True),
        sa.Column("detention_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("evidence_log_ref", sa.Uuid(), nullable=True),
        sa.Column("receivable_ref", sa.Uuid(), nullable=True),
        sa.Column("state", claim_state, nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["f01.account.id"],
            ondelete="CASCADE",
            name="fk_detention_claim_account_id_account",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_detention_claim_stop_ref", "detention_claim", ["stop_ref"], schema=SCHEMA)
    op.create_index(
        "ix_detention_claim_account_id", "detention_claim", ["account_id"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_table("detention_claim", schema=SCHEMA)
    for enum_name in ("claim_state", "detention_trigger", "claim_mode"):
        op.execute(f"DROP TYPE IF EXISTS {SCHEMA}.{enum_name}")
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")

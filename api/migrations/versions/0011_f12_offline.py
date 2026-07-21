"""F12 offline sync & outbox — idempotent sync envelopes

Revision ID: 0011_f12_offline
Revises: 0010_f10_crowd
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_f12_offline"
down_revision: str | None = "0010_f10_crowd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f12"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    op.create_table(
        "sync_envelope",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(60), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("client_skew_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["f01.account.id"],
            ondelete="CASCADE",
            name="fk_sync_envelope_account_id_account",
        ),
        sa.UniqueConstraint("account_id", "idempotency_key", name="uq_sync_account_idempotency"),
        schema=SCHEMA,
    )
    op.create_index("ix_sync_envelope_account_id", "sync_envelope", ["account_id"], schema=SCHEMA)
    op.create_index("ix_sync_envelope_kind", "sync_envelope", ["kind"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("sync_envelope", schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")

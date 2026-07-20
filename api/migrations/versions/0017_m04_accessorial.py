"""M4 accessorial recovery — accessorial claims

Revision ID: 0017_m04_accessorial
Revises: 0016_m03_detention
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_m04_accessorial"
down_revision: str | None = "0016_m03_detention"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "m04"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    accessorial_kind = sa.Enum("tonu", "layover", "lumper", name="accessorial_kind", schema=SCHEMA)
    accessorial_state = sa.Enum("draft", "invoiced", name="accessorial_state", schema=SCHEMA)

    op.create_table(
        "accessorial_claim",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("load_ref", sa.Uuid(), nullable=False),
        sa.Column("stop_ref", sa.Uuid(), nullable=True),
        sa.Column("counterparty_ref", sa.Uuid(), nullable=True),
        sa.Column("kind", accessorial_kind, nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("document_ref", sa.Uuid(), nullable=True),
        sa.Column("receivable_ref", sa.Uuid(), nullable=True),
        sa.Column("state", accessorial_state, nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["f01.account.id"],
            ondelete="CASCADE",
            name="fk_accessorial_claim_account_id_account",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_accessorial_claim_account_id", "accessorial_claim", ["account_id"], schema=SCHEMA
    )
    op.create_index(
        "ix_accessorial_claim_load_ref", "accessorial_claim", ["load_ref"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_table("accessorial_claim", schema=SCHEMA)
    for enum_name in ("accessorial_state", "accessorial_kind"):
        op.execute(f"DROP TYPE IF EXISTS {SCHEMA}.{enum_name}")
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")

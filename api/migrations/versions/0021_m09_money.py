"""M9 driver money & tax tools — settlements, discrepancies, expense receipts

Revision ID: 0021_m09_money
Revises: 0020_m07_fuel
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_m09_money"
down_revision: str | None = "0020_m07_fuel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "m09"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    discrepancy_status = sa.Enum(
        "flagged", "submitted", "resolved", name="discrepancy_status", schema=SCHEMA
    )

    op.create_table(
        "settlement",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("driver_account_id", sa.Uuid(), nullable=False),
        sa.Column("carrier", sa.String(200), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("gross_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("doc_ref", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["driver_account_id"], ["f01.account.id"], ondelete="CASCADE",
            name="fk_settlement_driver_account_id_account",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_settlement_driver_account_id", "settlement", ["driver_account_id"], schema=SCHEMA
    )

    op.create_table(
        "settlement_line",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("settlement_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["settlement_id"], [f"{SCHEMA}.settlement.id"], ondelete="CASCADE",
            name="fk_settlement_line_settlement_id_settlement",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_settlement_line_settlement_id", "settlement_line", ["settlement_id"], schema=SCHEMA
    )

    op.create_table(
        "discrepancy",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("settlement_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("owed_cents", sa.BigInteger(), nullable=False),
        sa.Column("paid_cents", sa.BigInteger(), nullable=False),
        sa.Column("missed_cents", sa.BigInteger(), nullable=False),
        sa.Column("evidence_ref", sa.Uuid(), nullable=True),
        sa.Column("status", discrepancy_status, nullable=False, server_default="flagged"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["settlement_id"], [f"{SCHEMA}.settlement.id"], ondelete="CASCADE",
            name="fk_discrepancy_settlement_id_settlement",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_discrepancy_settlement_id", "discrepancy", ["settlement_id"], schema=SCHEMA)

    op.create_table(
        "expense_receipt",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("driver_account_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("doc_ref", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["driver_account_id"], ["f01.account.id"], ondelete="CASCADE",
            name="fk_expense_receipt_driver_account_id_account",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_expense_receipt_driver_account_id", "expense_receipt", ["driver_account_id"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_table("expense_receipt", schema=SCHEMA)
    op.drop_table("discrepancy", schema=SCHEMA)
    op.drop_table("settlement_line", schema=SCHEMA)
    op.drop_table("settlement", schema=SCHEMA)
    op.execute(f"DROP TYPE IF EXISTS {SCHEMA}.discrepancy_status")
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")

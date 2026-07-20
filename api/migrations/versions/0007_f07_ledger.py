"""F7 ledger & payments — double-entry ledger, receivables

Revision ID: 0007_f07_ledger
Revises: 0006_f06_documents
Create Date: 2026-07-20

AI-CONTEXT: uses a self-contained local MetaData + create_all so the shared
`currency` enum (referenced by three tables) is emitted exactly once. op.create_table
emits a CREATE TYPE per enum column here, which collides for shared enums; one
MetaData with a single shared Enum object dedupes it (same pattern the models use).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_f07_ledger"
down_revision: str | None = "0006_f06_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f07"


def _tables():
    meta = sa.MetaData()
    currency = sa.Enum("usd", "points", name="currency", schema=SCHEMA)

    # Reference-only stub so the cross-schema FK to f01.account resolves; never
    # created/dropped here (f01 owns it).
    sa.Table(
        "account",
        meta,
        sa.Column("id", sa.Uuid(), primary_key=True),
        schema="f01",
    )

    ledger_account = sa.Table(
        "ledger_account",
        meta,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "kind",
            sa.Enum(
                "driver_cash",
                "driver_payable",
                "owner_payable",
                "claim_receivable",
                "platform_revenue",
                "contingency_revenue",
                "fuel_clearing",
                "cash_clearing",
                "points_balance",
                "points_pool",
                name="ledger_account_kind",
                schema=SCHEMA,
            ),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("currency", currency, nullable=False, server_default="usd"),
        sa.Column("owner_ref", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Index("ix_ledger_account_owner_ref", "owner_ref"),
        schema=SCHEMA,
    )

    journal_entry = sa.Table(
        "journal_entry",
        meta,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "entry_type",
            sa.Enum(
                "booking_payment",
                "owner_payout",
                "claim_recovery",
                "contingency_fee",
                "fuel_txn",
                "points_earn",
                "points_redeem",
                "adjustment",
                name="entry_type",
                schema=SCHEMA,
            ),
            nullable=False,
        ),
        sa.Column("currency", currency, nullable=False),
        sa.Column("description", sa.String(300), nullable=True),
        sa.Column("external_ref", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        schema=SCHEMA,
    )

    ledger_posting = sa.Table(
        "ledger_posting",
        meta,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("ledger_account_id", sa.Uuid(), nullable=False),
        sa.Column(
            "direction", sa.Enum("debit", "credit", name="direction", schema=SCHEMA), nullable=False
        ),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            [f"{SCHEMA}.journal_entry.id"],
            ondelete="CASCADE",
            name="fk_ledger_posting_entry_id_journal_entry",
        ),
        sa.ForeignKeyConstraint(
            ["ledger_account_id"],
            [f"{SCHEMA}.ledger_account.id"],
            ondelete="RESTRICT",
            name="fk_ledger_posting_ledger_account_id_ledger_account",
        ),
        sa.Index("ix_ledger_posting_entry_id", "entry_id"),
        sa.Index("ix_ledger_posting_ledger_account_id", "ledger_account_id"),
        schema=SCHEMA,
    )

    receivable = sa.Table(
        "receivable",
        meta,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("counterparty_ref", sa.Uuid(), nullable=True),
        sa.Column(
            "kind",
            sa.Enum(
                "detention", "tonu", "layover", "lumper", name="receivable_kind", schema=SCHEMA
            ),
            nullable=False,
        ),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", currency, nullable=False, server_default="usd"),
        sa.Column(
            "state",
            sa.Enum(
                "invoiced",
                "acknowledged",
                "disputed",
                "escalated",
                "recovered",
                "written_off",
                name="receivable_state",
                schema=SCHEMA,
            ),
            nullable=False,
            server_default="invoiced",
        ),
        sa.Column("entry_id", sa.Uuid(), nullable=True),
        sa.Column("external_ref", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["f01.account.id"],
            ondelete="CASCADE",
            name="fk_receivable_account_id_account",
            use_alter=True,
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            [f"{SCHEMA}.journal_entry.id"],
            ondelete="SET NULL",
            name="fk_receivable_entry_id_journal_entry",
        ),
        sa.Index("ix_receivable_account_id", "account_id"),
        sa.Index("ix_receivable_counterparty_ref", "counterparty_ref"),
        schema=SCHEMA,
    )
    return meta, [ledger_account, journal_entry, ledger_posting, receivable]


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    meta, tables = _tables()
    meta.create_all(op.get_bind(), tables=tables)


def downgrade() -> None:
    meta, tables = _tables()
    meta.drop_all(op.get_bind(), tables=tables)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")

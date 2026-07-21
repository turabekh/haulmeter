"""M7 fuel savings network — merchants, station pricing, fuel transactions

Revision ID: 0020_m07_fuel
Revises: 0019_m06_parking
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_m07_fuel"
down_revision: str | None = "0019_m06_parking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "m07"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    price_source = sa.Enum("feed", "crowd", name="price_source", schema=SCHEMA)
    fuel_txn_state = sa.Enum(
        "code_issued", "settled", "canceled", name="fuel_txn_state", schema=SCHEMA
    )

    op.create_table(
        "merchant",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("settlement_terms", sa.String(80), nullable=False, server_default="net_15"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        schema=SCHEMA,
    )

    op.create_table(
        "station_pricing",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("facility_ref", sa.Uuid(), nullable=False),
        sa.Column("merchant_id", sa.Uuid(), nullable=True),
        sa.Column("gross_cents_per_gal", sa.Integer(), nullable=False),
        sa.Column("discount_cents_per_gal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("spread_cents_per_gal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", price_source, nullable=False, server_default="feed"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["merchant_id"],
            [f"{SCHEMA}.merchant.id"],
            ondelete="SET NULL",
            name="fk_station_pricing_merchant_id_merchant",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_station_pricing_facility_ref",
        "station_pricing",
        ["facility_ref"],
        unique=True,
        schema=SCHEMA,
    )
    op.create_index(
        "ix_station_pricing_merchant_id", "station_pricing", ["merchant_id"], schema=SCHEMA
    )

    op.create_table(
        "fuel_transaction",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("driver_account_id", sa.Uuid(), nullable=False),
        sa.Column("station_ref", sa.Uuid(), nullable=False),
        sa.Column("merchant_id", sa.Uuid(), nullable=True),
        sa.Column("gallons_milli", sa.Integer(), nullable=False),
        sa.Column("gross_cents_per_gal", sa.Integer(), nullable=False),
        sa.Column("net_cents_per_gal", sa.Integer(), nullable=False),
        sa.Column("spread_cents_per_gal", sa.Integer(), nullable=False),
        sa.Column("gross_cents", sa.BigInteger(), nullable=False),
        sa.Column("net_cents", sa.BigInteger(), nullable=False),
        sa.Column("spread_cents", sa.BigInteger(), nullable=False),
        sa.Column("pump_code", sa.String(16), nullable=False),
        sa.Column("state", fuel_txn_state, nullable=False, server_default="code_issued"),
        sa.Column("entry_ref", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["driver_account_id"],
            ["f01.account.id"],
            ondelete="CASCADE",
            name="fk_fuel_transaction_driver_account_id_account",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_fuel_transaction_driver_account_id",
        "fuel_transaction",
        ["driver_account_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_fuel_transaction_station_ref", "fuel_transaction", ["station_ref"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_table("fuel_transaction", schema=SCHEMA)
    op.drop_table("station_pricing", schema=SCHEMA)
    op.drop_table("merchant", schema=SCHEMA)
    op.execute(f"DROP TYPE IF EXISTS {SCHEMA}.fuel_txn_state")
    op.execute(f"DROP TYPE IF EXISTS {SCHEMA}.price_source")
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")

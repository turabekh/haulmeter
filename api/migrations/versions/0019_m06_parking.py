"""M6 parking marketplace — properties, spots, bookings

Revision ID: 0019_m06_parking
Revises: 0018_m05_protection
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_m06_parking"
down_revision: str | None = "0018_m05_protection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "m06"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    booking_state = sa.Enum(
        "booked",
        "checked_in",
        "checked_out",
        "canceled",
        "refunded",
        name="booking_state",
        schema=SCHEMA,
    )

    op.create_table(
        "parking_property",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_account_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("facility_ref", sa.Uuid(), nullable=False),
        sa.Column("vetted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["owner_account_id"],
            ["f01.account.id"],
            ondelete="CASCADE",
            name="fk_parking_property_owner_account_id_account",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_parking_property_owner_account_id",
        "parking_property",
        ["owner_account_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_parking_property_facility_ref", "parking_property", ["facility_ref"], schema=SCHEMA
    )

    op.create_table(
        "parking_spot",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("price_cents_per_night", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["property_id"],
            [f"{SCHEMA}.parking_property.id"],
            ondelete="CASCADE",
            name="fk_parking_spot_property_id_parking_property",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_parking_spot_property_id", "parking_spot", ["property_id"], schema=SCHEMA)

    op.create_table(
        "booking",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("spot_id", sa.Uuid(), nullable=False),
        sa.Column("driver_account_id", sa.Uuid(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("nights", sa.Integer(), nullable=False),
        sa.Column("price_cents", sa.BigInteger(), nullable=False),
        sa.Column("take_cents", sa.BigInteger(), nullable=False),
        sa.Column("owner_payout_cents", sa.BigInteger(), nullable=False),
        sa.Column("state", booking_state, nullable=False, server_default="booked"),
        sa.Column("entry_ref", sa.Uuid(), nullable=True),
        sa.Column("refund_entry_ref", sa.Uuid(), nullable=True),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checked_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["spot_id"],
            [f"{SCHEMA}.parking_spot.id"],
            ondelete="CASCADE",
            name="fk_booking_spot_id_parking_spot",
        ),
        sa.ForeignKeyConstraint(
            ["driver_account_id"],
            ["f01.account.id"],
            ondelete="CASCADE",
            name="fk_booking_driver_account_id_account",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_booking_spot_id", "booking", ["spot_id"], schema=SCHEMA)
    op.create_index("ix_booking_driver_account_id", "booking", ["driver_account_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("booking", schema=SCHEMA)
    op.drop_table("parking_spot", schema=SCHEMA)
    op.drop_table("parking_property", schema=SCHEMA)
    op.execute(f"DROP TYPE IF EXISTS {SCHEMA}.booking_state")
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")

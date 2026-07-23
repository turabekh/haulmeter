"""M7 — regional fuel price baseline (EIA weekly on-highway diesel per PADD)

The indicative price shown on a fuel station until a network feed or a crowd
report (M7-FR5) gives a real per-station price (M1-FR5).

Revision ID: 0030_m07_regional_fuel
Revises: 0029_f02_is_dev
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_m07_regional_fuel"
down_revision: str | None = "0029_f02_is_dev"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "m07"


def upgrade() -> None:
    op.create_table(
        "regional_fuel_price",
        sa.Column("region", sa.String(length=8), primary_key=True),
        sa.Column("gross_cents_per_gal", sa.Integer(), nullable=False),
        sa.Column("week_of", sa.Date(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("regional_fuel_price", schema=SCHEMA)

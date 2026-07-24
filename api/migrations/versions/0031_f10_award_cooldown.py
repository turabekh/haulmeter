"""F10 — awarded flag on submissions (points-farming cooldown)

The belief is already spam-proof (distinct-contributor aggregation), but points
were awarded per presence-proven submission, so a driver could farm points by
re-reporting. `awarded` marks the submissions that actually issued points, so a
per-driver/per-facility/per-signal cooldown anchors on the last AWARD (not on any
recorded submission) and never slides off intermediate cooled-down reports.

Revision ID: 0031_f10_award_cooldown
Revises: 0030_m07_regional_fuel_price
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_f10_award_cooldown"
down_revision: str | None = "0030_m07_regional_fuel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f10"


def upgrade() -> None:
    op.add_column(
        "submission",
        sa.Column("awarded", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("submission", "awarded", schema=SCHEMA)

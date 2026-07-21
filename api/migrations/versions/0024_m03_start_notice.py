"""M3 detention — record when the detention-start notice was sent

Revision ID: 0024_m03_start_notice
Revises: 0023_m12_fleet
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_m03_start_notice"
down_revision: str | None = "0023_m12_fleet"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "m03"


def upgrade() -> None:
    op.add_column(
        "detention_claim",
        sa.Column("start_notice_sent_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("detention_claim", "start_notice_sent_at", schema=SCHEMA)

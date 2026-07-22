"""F2 — is_dev flag on facilities (isolate DEV_SEED field-test data)

DEV_SEED facilities render on the map but are excluded from real-data dedupe +
confidence so they never merge with or pollute NTAD/OSM/TPIMS records (PRD §12).

Revision ID: 0029_f02_is_dev
Revises: 0028_f10_authoritative
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_f02_is_dev"
down_revision: str | None = "0028_f10_authoritative"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f02"


def upgrade() -> None:
    op.add_column(
        "facility",
        sa.Column("is_dev", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("facility", "is_dev", schema=SCHEMA)

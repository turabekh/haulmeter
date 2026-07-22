"""F10 crowd — authoritative feed submissions (TPIMS)

Lets an authoritative source (TPIMS dynamic availability) contribute to the belief
pipeline: a submission with no driver account, a real source + timestamp, and
precedence over crowd at equal freshness (PRD §12).

Revision ID: 0028_f10_authoritative
Revises: 0027_f02_ingestion
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_f10_authoritative"
down_revision: str | None = "0027_f02_ingestion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f10"


def upgrade() -> None:
    op.alter_column(
        "submission", "account_id", existing_type=sa.Uuid(), nullable=True, schema=SCHEMA
    )
    op.add_column(
        "submission",
        sa.Column("authoritative", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema=SCHEMA,
    )
    op.add_column(
        "submission", sa.Column("source", sa.String(length=40), nullable=True), schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_column("submission", "source", schema=SCHEMA)
    op.drop_column("submission", "authoritative", schema=SCHEMA)
    op.alter_column(
        "submission", "account_id", existing_type=sa.Uuid(), nullable=False, schema=SCHEMA
    )

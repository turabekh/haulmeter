"""F15 localization — message catalog, glossary; per-user locale on F1 profile

Revision ID: 0014_f15_localization
Revises: 0013_f14_admin
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_f15_localization"
down_revision: str | None = "0013_f14_admin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f15"


def upgrade() -> None:
    # per-user locale lives on the F1 profile (PRD §7.15)
    op.add_column(
        "driver_profile",
        sa.Column("locale", sa.String(12), nullable=False, server_default="en"),
        schema="f01",
    )

    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "message_catalog",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("key", sa.String(160), nullable=False),
        sa.Column("locale", sa.String(12), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("key", "locale", name="uq_message_catalog_key_locale"),
        schema=SCHEMA,
    )
    op.create_index("ix_message_catalog_key", "message_catalog", ["key"], schema=SCHEMA)
    op.create_index("ix_message_catalog_locale", "message_catalog", ["locale"], schema=SCHEMA)

    op.create_table(
        "glossary_term",
        sa.Column("term", sa.String(80), primary_key=True),
        sa.Column("keep_english", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("definition", sa.String(400), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("glossary_term", schema=SCHEMA)
    op.drop_table("message_catalog", schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")
    op.drop_column("driver_profile", "locale", schema="f01")

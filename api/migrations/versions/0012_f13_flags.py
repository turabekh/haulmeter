"""F13 feature flags, validation gates & config registry

Revision ID: 0012_f13_flags
Revises: 0011_f12_offline
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_f13_flags"
down_revision: str | None = "0011_f12_offline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f13"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "feature_flag",
        sa.Column("key", sa.String(120), primary_key=True),
        sa.Column("description", sa.String(300), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("kill_switch", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        schema=SCHEMA,
    )

    op.create_table(
        "validation_gate",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("flag_key", sa.String(120), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("satisfied", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("satisfied_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["flag_key"],
            [f"{SCHEMA}.feature_flag.key"],
            ondelete="CASCADE",
            name="fk_validation_gate_flag_key_feature_flag",
        ),
        sa.UniqueConstraint("flag_key", "name", name="uq_validation_gate_flag_name"),
        schema=SCHEMA,
    )
    op.create_index("ix_validation_gate_flag_key", "validation_gate", ["flag_key"], schema=SCHEMA)

    op.create_table(
        "config_entry",
        sa.Column("key", sa.String(120), primary_key=True),
        sa.Column("scope", sa.String(60), nullable=False, server_default="global"),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        schema=SCHEMA,
    )
    op.create_index("ix_config_entry_scope", "config_entry", ["scope"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("config_entry", schema=SCHEMA)
    op.drop_table("validation_gate", schema=SCHEMA)
    op.drop_table("feature_flag", schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")

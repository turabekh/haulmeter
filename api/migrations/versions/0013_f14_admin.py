"""F14 admin console & analytics — events, audit log, moderation, view registry

Revision ID: 0013_f14_admin
Revises: 0012_f13_flags
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_f14_admin"
down_revision: str | None = "0012_f13_flags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f14"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    moderation_status = sa.Enum(
        "pending", "approved", "rejected", name="moderation_status", schema=SCHEMA
    )

    op.create_table(
        "analytics_event",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event_name", sa.String(120), nullable=False),
        sa.Column("module", sa.String(40), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("properties", sa.JSON(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["f01.account.id"],
            ondelete="SET NULL",
            name="fk_analytics_event_account_id_account",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_analytics_event_event_name", "analytics_event", ["event_name"], schema=SCHEMA
    )
    op.create_index("ix_analytics_event_module", "analytics_event", ["module"], schema=SCHEMA)
    op.create_index(
        "ix_analytics_event_account_id", "analytics_event", ["account_id"], schema=SCHEMA
    )
    op.create_index(
        "ix_analytics_event_occurred_at", "analytics_event", ["occurred_at"], schema=SCHEMA
    )

    op.create_table(
        "admin_action",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_account_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("target_kind", sa.String(60), nullable=True),
        sa.Column("target_ref", sa.Uuid(), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["actor_account_id"],
            ["f01.account.id"],
            ondelete="SET NULL",
            name="fk_admin_action_actor_account_id_account",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_admin_action_actor_account_id", "admin_action", ["actor_account_id"], schema=SCHEMA
    )
    op.create_index("ix_admin_action_action", "admin_action", ["action"], schema=SCHEMA)

    op.create_table(
        "moderation_item",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("content_kind", sa.String(60), nullable=False),
        sa.Column("content_ref", sa.Uuid(), nullable=False),
        sa.Column("submitted_by", sa.Uuid(), nullable=True),
        sa.Column("status", moderation_status, nullable=False, server_default="pending"),
        sa.Column("moderator_account_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["submitted_by"],
            ["f01.account.id"],
            ondelete="SET NULL",
            name="fk_moderation_item_submitted_by_account",
        ),
        sa.ForeignKeyConstraint(
            ["moderator_account_id"],
            ["f01.account.id"],
            ondelete="SET NULL",
            name="fk_moderation_item_moderator_account_id_account",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_moderation_item_content_kind", "moderation_item", ["content_kind"], schema=SCHEMA
    )
    op.create_index(
        "ix_moderation_item_content_ref", "moderation_item", ["content_ref"], schema=SCHEMA
    )
    op.create_index("ix_moderation_item_status", "moderation_item", ["status"], schema=SCHEMA)

    op.create_table(
        "admin_view",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("module", sa.String(40), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("path", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("key", name="uq_admin_view_key"),
        schema=SCHEMA,
    )
    op.create_index("ix_admin_view_module", "admin_view", ["module"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("admin_view", schema=SCHEMA)
    op.drop_table("moderation_item", schema=SCHEMA)
    op.drop_table("admin_action", schema=SCHEMA)
    op.drop_table("analytics_event", schema=SCHEMA)
    op.execute(f"DROP TYPE IF EXISTS {SCHEMA}.moderation_status")
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")

"""E-D1 — opt-in notification classes (`vendor_alert`)

design-prd §23 E-D1 approves a notification class whose interruption laws are
stricter than its tier: OFF until the driver turns it on, its own daily cap on
top of the §13.1 budget, route/favorite relevance, and a one-tap per-subject
mute. Absence of a row means NOT opted in — silence is never read as consent.

The class definitions live in code (f08 service) so the laws are reviewable in
one place; only the per-driver choice is data.

Revision ID: 0035_f08_notification_class
Revises: 0034_f10_vendor_signals
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035_f08_notification_class"
down_revision: str | None = "0034_f10_vendor_signals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f08"
NEW_SUPPRESS_REASONS = ("not_opted_in", "muted")


def upgrade() -> None:
    op.execute("COMMIT")
    for value in NEW_SUPPRESS_REASONS:
        op.execute(f"ALTER TYPE {SCHEMA}.suppress_reason ADD VALUE IF NOT EXISTS '{value}'")

    op.create_table(
        "notification_class_pref",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("f01.account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("class_key", sa.String(60), nullable=False),
        sa.Column("opted_in", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("muted_subjects", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("account_id", "class_key", name="uq_class_pref_account_class"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_f08_class_pref_account", "notification_class_pref", ["account_id"], schema=SCHEMA
    )
    op.create_index(
        "ix_f08_class_pref_key", "notification_class_pref", ["class_key"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_f08_class_pref_key", "notification_class_pref", schema=SCHEMA)
    op.drop_index("ix_f08_class_pref_account", "notification_class_pref", schema=SCHEMA)
    op.drop_table("notification_class_pref", schema=SCHEMA)
    # enum values cannot be dropped in PostgreSQL — the two reasons remain

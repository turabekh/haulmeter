"""E-D5 — scoped impersonation sessions ("view as vendor")

The session belongs to the ADMIN and merely NAMES the vendor it acts for, never the
other way round. That ordering is the safety property: every write attributes to the
admin structurally rather than by convention, and `resolve_session` refuses any token
carrying this column, so an impersonation token cannot reach a driver endpoint
however it is passed around.

Time-boxed at 30 minutes (owner-approved): a support session left open is an
unlocked door.

Revision ID: 0043_f01_impersonation
Revises: 0042_f01_account_management
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0043_f01_impersonation"
down_revision: str | None = "0042_f01_account_management"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f01"


def upgrade() -> None:
    op.add_column(
        "auth_session",
        sa.Column(
            "impersonating_account_id",
            sa.Uuid(),
            sa.ForeignKey(f"{SCHEMA}.account.id", ondelete="CASCADE"),
            nullable=True,
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "auth_session", sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_f01_session_impersonating", "auth_session", ["impersonating_account_id"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_f01_session_impersonating", "auth_session", schema=SCHEMA)
    op.drop_column("auth_session", "ended_at", schema=SCHEMA)
    op.drop_column("auth_session", "impersonating_account_id", schema=SCHEMA)

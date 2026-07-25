"""E-D6 — admin account management: active flag, display name, forced credential change

Deactivation, never deletion. An account references money, claims and evidence, so
erasing one would tear holes in records a third party may need to verify.
Deactivating blocks login and hides driver-facing presence while every row it points
at survives intact — hard delete is a data-retention WORKFLOW (PRD §17 Q16).

`must_change` carries the credential-reset flow: an admin issues a TEMPORARY
password and nothing else. Support that can read a password is support that can be
social-engineered into surrendering one.

Revision ID: 0042_f01_account_management
Revises: 0041_f14_audit_clock
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0042_f01_account_management"
down_revision: str | None = "0041_f14_audit_clock"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f01"


def upgrade() -> None:
    op.add_column(
        "account", sa.Column("display_name", sa.String(120), nullable=True), schema=SCHEMA
    )
    op.add_column(
        "account",
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        schema=SCHEMA,
    )
    op.add_column(
        "account", sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index("ix_f01_account_active", "account", ["active"], schema=SCHEMA)
    op.add_column(
        "auth_method",
        sa.Column("must_change", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("auth_method", "must_change", schema=SCHEMA)
    op.drop_index("ix_f01_account_active", "account", schema=SCHEMA)
    for column in ("deactivated_at", "active", "display_name"):
        op.drop_column("account", column, schema=SCHEMA)

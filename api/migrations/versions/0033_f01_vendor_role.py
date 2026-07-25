"""M13-FR1 — `vendor` account role via the F1 pluggable role registry

A vendor is the same F1 account model with a new role attachment; one vendor
account may carry several members (owner + helpers), so the role lives on the
attachment exactly like fleet_admin / property_owner.

`ALTER TYPE ... ADD VALUE` cannot run inside a transaction block on PostgreSQL,
so this migration commits the surrounding transaction first (Alembic wraps each
migration in one). IF NOT EXISTS keeps a re-run idempotent. Enum values cannot be
dropped in PostgreSQL, so the downgrade is a documented no-op.

Revision ID: 0033_f01_vendor_role
Revises: 0032_f01_equipment
Create Date: 2026-07-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0033_f01_vendor_role"
down_revision: str | None = "0032_f01_equipment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("COMMIT")
    op.execute("ALTER TYPE f01.role ADD VALUE IF NOT EXISTS 'vendor'")


def downgrade() -> None:
    pass

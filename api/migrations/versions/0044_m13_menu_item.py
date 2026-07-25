"""M13 — the vendor's standing menu

Offerings were keyed to the appearance and nothing else, so a cook retyped every
dish and every price for every window. This table is the list they keep.

It deliberately does NOT replace `offering`. A menu item is what the vendor sells;
an offering is what was ADVERTISED for one window. Publishing copies the first into
the second, so raising a price today changes what is advertised next and never what
a driver was shown last Tuesday — the reliability record and the reviews both refer
to past windows, and a menu that rewrote history would make them unauditable.

`price_cents` is information only. Phase A processes no payments and the platform
sells nothing (PRD extension §E1.1): no order, no basket, no total, no billing.

Revision ID: 0044_m13_menu_item
Revises: 0043_f01_impersonation
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044_m13_menu_item"
down_revision: str | None = "0043_f01_impersonation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "m13"


def upgrade() -> None:
    op.create_table(
        "menu_item",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "vendor_id",
            sa.Uuid(),
            sa.ForeignKey(f"{SCHEMA}.vendor.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("portions", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("vendor_id", "name", name="uq_menu_item_vendor_name"),
        schema=SCHEMA,
    )
    op.create_index("ix_m13_menu_item_vendor", "menu_item", ["vendor_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_m13_menu_item_vendor", "menu_item", schema=SCHEMA)
    op.drop_table("menu_item", schema=SCHEMA)

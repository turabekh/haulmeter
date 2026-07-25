"""M13 — a structured halal claim, so discovery does not have to parse a sentence

`halal_disclosure` is free text and stays exactly as it is: it is the vendor's own
words and the driver sees them verbatim. But a FILTER over free text would mean the
platform reading a cook's sentence and deciding who counts as halal — which is the
platform making a halal claim of its own, and §23 already settled that it does not.

So the cook answers a closed question as well as an open one. Three rungs, each
meaning precisely what it says:

    not_claimed   — the vendor does not claim halal. A complete, honest answer.
    self_declared — the VENDOR says halal. Nobody has checked, and the driver-facing
                    label says "vendor says", never a bare "Halal".
    certified     — an approved halal_cert document exists. Not self-awardable; see
                    `allowed_halal_claim`, which downgrades an unsupported claim.

Existing rows default to not_claimed. That is the honest backfill: nobody has
answered the closed question yet, and inferring it from their sentence is the exact
thing this column exists to avoid.

Revision ID: 0045_m13_halal_claim
Revises: 0044_m13_menu_item
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0045_m13_halal_claim"
down_revision: str | None = "0044_m13_menu_item"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "m13"
CLAIMS = ("not_claimed", "self_declared", "certified")


def upgrade() -> None:
    claim = sa.Enum(*CLAIMS, name="halal_claim", schema=SCHEMA)
    claim.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "vendor",
        sa.Column("halal_claim", claim, nullable=False, server_default="not_claimed"),
        schema=SCHEMA,
    )
    op.create_index("ix_m13_vendor_halal_claim", "vendor", ["halal_claim"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_m13_vendor_halal_claim", "vendor", schema=SCHEMA)
    op.drop_column("vendor", "halal_claim", schema=SCHEMA)
    sa.Enum(name="halal_claim", schema=SCHEMA).drop(op.get_bind(), checkfirst=True)

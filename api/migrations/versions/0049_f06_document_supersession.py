"""F6 — a credential is replaced, never overwritten

A driver renews a CDL and files the new one. The old one must not vanish: §17 Q16
forbids hard delete, and the previous card is still the answer to "what were you
carrying at that inspection in March". Destroying it would destroy evidence of a
fact that was true.

So a new document of a one-at-a-time type ARCHIVES the previous one and the previous
one points forward at its replacement. Nothing is deleted, no bytes are touched, and
the chain of what was held when stays walkable. What changes is only which document
the wallet PRODUCES — the single thing a driver or an inspector cares about.

`archived_at` is also read by the expiry engine: warning about a superseded card
would send a driver to renew something they have already renewed.

Revision ID: 0049_f06_document_supersession
Revises: 0048_m05_on_time_consent
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0049_f06_document_supersession"
down_revision: str | None = "0048_m05_on_time_consent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f06"


def upgrade() -> None:
    op.add_column(
        "document",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "document", sa.Column("superseded_by_id", sa.Uuid(), nullable=True), schema=SCHEMA
    )
    op.create_index(
        "ix_f06_document_superseded_by", "document", ["superseded_by_id"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_f06_document_superseded_by", "document", schema=SCHEMA)
    op.drop_column("document", "superseded_by_id", schema=SCHEMA)
    op.drop_column("document", "archived_at", schema=SCHEMA)

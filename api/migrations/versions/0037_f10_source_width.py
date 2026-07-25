"""F10 — widen submission.source for subject-scoped provenance

`source` held short feed names ("tpims", "eia"). A vendor's own authoritative
report is sourced as "vendor:<uuid>" (43 chars), which overflowed the 40-char
column. Provenance is the thing §11.7 relies on to say "vendor says" rather than
"N drivers", so it is widened rather than truncated.

Revision ID: 0037_f10_source_width
Revises: 0036_m13_vendor
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037_f10_source_width"
down_revision: str | None = "0036_m13_vendor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "submission",
        "source",
        type_=sa.String(80),
        existing_type=sa.String(40),
        existing_nullable=True,
        schema="f10",
    )


def downgrade() -> None:
    op.alter_column(
        "submission",
        "source",
        type_=sa.String(40),
        existing_type=sa.String(80),
        existing_nullable=True,
        schema="f10",
    )

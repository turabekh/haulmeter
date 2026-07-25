"""F14 — audit timestamps use clock_timestamp(), not now()

In PostgreSQL `now()` is the TRANSACTION start time. Several audit entries written
in one transaction therefore shared a timestamp, which made "who touched this last"
non-deterministic — the single question an audit log exists to answer. It also made
`created_at` mean "when the transaction began" rather than "when this happened",
which is not what an auditor means by "when".

`clock_timestamp()` is the real moment each row is written.

Revision ID: 0041_f14_audit_clock
Revises: 0040_m13_report_guards
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041_f14_audit_clock"
down_revision: str | None = "0040_m13_report_guards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "admin_action",
        "created_at",
        server_default=sa.text("clock_timestamp()"),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        schema="f14",
    )


def downgrade() -> None:
    op.alter_column(
        "admin_action",
        "created_at",
        server_default=sa.text("now()"),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        schema="f14",
    )

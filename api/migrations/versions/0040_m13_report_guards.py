"""M13 Q-8 — moderation integrity guards (Admin Console 2.0 decision 4)

Closes the report-abuse gap: a report is now recorded even when it carries no
automatic weight, and the reason it carries none is on the row.

`self_reported` marks a report filed by the vendor's own owner or a member — kept
on file so a moderator can SEE the attempted self-takedown, excluded from the
distinct-driver hide count so it cannot cause one.

`frivolous` is a moderator's third verdict: the report itself was the abuse. It
counts toward the REPORTER's record, because a moderator who can only ever
penalise the reported party makes the report button a free weapon.

Revision ID: 0040_m13_report_guards
Revises: 0039_f14_audit_and_jobs
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040_m13_report_guards"
down_revision: str | None = "0039_f14_audit_and_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "m13"


def upgrade() -> None:
    op.add_column(
        "content_report",
        sa.Column("frivolous", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema=SCHEMA,
    )
    op.add_column(
        "content_report",
        sa.Column("self_reported", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema=SCHEMA,
    )
    op.create_index("ix_m13_report_frivolous", "content_report", ["frivolous"], schema=SCHEMA)
    op.create_index(
        "ix_m13_report_self_reported", "content_report", ["self_reported"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_m13_report_self_reported", "content_report", schema=SCHEMA)
    op.drop_index("ix_m13_report_frivolous", "content_report", schema=SCHEMA)
    op.drop_column("content_report", "self_reported", schema=SCHEMA)
    op.drop_column("content_report", "frivolous", schema=SCHEMA)

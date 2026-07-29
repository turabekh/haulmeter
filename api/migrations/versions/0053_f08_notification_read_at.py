"""F8 — when the driver actually read a notification

F8 has decided tiers, budgets, quiet hours and classes since it shipped, and every
decision it made ended in a row nobody could read. There is no notification endpoint
in the API, no service worker or push registration in the client, and the only gateway
wired anywhere in application code is the RECORDING one used by tests. §23 entry 429
found the same shape in miniature — "nothing may be filed P2 until a surface renders
the digest" — and the general case is larger: nothing was rendering ANY of it.

An inbox needs one fact the table never stored: whether the driver has seen the thing.
`status` cannot carry it. It records what the SYSTEM did — sent, suppressed, digested —
and a notification that was pushed at 3 a.m. and never opened is `sent` either way.
Delivery and attention are different events, and a column that conflated them would
make "unread" mean "undelivered" the first time someone reasoned about it.

Existing rows are left NULL, which reads as unread. That is the honest default: nobody
has opened them, because until this migration there was nothing to open them with.

Revision ID: 0053_f08_notification_read_at
Revises: 0052_m03_claim_clock_since
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0053_f08_notification_read_at"
down_revision: str | None = "0052_m03_claim_clock_since"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f08"


def upgrade() -> None:
    op.add_column(
        "notification",
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("notification", "read_at", schema=SCHEMA)

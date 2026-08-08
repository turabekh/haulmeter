"""AI-CONTEXT: outbound mail stops claiming deliveries it did not get (audit F-06).

`send_counterparty_message` wrote `sent_at` unconditionally, beside a provider ref that
might say `smtp-failed-…`. Nothing anywhere read that ref, so a failed send left a row
asserting delivery — the same shape as U-07's queue reporting "synced" over a dropped
write, and F-01's F8 row claiming a notice was sent. With A12's "no monitoring" nothing
would ever have surfaced it.

`sent_at` NULL now means it has not gone out, which is what makes the unsent ones
findable. `attempts` bounds the retry so a permanently undeliverable address cannot be
tried forever. `to_ref` is the address it was sent to — which the database did not record
anywhere, so it could say a notice was sent and not say to whom.

BACKFILL, and why it is the shape it is. Existing rows all have `sent_at` set and no
`to_ref`, and there is no way to tell which of them actually went out — the information
was never kept. They are left exactly as they are: `attempts` 1, `to_ref` NULL. Rewriting
history from a guess would be inventing the fact this migration exists to stop inventing.
`retry_unsent_messages` skips a row with no `to_ref` and counts it rather than guessing an
address for a broker's detention notice.
"""

import sqlalchemy as sa
from alembic import op

revision = "0064_f08_outbound_delivery"
down_revision = "0063_f02_facility_timezone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "outbound_message",
        sa.Column("to_ref", sa.String(length=320), nullable=True),
        schema="f08",
    )
    op.add_column(
        "outbound_message",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        schema="f08",
    )
    # every existing row was written with sent_at set, so it has had its one attempt
    op.execute("UPDATE f08.outbound_message SET attempts = 1 WHERE sent_at IS NOT NULL")
    # the retry sweep reads exactly this predicate
    op.create_index(
        "ix_outbound_message_unsent",
        "outbound_message",
        ["sent_at", "attempts"],
        schema="f08",
    )


def downgrade() -> None:
    op.drop_index("ix_outbound_message_unsent", table_name="outbound_message", schema="f08")
    op.drop_column("outbound_message", "attempts", schema="f08")
    op.drop_column("outbound_message", "to_ref", schema="f08")

"""AI-CONTEXT: one email per purpose, enforced by Postgres rather than by remembering.

Duplicate suppression for counterparty mail was five ad-hoc guards spread across four
modules: `start_notice_message_ref` on a claim, `pre_notice_sent_at` beside it, a packet
state, per-action dunning columns — and on two send paths, nothing at all. Every one was
written for its own case, which is precisely how the same defect kept coming back: §23
entry 136 found `onSendNotice` "genuinely sent a broker two emails on a double tap", and
moving sends off the request thread re-opened it in `_existing_start_notice`, where a
never-attempted row did not look like an existing notice.

WHY THE CONSTRAINT AND NOT A CHECK. §23 closed the four money races on exactly this
reasoning: **an application check reads rows a concurrent transaction has not committed
yet.** Two taps landing together, or a request racing the offline queue's replay, both
pass a `SELECT ... WHERE dedupe_key = ?` and both insert. The index is what makes the
second one impossible; the application lookup above it is only the fast path that turns an
error into a returned row.

PARTIAL, on `dedupe_key IS NOT NULL`. Postgres already treats NULLs as distinct in a
unique index, so the WHERE clause is not what permits un-keyed rows — it keeps the index
off the millions of rows that will never carry a key, which is the only kind of message
this table held until today.

NOTHING IS BACKFILLED, and giving existing rows keys would be wrong. A key means "this
purpose has been served"; stamping one onto historical rows would silently make a future
send for that purpose a no-op, which is the opposite of the guarantee. Every existing row
stays NULL and every future send is keyed by its caller.

THIS MIGRATION CAN FAIL, and that is deliberate. If two rows somehow already shared a key
the index would refuse to build — there are none today because the column is new, but the
same statement re-run after a partial rollout must not silently drop one of them.
"""

import sqlalchemy as sa
from alembic import op

revision = "0073_outbound_dedupe_key"
down_revision = "0072_on_time_notice_ref"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "outbound_message",
        sa.Column("dedupe_key", sa.String(length=200), nullable=True),
        schema="f08",
    )
    op.create_index(
        "uq_f08_outbound_message_dedupe_key",
        "outbound_message",
        ["dedupe_key"],
        unique=True,
        schema="f08",
        postgresql_where=sa.text("dedupe_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_f08_outbound_message_dedupe_key",
        table_name="outbound_message",
        schema="f08",
    )
    op.drop_column("outbound_message", "dedupe_key", schema="f08")

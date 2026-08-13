"""AI-CONTEXT: driver push leaves the request thread, and takes its tray buttons with it.

`dispatch` called `gateway.send_push` inline — a POST per subscription with a ten-second
timeout, once for every browser a driver has, inside the request handler and holding a
pooled database connection on a third party. §23 records that exact outage: "QueuePool
limit of size 5 overflow 10 reached", the API out of connections and answering nothing.

THREE THINGS, and the last two are what a careless version of this change would have
broken silently.

`queued` is a new `notification_status`: DECIDED to interrupt the driver, not yet handed
to a push service. `sent` keeps its meaning exactly — the push service accepted it — and
`dispatched_at` still records that moment rather than the decision.

`actions` is the tray's buttons, and they were never persisted. They arrived as a
parameter and went straight to the gateway, so deferring the send would have dropped them
silently. The one notification that uses them is the lot-status prompt, whose own comment
says "the answer must be one tap from a LOCKED phone or it is a task, not a confirmation".
Losing them would not have failed anything; it would have turned a confirmation into a
chore, which is precisely the failure that comment exists to prevent.

`decided_at` is WHEN WE DECIDED TO INTERRUPT, and §13.1's interruption budget is counted
on it now. That is a real change to how a design-prd law is measured, and it was forced:
the budget counted `status = sent AND dispatched_at >= now - 24h`, and a queued
notification satisfies neither — so deferring delivery would have silently disabled the
two-a-day budget and every per-class daily cap, letting a burst inside one sweep window
through. `created_at` cannot serve, because it is a server default that ignores the `now`
a caller passes, which would make the budget wrong for any job replaying on a historical
clock.

IT IS BACKFILLED FROM `dispatched_at`, and that matters more than it looks. Without it
every historical row would have a NULL `decided_at`, so the 24-hour window would read
empty the moment this deploys and drivers could be nagged freely for the first hours. For
rows written before today the two instants are identical: the send was synchronous, so
the decision and the handoff happened in the same statement.
"""

import sqlalchemy as sa
from alembic import op

revision = "0075_notification_queued"
down_revision = "0074_drop_stale_mail_schedule"
branch_labels = None
depends_on = None

SCHEMA = "f08"
ENUM = "notification_status"


def upgrade() -> None:
    # ADD VALUE is not transactional on older servers; IF NOT EXISTS keeps a re-run safe.
    # Same shape as 0070's `discarded`.
    op.execute(sa.text(f"ALTER TYPE {SCHEMA}.{ENUM} ADD VALUE IF NOT EXISTS 'queued'"))
    op.add_column(
        "notification",
        sa.Column("actions", sa.JSON(), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "notification",
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_f08_notification_decided_at"),
        "notification",
        ["decided_at"],
        unique=False,
        schema=SCHEMA,
    )
    # AI-CONTEXT: BACKFILLED from `dispatched_at`, and this one matters. §13.1's budget is
    # counted on `decided_at` now, so leaving it NULL for every historical row would empty
    # the 24-hour window the moment this deploys — every driver's cap would read zero used
    # and the first hours after the deploy could nag them freely. For rows written before
    # today the two instants are the same: the send was synchronous, so the decision and
    # the handoff happened in the same statement.
    op.execute(
        sa.text(
            f"UPDATE {SCHEMA}.notification SET decided_at = dispatched_at "
            "WHERE decided_at IS NULL AND dispatched_at IS NOT NULL"
        )
    )


def downgrade() -> None:
    # AI-CONTEXT: POSTGRES CANNOT DROP AN ENUM VALUE, so this rebuilds the type rather
    # than pretending — the same approach 0070 takes, and for the same reason.
    #
    # It REFUSES if any row is actually `queued`. Rewriting those to `sent` would claim a
    # delivery that never happened (audit F-06's exact defect); rewriting them to
    # `suppressed` would claim a decision nobody made. A downgrade that has to lie about
    # what a driver was told should stop and say so.
    conn = op.get_bind()
    stuck = conn.execute(
        sa.text(f"SELECT count(*) FROM {SCHEMA}.notification WHERE status = 'queued'")
    ).scalar()
    if stuck:
        raise RuntimeError(
            f"{stuck} notification(s) are queued for delivery; run the push_delivery "
            "sweep until it reports none before downgrading"
        )

    # AI-CONTEXT: IF EXISTS on both, because this migration was applied once in an earlier
    # shape (before `decided_at` existed) and a downgrade that assumes its own final form
    # cannot unwind that. A downgrade is the path taken when something has already gone
    # differently than planned; it is the wrong place to be strict about what it finds.
    op.execute(sa.text(f"DROP INDEX IF EXISTS {SCHEMA}.ix_f08_notification_decided_at"))
    op.execute(sa.text(f"ALTER TABLE {SCHEMA}.notification DROP COLUMN IF EXISTS decided_at"))
    op.execute(sa.text(f"ALTER TABLE {SCHEMA}.notification DROP COLUMN IF EXISTS actions"))
    # AI-CONTEXT: the DEFAULT has to come off first. `status` carries
    # `'pending'::f08.notification_status`, and Postgres refuses to re-type a column whose
    # default is expressed in the type being replaced — "default for column status cannot
    # be cast automatically". Dropped here and restored after the swap; without this the
    # downgrade fails halfway, having already renamed the type.
    op.execute(sa.text(f"ALTER TABLE {SCHEMA}.notification ALTER COLUMN status DROP DEFAULT"))
    op.execute(sa.text(f"ALTER TYPE {SCHEMA}.{ENUM} RENAME TO {ENUM}_old"))
    op.execute(
        sa.text(
            f"CREATE TYPE {SCHEMA}.{ENUM} AS ENUM "
            "('pending', 'sent', 'suppressed', 'digested')"
        )
    )
    op.execute(
        sa.text(
            f"ALTER TABLE {SCHEMA}.notification ALTER COLUMN status TYPE {SCHEMA}.{ENUM} "
            f"USING status::text::{SCHEMA}.{ENUM}"
        )
    )
    op.execute(
        sa.text(
            f"ALTER TABLE {SCHEMA}.notification ALTER COLUMN status "
            f"SET DEFAULT 'pending'::{SCHEMA}.{ENUM}"
        )
    )
    op.execute(sa.text(f"DROP TYPE {SCHEMA}.{ENUM}_old"))

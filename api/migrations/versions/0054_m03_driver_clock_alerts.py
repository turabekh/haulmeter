"""M3 — the driver's own detention alerts, recorded separately from the broker's

design-prd §13.2 names "detention started" as the FIRST of its three P0 examples, and
nothing in this product had ever dispatched a P0: `notify.dispatch` was called from
five sites in two modules, all P1, and M3 did not call it at all. §23 entry 106 settled
which instant the notification means — free-time expiry, the `within_free_time ->
accruing` boundary `compute_detention` already computes — and these two columns are
what make firing it exactly once possible.

They are separate from `start_notice_sent_at`, which records the COUNTERPARTY notice.
Two audiences, two records: the broker's email and the driver's push come from
different code paths at different moments, and one column would have made "the driver
knows" mean "the broker was told".

The partial index serves the worker's scan directly. A claim drops out of the index the
moment both alerts have been sent, so the set it walks is the genuinely undecided one
rather than every claim ever filed.

Existing rows are left NULL — an alert that was never sent has no timestamp to invent,
and backfilling `now` would silently mark every open claim as already told.

Revision ID: 0054_m03_driver_clock_alerts
Revises: 0053_f08_notification_read_at
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0054_m03_driver_clock_alerts"
down_revision: str | None = "0053_f08_notification_read_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "m03"
PENDING_INDEX = "ix_detention_claim_pending_alerts"


def upgrade() -> None:
    op.add_column(
        "detention_claim",
        sa.Column("driver_start_alert_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "detention_claim",
        sa.Column("driver_warning_alert_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.execute(
        f"CREATE INDEX {PENDING_INDEX} ON {SCHEMA}.detention_claim (state) "
        "WHERE driver_start_alert_at IS NULL OR driver_warning_alert_at IS NULL"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {SCHEMA}.{PENDING_INDEX}")
    op.drop_column("detention_claim", "driver_warning_alert_at", schema=SCHEMA)
    op.drop_column("detention_claim", "driver_start_alert_at", schema=SCHEMA)

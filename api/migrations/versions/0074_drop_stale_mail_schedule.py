"""AI-CONTEXT: retire the schedule row for a job that no longer exists.

`outbound_retry` was renamed `outbound_mail` when it stopped being a net beside an inline
send and became the only thing that sends counterparty email. `f14.job_schedule` is keyed
by job NAME and `_ensure_schedule` creates a row on first claim, so the new name made its
own row and the old one was left behind — never claimed by anything, `next_run_at` frozen
in the past, and visible to `job_schedules()` and the admin console.

It is one stale row and it costs nothing to run. What it costs is READING: an operator
looking for a stuck job finds one that has not moved in weeks and cannot be moved, because
no code answers to that name any more. That is the same class of thing as a flag nobody
registered or an export nobody imports — a mechanism that looks live and is not.

DONE AS A MIGRATION rather than by hand on the box, because every environment that ran the
old name has the row: dev, the deployed VM, and any future restore from a backup taken
before the rename. A hand-edit fixes one of them and leaves the rest to be rediscovered.

`job_run` HISTORY IS DELIBERATELY KEPT. Those rows record attempts that genuinely happened
under that name, and rewriting them would be editing the operational record to match a
rename. The schedule is a pointer to future work; the runs are history.
"""

import sqlalchemy as sa
from alembic import op

# AI-CONTEXT: kept short on purpose. `alembic_version.version_num` is varchar(32) and the
# first spelling of this id was 38 characters — the upgrade applied its DELETE and then
# failed writing its own version row, which is the worst place for a migration to stop.
revision = "0074_drop_stale_mail_schedule"
down_revision = "0073_outbound_dedupe_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("DELETE FROM f14.job_schedule WHERE job_name = 'outbound_retry'"))


def downgrade() -> None:
    # AI-CONTEXT: nothing. Re-creating the row would resurrect a schedule for a job that
    # does not exist in any version of this code — a downgrade restores the SCHEMA, and
    # `_ensure_schedule` writes whatever row the running worker actually needs on its next
    # claim. Inventing one here would put back exactly the confusion this removed.
    pass

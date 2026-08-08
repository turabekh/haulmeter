"""AI-CONTEXT: the worker's schedule moves into the database (audit F-10).

`Job.next_run` and `Job.failures` were fields on an in-memory dataclass keyed off
`time.monotonic()`. Two consequences, both the audit's:

· Two worker containers both run every job. Compose runs one replica, but a rolling
  restart briefly has two — and `document_expiry` sends F8 notifications, so the
  duplicate is a driver's phone, not a wasted upsert.
· Every restart reset `next_run` to 0.0, so all jobs fired at once on boot.

`f14.job_run` could not carry this. It is one row per ATTEMPT and its own docstring
says why it must not be bent into schedule state: it records history, so it cannot
stop a second worker from starting a run it has no row for yet.

NO BACKFILL, and that is deliberate rather than an omission. An empty table means
every job is claimable on the next tick, which is precisely today's behaviour — so
the deploy that applies this changes nothing about when jobs run, and `_seed_schedule`
writes each row the first time the worker boots. Seeding rows here would have to
invent a `next_run_at` for jobs whose real schedule lives in a process that is about
to be replaced.
"""

import sqlalchemy as sa
from alembic import op

revision = "0065_f14_job_schedule"
down_revision = "0064_f08_outbound_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_schedule",
        sa.Column("job_name", sa.String(length=60), primary_key=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=120), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        schema="f14",
    )
    # the claim's WHERE clause reads exactly this
    op.create_index(
        "ix_job_schedule_next_run_at",
        "job_schedule",
        ["next_run_at"],
        schema="f14",
    )


def downgrade() -> None:
    op.drop_index("ix_job_schedule_next_run_at", table_name="job_schedule", schema="f14")
    op.drop_table("job_schedule", schema="f14")

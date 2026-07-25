"""F14 — audit before/after + target_key, and worker job telemetry

Two gaps the Admin Console 2.0 rework exposed:

1. The audit log recorded THAT something changed but not what it changed FROM,
   and `target_ref` was declared but never populated by any call site — so the log
   could not be filtered to one subject. `before`/`after` and a string `target_key`
   (flag keys and config keys are not UUIDs) close both.
2. Worker jobs logged to stdout only, so "did the feeds run, and is anything
   stuck?" could only be answered by reading container logs. `job_run` records one
   row per ATTEMPT, so a failure streak is history rather than an inferred counter.

Revision ID: 0039_f14_audit_and_jobs
Revises: 0038_m13_session_b
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039_f14_audit_and_jobs"
down_revision: str | None = "0038_m13_session_b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f14"


def upgrade() -> None:
    op.add_column(
        "admin_action", sa.Column("target_key", sa.String(120), nullable=True), schema=SCHEMA
    )
    op.add_column("admin_action", sa.Column("before", sa.JSON(), nullable=True), schema=SCHEMA)
    op.add_column("admin_action", sa.Column("after", sa.JSON(), nullable=True), schema=SCHEMA)
    op.create_index("ix_f14_action_target_key", "admin_action", ["target_key"], schema=SCHEMA)
    op.create_index("ix_f14_action_target_ref", "admin_action", ["target_ref"], schema=SCHEMA)
    op.create_index("ix_f14_action_created_at", "admin_action", ["created_at"], schema=SCHEMA)

    op.create_table(
        "job_run",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("job_name", sa.String(60), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("summary", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    for column in ("job_name", "started_at", "ok"):
        op.create_index(f"ix_f14_job_run_{column}", "job_run", [column], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("job_run", schema=SCHEMA)
    op.drop_index("ix_f14_action_created_at", "admin_action", schema=SCHEMA)
    op.drop_index("ix_f14_action_target_ref", "admin_action", schema=SCHEMA)
    op.drop_index("ix_f14_action_target_key", "admin_action", schema=SCHEMA)
    for column in ("after", "before", "target_key"):
        op.drop_column("admin_action", column, schema=SCHEMA)

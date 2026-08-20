"""f01: record SUCCESSFUL sign-ins, so an operator can answer who, when and from where.

AI-CONTEXT: §23 entry 234. `f01.login_attempt` looks like a login history and is a
THROTTLE — failures only, pruned on every write, and cleared the moment a driver gets in.
Production held ONE row against 236 live sessions, so an admin screen built on it would
have been confidently and permanently empty. This table records the successes instead.

Bounded on write by `LOGIN_EVENT_RETENTION_DAYS`: this is personal data about drivers and
an unbounded PII table is a liability that grows on its own.

Revision ID: 0095_f01_login_event
"""

import sqlalchemy as sa
from alembic import op

revision = "0095_f01_login_event"
down_revision = "0094_f03_attested_presence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_event",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("f01.account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        schema="f01",
    )
    op.create_index("ix_f01_login_event_account_id", "login_event", ["account_id"], schema="f01")
    op.create_index("ix_f01_login_event_kind", "login_event", ["kind"], schema="f01")
    op.create_index("ix_f01_login_event_occurred_at", "login_event", ["occurred_at"], schema="f01")


def downgrade() -> None:
    op.drop_index("ix_f01_login_event_occurred_at", "login_event", schema="f01")
    op.drop_index("ix_f01_login_event_kind", "login_event", schema="f01")
    op.drop_index("ix_f01_login_event_account_id", "login_event", schema="f01")
    op.drop_table("login_event", schema="f01")

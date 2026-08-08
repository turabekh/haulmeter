"""AI-CONTEXT: the failed-login table behind F1's authentication throttle (audit F-07).

There was no limiter, no lockout and no attempt counter anywhere in the application, on
a live product with real driver accounts, one VM, and no monitoring.

In Postgres rather than Redis on purpose: `core/events.py` establishes that Redis here
is not a system of record and degrades silently, which is correct for a live channel and
wrong for a security control — a throttle that vanishes when Redis is unreachable fails
OPEN and nothing would say so.

Only failures are stored, a success clears the identifier's rows, and rows older than
the window are deleted on every write, so the table stays proportional to the attack
rather than growing forever.
"""

import sqlalchemy as sa
from alembic import op

revision = "0061_f01_login_attempt"
down_revision = "0060_money_race_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_attempt",
        sa.Column("id", sa.Uuid(), primary_key=True),
        # the SUBMITTED address, normalised, recorded whether or not an account exists —
        # counting only real accounts would make the throttle an existence oracle
        sa.Column("identifier", sa.String(length=320), nullable=False),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema="f01",
    )
    # both reads are "how many in the last N seconds", so both indexes lead with the
    # dimension and carry the time
    op.create_index(
        "ix_login_attempt_identifier_time",
        "login_attempt",
        ["identifier", "occurred_at"],
        schema="f01",
    )
    op.create_index(
        "ix_login_attempt_ip_time",
        "login_attempt",
        ["client_ip", "occurred_at"],
        schema="f01",
    )


def downgrade() -> None:
    op.drop_index("ix_login_attempt_ip_time", table_name="login_attempt", schema="f01")
    op.drop_index("ix_login_attempt_identifier_time", table_name="login_attempt", schema="f01")
    op.drop_table("login_attempt", schema="f01")

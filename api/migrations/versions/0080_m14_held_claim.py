"""AI-CONTEXT: the queue a fleet admin works (M14-FR4, E2 slice 1).

`claim_ref` IS NOT A FOREIGN KEY, and that is deliberate rather than an oversight. m14
sits above m03 in the import spine, and a database-level dependency pointing down would
outlive any import-linter contract — the constraint would still be there long after
somebody moved the Python. The uniqueness that matters is enforced here; the referential
relationship is M14's business to keep.

`uq_held_claim_claim` is the load-bearing one. A poll every 60 s re-reads an overlapping
window, so the same stop can be reached repeatedly; without this a fleet admin would be
shown one detention several times and approve it several times, and `generate_pack`'s
state guard is the only thing between that and several invoices to one broker. Making it
a database fact rather than a loop invariant is migration 0077's lesson, two migrations
old: a thing that exists once should be unique in Postgres.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0080_m14_held_claim"
down_revision = "0079_m14_recovery"
branch_labels = None
depends_on = None

SCHEMA = "m14"


def upgrade() -> None:
    # created explicitly, then referenced with `create_type=False` — a bare `sa.Enum`
    # inside `create_table` emits its own CREATE TYPE and the second one fails
    # (migration 0057's note; 0079 re-learned it this session)
    sa.Enum("held", "approved", "sent", "rejected", name="hold_state", schema=SCHEMA).create(
        op.get_bind(), checkfirst=True
    )
    hold_state = postgresql.ENUM(name="hold_state", schema=SCHEMA, create_type=False)

    op.create_table(
        "held_claim",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("fleet_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("claim_ref", sa.Uuid(), nullable=False, index=True),
        sa.Column("stop_ref", sa.Uuid(), nullable=False, index=True),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("f01.account.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "evidence_class", sa.String(length=20), nullable=False, server_default="eld_derived"
        ),
        sa.Column("state", hold_state, nullable=False, server_default="held"),
        sa.Column(
            "decided_by", sa.Uuid(), sa.ForeignKey("f01.account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        # which gate refused the send, so a screen can say WHY rather than going quiet
        sa.Column("send_blocked_by", sa.String(length=60), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("claim_ref", name="uq_held_claim_claim"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("held_claim", schema=SCHEMA)
    sa.Enum(name="hold_state", schema=SCHEMA).drop(op.get_bind(), checkfirst=True)

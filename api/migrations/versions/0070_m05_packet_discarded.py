"""AI-CONTEXT: a driver may decline paperwork (owner request, 2026-08-11).

`stop_packet_state` had two values and the review step had one exit. A packet the driver
did not want to send stayed on the Load tab indefinitely, and the only control that could
clear it was Send — so the app's answer to "I don't need to send this" was to send it.

WHY A THIRD STATE RATHER THAN A DELETE. The row is the record that a stop produced
paperwork and what the driver decided about it. Deleting it would make a declined packet
indistinguishable from a stop that never drafted one, and `draft_stop_packet` is
get-or-create on a uniquely-constrained `stop_ref` — so a deleted row would be re-drafted
by the next EXIT at that dock and the decision would silently un-happen.

NOTHING IS BACKFILLED and nothing needs to be: every existing row is `draft` or `sent`,
both of which keep their exact meaning. The new value is unreachable until a driver taps
the control this migration exists to support.

POSTGRES CANNOT DROP AN ENUM VALUE, which is why `downgrade` rebuilds the type rather
than pretending. It refuses if any row is actually `discarded` instead of silently
rewriting a driver's decision into `draft` and putting declined paperwork back in a
queue — the same refusing pre-check 0067 and 0068 use, and for the same reason.
"""

import sqlalchemy as sa
from alembic import op

revision = "0070_m05_packet_discarded"
down_revision = "0069_f01_attempt_kind"
branch_labels = None
depends_on = None

SCHEMA = "m05"
TABLE = "stop_packet"
ENUM = "stop_packet_state"


def upgrade() -> None:
    # ADD VALUE is not transactional on older servers; IF NOT EXISTS keeps a re-run safe.
    op.execute(sa.text(f"ALTER TYPE {SCHEMA}.{ENUM} ADD VALUE IF NOT EXISTS 'discarded'"))
    # its own timestamp, beside `sent_at` rather than sharing it: "the driver declined
    # this" and "this reached a dispatcher" are different facts about different acts.
    op.add_column(
        TABLE,
        sa.Column("discarded_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    conn = op.get_bind()
    stuck = conn.execute(
        sa.text(f"SELECT count(*) FROM {SCHEMA}.{TABLE} WHERE state = 'discarded'")
    ).scalar_one()
    if stuck:
        raise RuntimeError(
            f"{stuck} stop packet(s) are 'discarded'. Downgrading would rewrite a "
            "driver's decision not to send paperwork and return it to their queue. "
            "Resolve those rows deliberately before downgrading."
        )
    op.drop_column(TABLE, "discarded_at", schema=SCHEMA)
    op.execute(sa.text(f"ALTER TYPE {SCHEMA}.{ENUM} RENAME TO {ENUM}_old"))
    op.execute(sa.text(f"CREATE TYPE {SCHEMA}.{ENUM} AS ENUM ('draft', 'sent')"))
    op.execute(
        sa.text(
            f"ALTER TABLE {SCHEMA}.{TABLE} ALTER COLUMN state "
            f"TYPE {SCHEMA}.{ENUM} USING state::text::{SCHEMA}.{ENUM}"
        )
    )
    op.execute(sa.text(f"DROP TYPE {SCHEMA}.{ENUM}_old"))

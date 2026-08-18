"""AI-CONTEXT: the scoring rubric stops standing in the middle of the conversation.

MEASURED ON THE BOX, which is the only reason this exists. A full exchange cost ~5.5s from
the moment a driver stopped speaking to the moment the officer spoke again, and the legs
were: STT 0.32s, **scoring rubric 3.41s**, echo synthesis 0.25s, the officer's own line
1.24s, his voice 0.25s. The rubric was the single largest cost in a spoken conversation —
and it decides what a driver is told about their English ON THE RESULT SCREEN, at the end.
Nobody was waiting for it. Every driver was.

WHY A COLUMN AND NOT AN ABSENT SCORE. `scores = {}` already MEANS something in this module
and means it deliberately: Q-2's law is that a turn we could not hear, or that was not an
attempt at an answer, carries no scores at all so it is excluded from the band rather than
dragging it down. NO_RESPONSE, the ASR floor and REPETITION_REQUIRED all return exactly
that. If "not scored yet" were also `{}`, then a turn still queued and a turn deliberately
excluded would be indistinguishable — and the band would be computed over whichever ones
happened to have finished. That is a wrong number quietly presented as a right one, which
is the failure this codebase keeps paying for.

`scoring_state` says which it is, out loud:
  · `not_required` — Q-2 decided this turn carries no scores. Terminal, correct, done.
  · `pending`      — the rubric has not run yet. NOT a verdict about anything.
  · `done`         — the rubric ran and the scores are real.

WHAT GUARANTEES A DRIVER NEVER SEES A HALF-SCORED RESULT: the result endpoint settles any
`pending` turns for that session before it computes a band. The worker sweep is the fast
path, not the correctness path — so a worker that is down makes the result screen slower,
never wrong. A driver waits once, at the end, where waiting is what you do anyway.
"""

import sqlalchemy as sa
from alembic import op

revision = "0091_m15_deferred_scoring"
down_revision = "0090_m15_repair_echo"
branch_labels = None
depends_on = None

SCHEMA = "m15"


def upgrade() -> None:
    # server_default `done` rather than `pending`: every turn that already exists WAS
    # scored inline, and defaulting them to pending would enqueue the entire history of
    # every session for a rubric pass that has already happened.
    op.add_column(
        "turn",
        sa.Column("scoring_state", sa.String(16), nullable=False, server_default="done"),
        schema=SCHEMA,
    )
    # the sweep's only query: pending turns, oldest first. Partial, because `done` is
    # almost every row and an index over all of them would be read by nothing.
    op.create_index(
        "ix_turn_scoring_pending",
        "turn",
        ["session_id"],
        schema=SCHEMA,
        postgresql_where=sa.text("scoring_state = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("ix_turn_scoring_pending", table_name="turn", schema=SCHEMA)
    op.drop_column("turn", "scoring_state", schema=SCHEMA)

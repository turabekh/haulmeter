"""AI-CONTEXT: the scenario's hidden state gets a column (M15-FR2).

E3 §E3.1.2 is explicit: "A `scenario_version` carries hidden state (driver name, carrier,
origin, destination, cargo, HOS numbers, trailer) **from which questions and expected
answers derive**." §E3.1.4's table list does not include a column for it — a gap between
the requirement and the data model, found by running a real session rather than by reading
either document.

WHAT THE GAP COST, because it is the good kind of bug: the probe spoke "I have been
driving six hours today" through Azure, Deepgram heard it perfectly at confidence 1.000,
and the driver was scored `answer_completeness: 0`. `expected_slots` had been filled from
`intent.required_slots`, whose values are the string "required" — so the validator was
checking whether the driver had said the word "required". A green suite had no opinion
about this, because every test supplied its own expected slots directly.

Nullable and defaulting to `{}`: existing rows carry no hidden state and are none the
worse, and a scenario without it simply has no facts to check against.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0087_m15_hidden"
down_revision = "0086_f06_retention"
branch_labels = None
depends_on = None

SCHEMA = "m15"


def upgrade() -> None:
    op.add_column(
        "scenario_version",
        sa.Column("hidden_state", postgresql.JSONB(), nullable=False, server_default="{}"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("scenario_version", "hidden_state", schema=SCHEMA)

"""AI-CONTEXT: the two additive foundation columns M14 slice 1 needs (PRD Extension E2, D8).

Both are BACKFILLED TO WHAT IS ALREADY TRUE, so no box changes behaviour on apply — the
0066 discipline. That is not a formality here, it is the whole safety argument:

  · `f03.location_ping.source` → `device`. Every ping in every database was produced by a
    driver's phone, so `device` is a statement of fact about existing rows rather than an
    assumption about them.
  · `f04.shared_pack.evidence_class` → `phone_verified`. Same reasoning, and it matters
    more: this column is what a pack PRINTS to a counterparty. A wrong default here would
    make an existing pack claim a basis it does not have, which is the exact §11.7 failure
    M14-FR3 exists to prevent.

WHY `String` AND NOT AN ENUM, on both. `source` carries `eld:<provider>` and
`evidence_class` is M14's vocabulary; making either an enum would mean a migration on a
FOUNDATION table every time a provider is added — and rebuilding an enum needs the column
DEFAULT dropped first (HANDOFF-125 §4.9), which is a sharp edge to hand a future session
for no gain. The values are validated where they are produced, in `m14`.

NOT NULLABLE, with a server default. A nullable column would make "we do not know what
produced this" representable, and it is not: every row has a source, we simply had not
been writing it down.
"""

import sqlalchemy as sa
from alembic import op

revision = "0078_evidence_class_source"
down_revision = "0077_settlement_period_uniq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "location_ping",
        sa.Column(
            "source",
            sa.String(length=40),
            nullable=False,
            server_default="device",
        ),
        schema="f03",
    )
    op.add_column(
        "shared_pack",
        sa.Column(
            "evidence_class",
            sa.String(length=20),
            nullable=False,
            server_default="phone_verified",
        ),
        schema="f04",
    )


def downgrade() -> None:
    op.drop_column("shared_pack", "evidence_class", schema="f04")
    op.drop_column("location_ping", "source", schema="f03")

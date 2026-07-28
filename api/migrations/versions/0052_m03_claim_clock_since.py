"""M3 — the moment a claim began watching, stored rather than inferred

A detention claim's clock was reconstructed by replaying every geofence event ever
recorded for the account at that facility and taking the earliest ENTER and the latest
EXIT. Any earlier visit to the same dock therefore became the start of this claim's
clock. Measured on a real two-stop load: a delivery the driver stood at for 53 seconds
billed 2h20m — $187.76 against $0.00 actually owed — because an ENTER from an earlier
run that afternoon was still the earliest one on file.

F3 has always recorded visits properly, one presence session per arrival. To ask it
which session belongs to THIS claim, the claim has to say when it started watching.
`created_at` is row metadata and could not carry that: it is a server default, absent
on the in-session object, and not something a caller may state. `clock_since` is the
anchor the money depends on, so it is explicit, stored, and printable on the invoice
beside the arrival and departure it bounds.

Existing rows are backfilled from `created_at` — the best available statement of when
watching began, and identical to it for every claim the application has ever made.

Revision ID: 0052_m03_claim_clock_since
Revises: 0051_f05_stop_appointment_source
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0052_m03_claim_clock_since"
down_revision: str | None = "0051_f05_stop_appointment_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "m03"


def upgrade() -> None:
    op.add_column(
        "detention_claim",
        sa.Column("clock_since", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.execute(f"UPDATE {SCHEMA}.detention_claim SET clock_since = created_at")


def downgrade() -> None:
    op.drop_column("detention_claim", "clock_since", schema=SCHEMA)

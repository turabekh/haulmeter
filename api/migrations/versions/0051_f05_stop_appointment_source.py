"""F5 — where a STOP's appointment came from, rather than where its load did

M5-FR1 shows the appointment window before arrival with its provenance, because a
machine read of a photographed contract and a value a driver typed carry different
confidence and only the driver knows which is right. The Meter has been reporting that
provenance from `load.source` — how the LOAD was created — which is a different fact
about a different object, and it was wrong in both directions:

  · A load imported from a rate con reported "Read from your rate con" for its
    appointment even though the confirm sheet never sent one, so the value was null and
    the claim described nothing.
  · Correcting a mis-parsed appointment could not change the claim, so the screen would
    go on crediting the parse for a time the driver typed.

The provenance belongs to the appointment. Existing rows are backfilled from the load
they belong to, which is the best available statement of how they got their value and
exactly what the Meter was already reporting — so no screen changes meaning for a load
that already exists.

Revision ID: 0051_f05_stop_appointment_source
Revises: 0050_f06_document_archive_reason
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0051_f05_stop_appointment_source"
down_revision: str | None = "0050_f06_document_archive_reason"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f05"


def upgrade() -> None:
    op.add_column(
        "stop",
        sa.Column("appointment_source", sa.String(length=20), nullable=True),
        schema=SCHEMA,
    )
    # backfill from the owning load: it is what the Meter reported for these rows
    # already, so nothing on screen changes meaning for a load that predates this.
    # Only stops that actually HAVE an appointment get a provenance — a null window
    # has no source to state, and claiming one would be the same defect one layer down.
    op.execute(
        f"UPDATE {SCHEMA}.stop AS s SET appointment_source = l.source::text "
        f"FROM {SCHEMA}.load AS l "
        "WHERE s.load_id = l.id AND s.appointment_start IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("stop", "appointment_source", schema=SCHEMA)

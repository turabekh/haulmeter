"""M13-FR4 — vendor crowd signals + a belief subject discriminator

A belief was keyed (facility_id, signal_type), which is right for facility-wide
readings (parking fullness, fuel price) but wrong for a vendor: two cooks at one
truck stop would tally against each other, so "vendor A is here" and "vendor B
isn't" would fight over a single row. `subject_ref` names what the signal is
ABOUT within the facility. It is an EMPTY STRING (never NULL) for every existing
signal, because PostgreSQL treats NULLs as distinct in a unique constraint — a
nullable column would silently switch off uniqueness for facility-wide beliefs.

Existing rows are untouched by design: they backfill to '' and keep aggregating
exactly as before.

Revision ID: 0034_f10_vendor_signals
Revises: 0033_f01_vendor_role
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_f10_vendor_signals"
down_revision: str | None = "0033_f01_vendor_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f10"
NEW_SIGNALS = ("vendor_present", "vendor_sold_out")


def upgrade() -> None:
    # enum values first: ALTER TYPE ... ADD VALUE cannot run inside a transaction
    op.execute("COMMIT")
    for value in NEW_SIGNALS:
        op.execute(f"ALTER TYPE {SCHEMA}.signal_type ADD VALUE IF NOT EXISTS '{value}'")

    for table in ("submission", "belief"):
        op.add_column(
            table,
            sa.Column("subject_ref", sa.String(64), nullable=False, server_default=sa.text("''")),
            schema=SCHEMA,
        )
    op.create_index("ix_f10_submission_subject_ref", "submission", ["subject_ref"], schema=SCHEMA)

    # the belief uniqueness key gains the subject: one belief per
    # (facility, signal, subject), with '' meaning "the facility as a whole"
    op.drop_constraint("uq_belief_facility_signal", "belief", schema=SCHEMA, type_="unique")
    op.create_unique_constraint(
        "uq_belief_facility_signal",
        "belief",
        ["facility_id", "signal_type", "subject_ref"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint("uq_belief_facility_signal", "belief", schema=SCHEMA, type_="unique")
    op.create_unique_constraint(
        "uq_belief_facility_signal", "belief", ["facility_id", "signal_type"], schema=SCHEMA
    )
    op.drop_index("ix_f10_submission_subject_ref", "submission", schema=SCHEMA)
    for table in ("belief", "submission"):
        op.drop_column(table, "subject_ref", schema=SCHEMA)
    # enum values cannot be dropped in PostgreSQL — the two vendor signals remain

"""AI-CONTEXT: a facility's IANA timezone — the prerequisite the audit named for F-14
and F-22 and could not answer from a dump.

F2 carried no timezone at all, and `DriverProfile.home_timezone` is written by nothing
outside the tests, so the product's only notion of local time was inert. Both money
questions were therefore being asked of UTC instants:

  · F-14, m06: `nights = (end_at.date() - start_at.date()).days`. In Dallas an
    11pm Aug 7 -> 5am Aug 9 stay is 05:00 Aug 8 -> 11:00 Aug 9 in UTC and billed as ONE
    night instead of two. `max(1, ...)` hid the short cases, so it read as correct.
  · F-22, m04: `arrival.date() == departure.date()`. An 8pm -> 4am Dallas layover is
    01:00 -> 09:00 on one UTC day, so the claim was REFUSED. F-21 filed claims that
    should not exist; this refused ones that should.

NULLABLE and left empty on purpose. `facility_timezone()` resolves a row the first time
something asks and stores what it finds, so the ~4,800 rows already in the registry heal
as they are used and a facility a driver creates at a dock is covered by the same path.
A backfill here would be a long-running data migration that can half-finish, for a column
whose absence is self-correcting.
"""

import sqlalchemy as sa
from alembic import op

revision = "0063_f02_facility_timezone"
down_revision = "0062_f09_monthly_budget"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "facility",
        sa.Column("timezone", sa.String(length=60), nullable=True),
        schema="f02",
    )


def downgrade() -> None:
    op.drop_column("facility", "timezone", schema="f02")

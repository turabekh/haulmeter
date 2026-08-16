"""AI-CONTEXT: the truck's own fuel economy, self-reported (J1-A3, §23 entry 154).

The true-profit calculator has burned a hardcoded **6.0 mpg** since it was written — in
`m08_intelligence`'s request model and again in the calculator surface's payload. Entry
154 named it as the remainder of that session. A driver hauling reefer at 5.2 and one
running light at 7.5 were handed the same fuel cost for the same route, and the screen
gave no sign that the number was ours rather than theirs.

NULLABLE, and that is the honest shape rather than a convenience. NULL means *this
driver has not told us*, which is different from any number we could put there — and the
difference is exactly what the basis line has to say out loud. A `server_default` of 6.0
would make every existing row assert a fuel economy its owner never reported, which is
the `assumed_none` failure entry 154 was written about, one column over.

`Numeric(3, 1)` rather than a float: 6.0 mpg is a figure a human types and reads back,
and binary float would make 6.1 render as 6.0999999. Range is enforced in F1 rather than
as a CHECK — the message a driver sees ("between 3 and 12") belongs with the code that
can say it in their language.
"""

import sqlalchemy as sa
from alembic import op

revision = "0081_driver_profile_mpg"
down_revision = "0080_m14_held_claim"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "driver_profile",
        sa.Column("mpg", sa.Numeric(3, 1), nullable=True),
        schema="f01",
    )


def downgrade() -> None:
    op.drop_column("driver_profile", "mpg", schema="f01")

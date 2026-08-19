"""f03: mark a visit the driver ATTESTED, so a sensor cannot silently overrule them.

AI-CONTEXT: §23 entry 227. A manual arrival is an explicit human statement — "I am here"
— and a single GPS fix was allowed to close the visit it opened, with no way for the
driver to contradict it. Measured on production: a stop attested at 07:56 was closed 76
seconds later by a fix ~17,000 km away, which drafted paperwork announcing the driver had
left a dock they were standing on.

`attested_at` is what lets the exit path tell the two kinds of visit apart. NULL means the
geofence opened it and the geofence may close it, exactly as before.

Revision ID: 0094_f03_attested_presence
"""

import sqlalchemy as sa
from alembic import op

revision = "0094_f03_attested_presence"
down_revision = "0093_m15_coaching_voice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "geofence_presence",
        sa.Column("attested_at", sa.DateTime(timezone=True), nullable=True),
        schema="f03",
    )


def downgrade() -> None:
    op.drop_column("geofence_presence", "attested_at", schema="f03")

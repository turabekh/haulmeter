"""AI-CONTEXT: the geofence state machine's structural guards (F3-2, F3-3, F3-4).

The machine that mints the arrival and departure every detention dollar descends from
trusted its pings to be ordered, unique, accurate and finite. This migration is the part
of the fix that has to live in Postgres.

ONE ACTIVE PRESENCE PER (account, facility). The ENTER branch is check-then-add over a
table with no uniqueness, so two concurrent first-pings — two devices, or two parallel
offline flushes — both miss and both insert. EXIT then closes one of them and the zombie
keeps its old `entered_at`, which `visit_window` can hand to a LATER load as its arrival.
The preflight refuses rather than dying mid-apply (0060's shape); unlike 0067's, duplicates
here are race anomalies rather than a designed-in property, so zero is the expected count.

NO INDEX ON ARMINGS, deliberately, and it is the opposite call to the one above. Armings
duplicate BY DESIGN today — `arm_geofence` writes a row per call and has done since the
Foundation — so a unique index plus a refusing preflight would be undeployable by
construction: it would refuse on every box that has ever run the product. Armings are
reconciled in application code instead (`reconcile_armings`), which needs no schema.

`evaluation_cursor` is what makes per-account evaluation serial. Locking the row `FOR
UPDATE` is the mechanism that kills the duplicate-presence race at its source; the index
above is the structural backstop for the case the lock cannot cover (a row that does not
exist yet on two connections at once). `last_evaluated_at` is also the ordering guard's
memory: a ping at or before it is trail-recorded and not evaluated.

`outside_streak` is the exit debounce's counter. It ships with a config default of 1
confirming ping, which is exactly today's behaviour — the column moves no money on its own.
"""

import sqlalchemy as sa
from alembic import op

revision = "0068_f03_location_integrity"
down_revision = "0067_m03_claim_hardening"
branch_labels = None
depends_on = None

SCHEMA = "f03"

DUPLICATE_ACTIVE_PRESENCE = sa.text(
    """
    SELECT account_id, facility_id, count(*) AS n
      FROM f03.geofence_presence
     WHERE active
     GROUP BY account_id, facility_id
    HAVING count(*) > 1
    """
)


def _refuse(rows, what: str) -> None:
    detail = "; ".join(str(tuple(r)) for r in rows[:10])
    raise RuntimeError(
        f"0068 cannot apply: {len(rows)} {what} already exist and would violate the new "
        f"constraint. Reconcile them first — this migration will not choose which row "
        f"survives. Offenders: {detail}"
    )


def upgrade() -> None:
    conn = op.get_bind()

    duplicates = conn.execute(DUPLICATE_ACTIVE_PRESENCE).fetchall()
    if duplicates:
        _refuse(duplicates, "(account, facility) pairs with more than one ACTIVE presence")

    op.create_index(
        "uq_geofence_presence_active",
        "geofence_presence",
        ["account_id", "facility_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("active"),
    )

    op.add_column(
        "geofence_presence",
        sa.Column("outside_streak", sa.Integer(), nullable=False, server_default="0"),
        schema=SCHEMA,
    )

    op.create_table(
        "evaluation_cursor",
        sa.Column("account_id", sa.Uuid(), primary_key=True),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["f01.account.id"], ondelete="CASCADE"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("evaluation_cursor", schema=SCHEMA)
    op.drop_column("geofence_presence", "outside_streak", schema=SCHEMA)
    op.drop_index("uq_geofence_presence_active", table_name="geofence_presence", schema=SCHEMA)

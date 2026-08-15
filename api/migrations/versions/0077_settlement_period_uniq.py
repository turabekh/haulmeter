"""AI-CONTEXT: one settlement per driver, carrier and pay period.

MEASURED BEFORE THIS EXISTED: a driver pressing "Run audit" three times on the same pay
period — which is what you do after a typo in what your carrier paid — produced three
settlements, three sets of flagged discrepancies, and a `flagged_cents` of
**15000 → 30000 → 45000** on the Money tab. The app told them the same $150 three times.

Audit F-23 fixed the neighbouring half (an all-time `owed` compared against a
period-scoped `paid`, so one balance was re-flagged on every LATER settlement). Re-running
the SAME period was never covered, and it is the more common act.

THE BACKFILL MOVES RATHER THAN DELETES. Duplicate settlements may carry discrepancies the
driver has already ACTED on — `submitted` to a carrier, or `resolved`. Those are a record
of something a person did, so they are re-pointed onto the surviving settlement before the
losers go; only `flagged` rows, which the next audit regenerates from current data, are
dropped with them. The survivor is the NEWEST row per key, because that is the driver's
most recent correction.

Measured on the dev box before writing this: 2 settlement groups, 1 of them duplicated.
"""

import sqlalchemy as sa
from alembic import op

revision = "0077_settlement_period_uniq"
down_revision = "0076_message_attachment"
branch_labels = None
depends_on = None

SCHEMA = "m09"
CONSTRAINT = "uq_settlement_driver_carrier_period"


def upgrade() -> None:
    bind = op.get_bind()

    # the survivor per (driver, carrier, period): the most recently created row
    survivors = sa.text(
        f"""
        CREATE TEMPORARY TABLE _settlement_survivor AS
        SELECT DISTINCT ON (driver_account_id, carrier, period_start, period_end)
               id, driver_account_id, carrier, period_start, period_end
        FROM {SCHEMA}.settlement
        ORDER BY driver_account_id, carrier, period_start, period_end, created_at DESC, id
        """
    )
    bind.execute(survivors)

    # anything the driver acted on moves to the survivor rather than dying with its row
    bind.execute(
        sa.text(
            f"""
            UPDATE {SCHEMA}.discrepancy d
               SET settlement_id = s.id
              FROM {SCHEMA}.settlement old
              JOIN _settlement_survivor s
                ON s.driver_account_id = old.driver_account_id
               AND s.carrier           = old.carrier
               AND s.period_start      = old.period_start
               AND s.period_end        = old.period_end
             WHERE d.settlement_id = old.id
               AND old.id <> s.id
               AND d.status <> 'flagged'
            """
        )
    )

    # the losers go, and their lines and remaining (flagged) discrepancies cascade
    bind.execute(
        sa.text(
            f"""
            DELETE FROM {SCHEMA}.settlement
             WHERE id NOT IN (SELECT id FROM _settlement_survivor)
            """
        )
    )
    bind.execute(sa.text("DROP TABLE _settlement_survivor"))

    op.create_unique_constraint(
        CONSTRAINT,
        "settlement",
        ["driver_account_id", "carrier", "period_start", "period_end"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    # AI-CONTEXT: the merged rows are NOT restored, and cannot be — a settlement deleted
    # as a duplicate has no separate identity to come back to. Dropping the constraint is
    # the whole of the reversal.
    op.drop_constraint(CONSTRAINT, "settlement", schema=SCHEMA, type_="unique")

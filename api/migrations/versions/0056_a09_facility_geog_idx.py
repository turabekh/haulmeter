"""A9 §4 — a GiST index on the geography EXPRESSION, not the column

v2.0 A9 §4 says it outright: "Every `geom::geography` predicate needs a GiST index on
the expression, not the column; run EXPLAIN (ANALYZE) before multiplying the table."
Measured before writing this, on the deployed box rather than a laptop — the laptop's
postgres runs amd64 under emulation and its timings are fiction:

    Seq Scan on facility  (actual time=15.6..29.8 rows=26)
      Rows Removed by Filter: 6486
    Execution Time: 28 ms

`ix_facility_geom` is a GiST index on `geom`, which is a GEOMETRY index. Every distance
query in F2 casts to geography — `ST_DWithin(geom::geography, point, m)` — and a
geometry index cannot answer that, so all six of them were sequential scans. Nobody
noticed because 6,516 rows is 28 ms.

With this index the same query examines 30 rows instead of 6,512 and runs in 13.5 ms.
The wall-clock halving is not the point; the row count is. A sequential scan costs
~4.3 µs per row measured, so it is LINEAR in the size of the table — and A9 exists to
multiply that table by roughly six. Extrapolated (arithmetic on a measured rate, not a
measurement): ~170 ms per query at 40,000 facilities, and `_facilities_in_area` issues
one query PER FACILITY TYPE, so the Drive preset's five kinds would cost most of a
second before a single pin is enriched. §20 gives the whole map 4 s cold.

This index is O(log n) in the same place. It is cheap to add now and it is the
difference between A9 being an ingest and A9 being an outage.

The revision id is short because `alembic_version.version_num` is varchar(32) and the
descriptive name this wanted was 33 — the upgrade fails on the version write AFTER
creating the index, which rolls back cleanly but reads like the index is the problem.

CONCURRENTLY is deliberately NOT used: this runs inside alembic's transaction, the
table is small today, and the lock is measured in milliseconds. At national density a
future rebuild should reconsider that.

Revision ID: 0056_a09_facility_geog_idx
Revises: 0055_f08_push_subscription
Create Date: 2026-08-01
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0056_a09_facility_geog_idx"
down_revision: str | None = "0055_f08_push_subscription"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # IF NOT EXISTS because the index was created by hand on the box while measuring,
    # and a migration that fails on an index someone already added is a migration that
    # teaches people to skip migrations.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_facility_geog "
        "ON f02.facility USING gist ((geom::geography))"
    )
    # the planner will keep choosing the sequential scan until it knows the index is
    # there — an index nobody's statistics have seen is an index nobody uses
    op.execute("ANALYZE f02.facility")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS f02.ix_facility_geog")

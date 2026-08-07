"""AI-CONTEXT: the four check-then-act money races, closed in the database (audit F-05,
F-13, F-28, F-29).

F-05 and F-13 need schema; F-28 (a row lock) and F-29 (an unconditional log write) are
code-only and appear here only in this note, so a later reader looking for them stops.

Both constraints are written so a duplicate or an overlap becomes IMPOSSIBLE rather than
unlikely — application checks read rows a concurrent transaction has not committed yet,
and they do not survive a second API replica however carefully they are written.

The upgrade refuses to run against data that already violates either rule, and says which
rows, rather than surfacing a raw Postgres error from the middle of a deploy.
"""

import sqlalchemy as sa
from alembic import op

revision = "0060_money_race_constraints"
down_revision = "0059_f13_config_decl"
branch_labels = None
depends_on = None

DUPLICATE_REFS = sa.text(
    """
    SELECT entry_type::text, external_ref, count(*) AS n
      FROM f07.journal_entry
     WHERE external_ref IS NOT NULL
     GROUP BY entry_type, external_ref
    HAVING count(*) > 1
    """
)

OVERLAPPING_BOOKINGS = sa.text(
    """
    SELECT a.id AS a_id, b.id AS b_id, a.spot_id
      FROM m06.booking a
      JOIN m06.booking b
        ON a.spot_id = b.spot_id
       AND a.id < b.id
       AND tstzrange(a.start_at, a.end_at) && tstzrange(b.start_at, b.end_at)
     WHERE a.state IN ('booked', 'checked_in', 'checked_out')
       AND b.state IN ('booked', 'checked_in', 'checked_out')
    """
)


def _refuse(rows, what: str) -> None:
    detail = "; ".join(str(tuple(r)) for r in rows[:10])
    raise RuntimeError(
        f"0060 cannot apply: {len(rows)} {what} already exist and would violate the new "
        f"constraint. Reconcile them first — this migration will not choose which row "
        f"survives. Offenders: {detail}"
    )


def upgrade() -> None:
    conn = op.get_bind()

    duplicates = conn.execute(DUPLICATE_REFS).fetchall()
    if duplicates:
        _refuse(duplicates, "duplicate (entry_type, external_ref) journal entries")

    overlaps = conn.execute(OVERLAPPING_BOOKINGS).fetchall()
    if overlaps:
        _refuse(overlaps, "overlapping active bookings")

    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_index(
        "uq_journal_entry_type_ref",
        "journal_entry",
        ["entry_type", "external_ref"],
        unique=True,
        schema="f07",
        postgresql_where=sa.text("external_ref IS NOT NULL"),
    )

    op.execute(
        """
        ALTER TABLE m06.booking
          ADD CONSTRAINT ex_booking_no_overlap
          EXCLUDE USING gist (
            spot_id WITH =,
            tstzrange(start_at, end_at) WITH &&
          ) WHERE (state IN ('booked', 'checked_in', 'checked_out'))
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE m06.booking DROP CONSTRAINT ex_booking_no_overlap")
    op.drop_index("uq_journal_entry_type_ref", table_name="journal_entry", schema="f07")
    # btree_gist is deliberately left installed: dropping an extension another object may
    # come to depend on is a worse failure than an unused one sitting in the database.

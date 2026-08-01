"""AI-CONTEXT: A1 requirement 1 — `seal` and `damage` as capturable document types.

The test database is built by `create_all`, so the Python enum alone makes every test
pass while the box rejects both values. That gap is the same shape as A9's geography
index, which lived only in a migration and so was invisible to every test — this is the
mirror of it, and both directions end with a suite that agrees with nothing real.

ADD VALUE IF NOT EXISTS is idempotent; PostgreSQL cannot drop an enum value, so the
downgrade is deliberately a no-op rather than a lie about being reversible.
"""

from alembic import op

revision = "0058_a01_checklist_doc"
down_revision = "0057_a01_stop_packet"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE f06.doc_type ADD VALUE IF NOT EXISTS 'seal'")
    op.execute("ALTER TYPE f06.doc_type ADD VALUE IF NOT EXISTS 'damage'")


def downgrade() -> None:
    pass

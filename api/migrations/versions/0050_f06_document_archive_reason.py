"""F6 — why a document was archived, not merely that it was

0049 gave a document `archived_at`, and exactly one thing could set it: filing a
replacement. A driver had no way to remove anything from their own wallet — a blurry
photo, a permit for a state they no longer run, a credential filed twice — so the
wallet could only ever grow.

Removal is now the driver's, and it is still not a delete. §17 Q16 forbids hard
delete and the reasoning of 0049 is unchanged: an old card is the answer to "what
were you carrying at that inspection in March". What removal changes is which
document the wallet PRODUCES, which is the only thing a driver or an inspector cares
about — and it is reversible, which supersession is not.

That makes the REASON load-bearing rather than decorative. "Replaced by your new CDL"
and "you removed this" are different facts about the same archived row, the archive
list must say which, and restoring is allowed for one and meaningless for the other.
Existing archived rows are backfilled to `superseded` because until this migration
that was the only way a row could have been archived.

Revision ID: 0050_f06_document_archive_reason
Revises: 0049_f06_document_supersession
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0050_f06_document_archive_reason"
down_revision: str | None = "0049_f06_document_supersession"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f06"


def upgrade() -> None:
    op.add_column(
        "document",
        sa.Column("archive_reason", sa.String(length=40), nullable=True),
        schema=SCHEMA,
    )
    # every row archived before this migration got there by supersession — it was the
    # only writer of archived_at that existed
    op.execute(
        f"UPDATE {SCHEMA}.document SET archive_reason = 'superseded' "
        "WHERE archived_at IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("document", "archive_reason", schema=SCHEMA)

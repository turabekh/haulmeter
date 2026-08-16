"""AI-CONTEXT: F6 gains a retention class for raw driver audio (E3 §E3.4.3, D14).

THE DEFAULT IS `permanent` AND THE SERVER DEFAULT IS TOO, which is the whole safety
property of this migration. Every row F6 already holds — every CDL, medical card,
insurance certificate, rate con and evidence photo — is backfilled to `permanent`, and so
is every row a future caller forgets to classify. Nothing enters the sweepable class
except by a caller explicitly saying what the object is.

`bytes_expire_at` is NULL for permanent rows, and the sweep additionally requires it to be
non-null, so a row would have to be wrong in TWO independent ways to be swept by accident.

A note for whoever reads this beside the archiving code in `models.py`: PRD §17 Q16 does
NOT forbid hard delete. It reads "Hard delete / data retention — OPEN, deliberately not
built... 'delete this user' is not a button but a workflow... Needs counsel before code",
and it scopes itself to ACCOUNT ERASURE. This class is a narrower, later, owner-signed law
(D14) about one kind of object, and it leaves Q16's question exactly as open as it found
it.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0086_f06_retention"
down_revision = "0085_f01_tg_guest"
branch_labels = None
depends_on = None

SCHEMA = "f06"


def upgrade() -> None:
    sa.Enum("permanent", "audio_30d", name="retention_class", schema=SCHEMA).create(
        op.get_bind(), checkfirst=True
    )
    retention = postgresql.ENUM(name="retention_class", schema=SCHEMA, create_type=False)

    op.add_column(
        "document",
        sa.Column("retention_class", retention, nullable=False, server_default="permanent"),
        schema=SCHEMA,
    )
    op.add_column(
        "document",
        sa.Column("bytes_expire_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "document",
        sa.Column("bytes_deleted_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_document_retention_class", "document", ["retention_class"], schema=SCHEMA
    )
    op.create_index("ix_document_bytes_expire_at", "document", ["bytes_expire_at"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_document_bytes_expire_at", "document", schema=SCHEMA)
    op.drop_index("ix_document_retention_class", "document", schema=SCHEMA)
    op.drop_column("document", "bytes_deleted_at", schema=SCHEMA)
    op.drop_column("document", "bytes_expire_at", schema=SCHEMA)
    op.drop_column("document", "retention_class", schema=SCHEMA)
    sa.Enum(name="retention_class", schema=SCHEMA).drop(op.get_bind(), checkfirst=True)

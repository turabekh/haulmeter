"""F4 — what was actually sent to a counterparty, pinned

Rendering an evidence pack is deterministic, so regenerating on demand is free and
always current. Sharing is a different act. A pack shared at 14:00 and regenerated
at 16:00 after another photo lands is a DIFFERENT DOCUMENT, and in a dispute the
question is never "what does the pack say now" — it is "what did we send them".

So a share pins the bytes: hashed, stored in F6 object storage, and recorded here
with an opaque token that resolves to those bytes and no others. The chain is free
to grow afterwards, which is exactly the reason this table exists.

Two columns are deliberately durable. `content_hash` and `storage_key` OUTLIVE
revocation, because closing a link does not unsend a document — a counterparty may
already hold a copy — and the record of what was sent must survive the decision to
stop hosting it. `first_opened_at` is kept apart from `opened_count` because "they
opened it on the 12th" is evidence, while a clerk refreshing four times is not four
facts.

The token is random rather than signed: the row exists anyway for the hash and the
key, so a lookup costs nothing, revocation is one column instead of a denylist, and
there is no signing secret to keep out of the repo.

Revision ID: 0047_f04_shared_pack
Revises: 0046_f08_followed_subjects
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0047_f04_shared_pack"
down_revision: str | None = "0046_f08_followed_subjects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f04"


def upgrade() -> None:
    op.create_table(
        "shared_pack",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("log_id", sa.Uuid(), nullable=False),
        sa.Column("template", sa.String(length=40), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("shared_by", sa.Uuid(), nullable=True),
        sa.Column("recipient", sa.String(length=320), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("first_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["log_id"], [f"{SCHEMA}.evidence_log.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shared_by"], ["f01.account.id"], ondelete="SET NULL"),
        schema=SCHEMA,
    )
    op.create_index("ix_f04_shared_pack_log_id", "shared_pack", ["log_id"], schema=SCHEMA)
    op.create_index(
        "ix_f04_shared_pack_content_hash", "shared_pack", ["content_hash"], schema=SCHEMA
    )
    op.create_index(
        "ix_f04_shared_pack_token", "shared_pack", ["token"], unique=True, schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_f04_shared_pack_token", "shared_pack", schema=SCHEMA)
    op.drop_index("ix_f04_shared_pack_content_hash", "shared_pack", schema=SCHEMA)
    op.drop_index("ix_f04_shared_pack_log_id", "shared_pack", schema=SCHEMA)
    op.drop_table("shared_pack", schema=SCHEMA)

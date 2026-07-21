"""F6 documents service — typed documents, extraction, expiry

Revision ID: 0006_f06_documents
Revises: 0005_f05_load
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_f06_documents"
down_revision: str | None = "0005_f05_load"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f06"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    doc_type = sa.Enum(
        "rate_con",
        "bol",
        "pod",
        "lumper_receipt",
        "cdl",
        "med_card",
        "insurance",
        "permit",
        "settlement",
        "other",
        name="doc_type",
        schema=SCHEMA,
    )
    extraction_status = sa.Enum(
        "pending", "extracted", "failed", name="extraction_status", schema=SCHEMA
    )

    op.create_table(
        "document",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("doc_type", doc_type, nullable=False),
        sa.Column("storage_key", sa.String(600), nullable=False),
        sa.Column("filename", sa.String(300), nullable=True),
        sa.Column("content_type", sa.String(120), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("issued_on", sa.Date(), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("sent_reminders", sa.JSON(), nullable=True),
        sa.Column("extraction", sa.JSON(), nullable=True),
        sa.Column("extraction_status", extraction_status, nullable=False, server_default="pending"),
        sa.Column("subject_kind", sa.String(40), nullable=True),
        sa.Column("subject_ref", sa.Uuid(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["f01.account.id"],
            ondelete="CASCADE",
            name="fk_document_account_id_account",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_document_account_id", "document", ["account_id"], schema=SCHEMA)
    op.create_index("ix_document_content_hash", "document", ["content_hash"], schema=SCHEMA)
    op.create_index("ix_document_expires_on", "document", ["expires_on"], schema=SCHEMA)
    op.create_index("ix_document_subject_ref", "document", ["subject_ref"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("document", schema=SCHEMA)
    for enum_name in ("extraction_status", "doc_type"):
        op.execute(f"DROP TYPE IF EXISTS {SCHEMA}.{enum_name}")
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")

"""M13 Vendor Network — schema m13 (FR1-FR4, discovery only)

Vendors, members, verification documents, appearances and offerings. Phase A
processes no payments: `offering.price_cents` is display-only, and there is
deliberately no order, charge, or payout table anywhere in this schema.

Revision ID: 0036_m13_vendor
Revises: 0035_f08_notification_class
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036_m13_vendor"
down_revision: str | None = "0035_f08_notification_class"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "m13"

vendor_type = sa.Enum("food_mobile", "service_center", name="vendor_type", schema=SCHEMA)
verify_status = sa.Enum(
    "unverified", "documents_on_file", "verified", name="vendor_verify_status", schema=SCHEMA
)
vendor_status = sa.Enum("active", "suspended", "merged", name="vendor_status", schema=SCHEMA)
member_role = sa.Enum("owner", "helper", name="member_role", schema=SCHEMA)
document_kind = sa.Enum(
    "license", "insurance", "halal_cert", name="vendor_document_kind", schema=SCHEMA
)
document_review = sa.Enum(
    "pending", "approved", "rejected", name="vendor_document_review", schema=SCHEMA
)
appearance_status = sa.Enum(
    "scheduled", "live", "done", "cancelled", "lapsed", name="appearance_status", schema=SCHEMA
)


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "vendor",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_account_id",
            sa.Uuid(),
            sa.ForeignKey("f01.account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("vendor_type", vendor_type, nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("name_normalized", sa.String(160), nullable=False),
        sa.Column("metro", sa.String(80), nullable=False, server_default=""),
        sa.Column("contact_phone", sa.String(20), nullable=False, server_default=""),
        sa.Column("categories", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("languages", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("halal_disclosure", sa.Text(), nullable=True),
        sa.Column("halal_answered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("verify_status", verify_status, nullable=False, server_default="unverified"),
        sa.Column("status", vendor_status, nullable=False, server_default="active"),
        sa.Column(
            "merged_into_id",
            sa.Uuid(),
            sa.ForeignKey(f"{SCHEMA}.vendor.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("consecutive_no_shows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("publish_suspended", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_dev", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema=SCHEMA,
    )
    vendor_indexes = (
        "owner_account_id",
        "name_normalized",
        "metro",
        "contact_phone",
        "status",
        "is_dev",
    )
    for column in vendor_indexes:
        op.create_index(f"ix_m13_vendor_{column}", "vendor", [column], schema=SCHEMA)
    # Q-5 dedupe blocking runs pg_trgm similarity over the normalized name
    op.execute(
        f"CREATE INDEX ix_m13_vendor_name_trgm ON {SCHEMA}.vendor "
        "USING gin (name_normalized gin_trgm_ops)"
    )

    op.create_table(
        "vendor_member",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "vendor_id",
            sa.Uuid(),
            sa.ForeignKey(f"{SCHEMA}.vendor.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("f01.account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("member_role", member_role, nullable=False, server_default="helper"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("vendor_id", "account_id", name="uq_vendor_member"),
        schema=SCHEMA,
    )
    op.create_index("ix_m13_member_vendor", "vendor_member", ["vendor_id"], schema=SCHEMA)
    op.create_index("ix_m13_member_account", "vendor_member", ["account_id"], schema=SCHEMA)

    op.create_table(
        "vendor_document",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "vendor_id",
            sa.Uuid(),
            sa.ForeignKey(f"{SCHEMA}.vendor.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("f06.document.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("doc_kind", document_kind, nullable=False),
        sa.Column("review_status", document_review, nullable=False, server_default="pending"),
        sa.Column("moderation_ref", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_m13_document_vendor", "vendor_document", ["vendor_id"], schema=SCHEMA)

    op.create_table(
        "appearance",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "vendor_id",
            sa.Uuid(),
            sa.ForeignKey(f"{SCHEMA}.vendor.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "facility_id",
            sa.Uuid(),
            sa.ForeignKey("f02.facility.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", appearance_status, nullable=False, server_default="scheduled"),
        sa.Column("recurrence", sa.JSON(), nullable=True),
        sa.Column("series_id", sa.Uuid(), nullable=True),
        sa.Column("property_approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema=SCHEMA,
    )
    for column in ("vendor_id", "facility_id", "starts_at", "ends_at", "status", "series_id"):
        op.create_index(f"ix_m13_appearance_{column}", "appearance", [column], schema=SCHEMA)

    op.create_table(
        "offering",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "appearance_id",
            sa.Uuid(),
            sa.ForeignKey(f"{SCHEMA}.appearance.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        # informational only — Phase A moves no money
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("portions", sa.Integer(), nullable=True),
        schema=SCHEMA,
    )
    op.create_index("ix_m13_offering_appearance", "offering", ["appearance_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("offering", schema=SCHEMA)
    op.drop_table("appearance", schema=SCHEMA)
    op.drop_table("vendor_document", schema=SCHEMA)
    op.drop_table("vendor_member", schema=SCHEMA)
    op.drop_table("vendor", schema=SCHEMA)
    for enum_type in (
        appearance_status,
        document_review,
        document_kind,
        member_role,
        vendor_status,
        verify_status,
        vendor_type,
    ):
        enum_type.drop(op.get_bind(), checkfirst=True)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")

"""M13 Session B — reviews, promotions, facility claims, content reports

FR5 vendor reviews (publish immediately, hidden only on report — see ReviewStatus),
FR6 promotions (labelled slots; no price/bid/billing column exists, Phase A),
FR7 facility claims (curated facts live on the CLAIM, never written back to
f02.facility, so a claim can only ever add to what ingestion knows), and the Q-8
content-report ledger keyed per reporting driver so a vendor listing needs reports
from N DISTINCT drivers before it hides.

Revision ID: 0038_m13_session_b
Revises: 0037_f10_source_width
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038_m13_session_b"
down_revision: str | None = "0037_f10_source_width"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "m13"

review_status = sa.Enum(
    "visible", "hidden_pending", "removed", name="vendor_review_status", schema=SCHEMA
)
promotion_status = sa.Enum(
    "active",
    "expired",
    "cancelled",
    "hidden_pending",
    "removed",
    name="promotion_status",
    schema=SCHEMA,
)
promotion_scope = sa.Enum(
    "own_appearances", "claimed_facility", name="promotion_scope", schema=SCHEMA
)
claim_status = sa.Enum(
    "pending", "approved", "rejected", "disputed", name="claim_status", schema=SCHEMA
)
moderation_reason = sa.Enum(
    "spam",
    "offensive",
    "false_information",
    "false_property_attestation",
    "impersonation",
    "other",
    name="moderation_reason",
    schema=SCHEMA,
)

VENDOR_FK = f"{SCHEMA}.vendor.id"


def upgrade() -> None:
    op.create_table(
        "vendor_review",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "vendor_id", sa.Uuid(), sa.ForeignKey(VENDOR_FK, ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("f01.account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("status", review_status, nullable=False, server_default="visible"),
        sa.Column("moderation_ref", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema=SCHEMA,
    )
    for column in ("vendor_id", "account_id", "status"):
        op.create_index(f"ix_m13_review_{column}", "vendor_review", [column], schema=SCHEMA)

    op.create_table(
        "promotion",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "vendor_id", sa.Uuid(), sa.ForeignKey(VENDOR_FK, ondelete="CASCADE"), nullable=False
        ),
        sa.Column("text", sa.String(140), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope", promotion_scope, nullable=False, server_default="own_appearances"),
        sa.Column("status", promotion_status, nullable=False, server_default="active"),
        sa.Column("pushed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("moderation_ref", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema=SCHEMA,
    )
    for column in ("vendor_id", "starts_at", "ends_at", "status"):
        op.create_index(f"ix_m13_promotion_{column}", "promotion", [column], schema=SCHEMA)

    op.create_table(
        "facility_claim",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "vendor_id", sa.Uuid(), sa.ForeignKey(VENDOR_FK, ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "facility_id",
            sa.Uuid(),
            sa.ForeignKey("f02.facility.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("claimed_name", sa.String(160), nullable=False),
        sa.Column("name_match_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("f06.document.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", claim_status, nullable=False, server_default="pending"),
        sa.Column("moderation_ref", sa.Uuid(), nullable=True),
        sa.Column("services_added", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("hours", sa.String(200), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    for column in ("vendor_id", "facility_id", "status"):
        op.create_index(f"ix_m13_claim_{column}", "facility_claim", [column], schema=SCHEMA)

    op.create_table(
        "content_report",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("content_kind", sa.String(40), nullable=False),
        sa.Column("content_ref", sa.Uuid(), nullable=False),
        sa.Column(
            "vendor_id", sa.Uuid(), sa.ForeignKey(VENDOR_FK, ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("f01.account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", moderation_reason, nullable=False),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("upheld", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        # one report per driver per item: the N-distinct-driver threshold is only
        # meaningful if one person cannot manufacture N reports
        sa.UniqueConstraint(
            "content_kind", "content_ref", "account_id", name="uq_report_content_account"
        ),
        schema=SCHEMA,
    )
    for column in ("content_kind", "content_ref", "vendor_id", "account_id"):
        op.create_index(f"ix_m13_report_{column}", "content_report", [column], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("content_report", schema=SCHEMA)
    op.drop_table("facility_claim", schema=SCHEMA)
    op.drop_table("promotion", schema=SCHEMA)
    op.drop_table("vendor_review", schema=SCHEMA)
    for enum_type in (
        moderation_reason,
        claim_status,
        promotion_scope,
        promotion_status,
        review_status,
    ):
        enum_type.drop(op.get_bind(), checkfirst=True)

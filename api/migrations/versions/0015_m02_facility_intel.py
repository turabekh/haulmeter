"""M2 facility intelligence — profiles, structured reviews

Revision ID: 0015_m02_facility_intel
Revises: 0014_f15_localization
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_m02_facility_intel"
down_revision: str | None = "0014_f15_localization"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "m02"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    review_status = sa.Enum("pending", "approved", "rejected", name="review_status", schema=SCHEMA)

    op.create_table(
        "facility_profile",
        sa.Column("facility_id", sa.Uuid(), primary_key=True),
        sa.Column("check_in_procedure", sa.Text(), nullable=True),
        sa.Column("ppe_rules", sa.Text(), nullable=True),
        sa.Column("restrooms", sa.Boolean(), nullable=True),
        sa.Column("overnight_parking", sa.Boolean(), nullable=True),
        sa.Column("backing_type", sa.String(60), nullable=True),
        sa.Column("hazards", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["f02.facility.id"],
            ondelete="CASCADE",
            name="fk_facility_profile_facility_id_facility",
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "facility_review",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("ratings", sa.JSON(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("status", review_status, nullable=False, server_default="pending"),
        sa.Column("moderation_ref", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["f02.facility.id"],
            ondelete="CASCADE",
            name="fk_facility_review_facility_id_facility",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["f01.account.id"],
            ondelete="CASCADE",
            name="fk_facility_review_account_id_account",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_facility_review_facility_id", "facility_review", ["facility_id"], schema=SCHEMA
    )
    op.create_index(
        "ix_facility_review_account_id", "facility_review", ["account_id"], schema=SCHEMA
    )
    op.create_index("ix_facility_review_status", "facility_review", ["status"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("facility_review", schema=SCHEMA)
    op.drop_table("facility_profile", schema=SCHEMA)
    op.execute(f"DROP TYPE IF EXISTS {SCHEMA}.review_status")
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")

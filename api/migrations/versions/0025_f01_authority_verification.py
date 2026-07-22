"""F1 identity — FMCSA operating-authority verification on the driver profile

Revision ID: 0025_f01_authority_verification
Revises: 0024_m03_start_notice
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_f01_authority_verification"
down_revision: str | None = "0024_m03_start_notice"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f01"


def upgrade() -> None:
    verify_status = sa.Enum(
        "unverified", "verified", "failed", name="verify_status", schema=SCHEMA
    )
    verify_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "driver_profile",
        sa.Column("mc_number", sa.String(length=12), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "driver_profile",
        sa.Column("dot_number", sa.String(length=12), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "driver_profile",
        sa.Column("legal_name", sa.String(length=160), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "driver_profile",
        sa.Column(
            "authority_verify_status",
            verify_status,
            nullable=False,
            server_default="unverified",
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "driver_profile",
        sa.Column("authority_verified_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("driver_profile", "authority_verified_at", schema=SCHEMA)
    op.drop_column("driver_profile", "authority_verify_status", schema=SCHEMA)
    op.drop_column("driver_profile", "legal_name", schema=SCHEMA)
    op.drop_column("driver_profile", "dot_number", schema=SCHEMA)
    op.drop_column("driver_profile", "mc_number", schema=SCHEMA)
    sa.Enum(name="verify_status", schema=SCHEMA).drop(op.get_bind(), checkfirst=True)

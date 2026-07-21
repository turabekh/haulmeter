"""M12 fleet & B2B — fleet membership, parking benefits, data subscriptions

Revision ID: 0023_m12_fleet
Revises: 0022_m10_community
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_m12_fleet"
down_revision: str | None = "0022_m10_community"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "m12"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    fleet_role = sa.Enum("owner", "dispatcher", "driver", name="fleet_role", schema=SCHEMA)
    membership_state = sa.Enum(
        "invited", "active", "removed", name="membership_state", schema=SCHEMA
    )

    op.create_table(
        "fleet_membership",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("fleet_org_id", sa.Uuid(), nullable=False),
        sa.Column("driver_account_id", sa.Uuid(), nullable=False),
        sa.Column("role", fleet_role, nullable=False),
        sa.Column("consent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("state", membership_state, nullable=False, server_default="invited"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["driver_account_id"],
            ["f01.account.id"],
            ondelete="CASCADE",
            name="fk_fleet_membership_driver_account_id_account",
        ),
        sa.UniqueConstraint("fleet_org_id", "driver_account_id", name="uq_fleet_member"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_fleet_membership_fleet_org_id", "fleet_membership", ["fleet_org_id"], schema=SCHEMA
    )
    op.create_index(
        "ix_fleet_membership_driver_account_id",
        "fleet_membership",
        ["driver_account_id"],
        schema=SCHEMA,
    )

    op.create_table(
        "parking_benefit",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("fleet_org_id", sa.Uuid(), nullable=False),
        sa.Column("monthly_allowance_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("policy", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_parking_benefit_fleet_org_id",
        "parking_benefit",
        ["fleet_org_id"],
        unique=True,
        schema=SCHEMA,
    )

    op.create_table(
        "benefit_usage",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("fleet_org_id", sa.Uuid(), nullable=False),
        sa.Column("driver_account_id", sa.Uuid(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("spent_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["driver_account_id"],
            ["f01.account.id"],
            ondelete="CASCADE",
            name="fk_benefit_usage_driver_account_id_account",
        ),
        sa.UniqueConstraint("fleet_org_id", "driver_account_id", "month", name="uq_benefit_usage"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_benefit_usage_fleet_org_id", "benefit_usage", ["fleet_org_id"], schema=SCHEMA
    )
    op.create_index(
        "ix_benefit_usage_driver_account_id", "benefit_usage", ["driver_account_id"], schema=SCHEMA
    )

    op.create_table(
        "data_subscription",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("subscriber_ref", sa.String(200), nullable=False),
        sa.Column("tier", sa.String(40), nullable=False, server_default="standard"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("subscriber_ref", name="uq_data_subscription_subscriber_ref"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("data_subscription", schema=SCHEMA)
    op.drop_table("benefit_usage", schema=SCHEMA)
    op.drop_table("parking_benefit", schema=SCHEMA)
    op.drop_table("fleet_membership", schema=SCHEMA)
    op.execute(f"DROP TYPE IF EXISTS {SCHEMA}.membership_state")
    op.execute(f"DROP TYPE IF EXISTS {SCHEMA}.fleet_role")
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")

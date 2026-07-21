"""F1 identity — accounts, pluggable auth methods, sessions, orgs, profiles

Revision ID: 0001_f01_identity
Revises:
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_f01_identity"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f01"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    method_type = sa.Enum(
        "password", "oauth", "otp_email", "otp_sms", name="method_type", schema=SCHEMA
    )
    role = sa.Enum(
        "driver", "fleet_admin", "property_owner", "platform_admin", name="role", schema=SCHEMA
    )
    org_type = sa.Enum("fleet", "property_business", name="org_type", schema=SCHEMA)
    authority_type = sa.Enum("own_mc", "leased", "company", name="authority_type", schema=SCHEMA)

    op.create_table(
        "account",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("email", name="uq_account_email"),
        schema=SCHEMA,
    )
    op.create_index("ix_account_email", "account", ["email"], schema=SCHEMA)

    op.create_table(
        "auth_method",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("method_type", method_type, nullable=False),
        sa.Column("identifier", sa.String(320), nullable=False),
        sa.Column("secret_ref", sa.String(1024), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"],
            [f"{SCHEMA}.account.id"],
            ondelete="CASCADE",
            name="fk_auth_method_account_id_account",
        ),
        sa.UniqueConstraint("method_type", "identifier", name="uq_auth_method_type_identifier"),
        schema=SCHEMA,
    )
    op.create_index("ix_auth_method_account_id", "auth_method", ["account_id"], schema=SCHEMA)

    op.create_table(
        "auth_session",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("token", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("client_skew_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"],
            [f"{SCHEMA}.account.id"],
            ondelete="CASCADE",
            name="fk_auth_session_account_id_account",
        ),
        sa.UniqueConstraint("token", name="uq_auth_session_token"),
        schema=SCHEMA,
    )
    op.create_index("ix_auth_session_account_id", "auth_session", ["account_id"], schema=SCHEMA)
    op.create_index("ix_auth_session_token", "auth_session", ["token"], schema=SCHEMA)

    op.create_table(
        "organization",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_type", org_type, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        schema=SCHEMA,
    )

    op.create_table(
        "org_membership",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["org_id"],
            [f"{SCHEMA}.organization.id"],
            ondelete="CASCADE",
            name="fk_org_membership_org_id_organization",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            [f"{SCHEMA}.account.id"],
            ondelete="CASCADE",
            name="fk_org_membership_account_id_account",
        ),
        sa.UniqueConstraint("org_id", "account_id", name="uq_org_membership_org_account"),
        schema=SCHEMA,
    )
    op.create_index("ix_org_membership_org_id", "org_membership", ["org_id"], schema=SCHEMA)
    op.create_index("ix_org_membership_account_id", "org_membership", ["account_id"], schema=SCHEMA)

    op.create_table(
        "role_attachment",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("role", role, nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            [f"{SCHEMA}.account.id"],
            ondelete="CASCADE",
            name="fk_role_attachment_account_id_account",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            [f"{SCHEMA}.organization.id"],
            ondelete="CASCADE",
            name="fk_role_attachment_org_id_organization",
        ),
        sa.UniqueConstraint(
            "account_id", "role", "org_id", name="uq_role_attachment_account_role_org"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_role_attachment_account_id", "role_attachment", ["account_id"], schema=SCHEMA
    )

    op.create_table(
        "driver_profile",
        sa.Column("account_id", sa.Uuid(), primary_key=True),
        sa.Column("authority_type", authority_type, nullable=True),
        sa.Column("truck_length_ft", sa.Integer(), nullable=True),
        sa.Column("truck_height_in", sa.Integer(), nullable=True),
        sa.Column("gross_weight_lbs", sa.Integer(), nullable=True),
        sa.Column("trailer_type", sa.String(60), nullable=True),
        sa.Column("equipment_type", sa.String(60), nullable=True),
        sa.Column("home_timezone", sa.String(60), nullable=False, server_default="UTC"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            [f"{SCHEMA}.account.id"],
            ondelete="CASCADE",
            name="fk_driver_profile_account_id_account",
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("driver_profile", schema=SCHEMA)
    op.drop_table("role_attachment", schema=SCHEMA)
    op.drop_table("org_membership", schema=SCHEMA)
    op.drop_table("organization", schema=SCHEMA)
    op.drop_table("auth_session", schema=SCHEMA)
    op.drop_table("auth_method", schema=SCHEMA)
    op.drop_table("account", schema=SCHEMA)
    for enum_name in ("authority_type", "org_type", "role", "method_type"):
        op.execute(f"DROP TYPE IF EXISTS {SCHEMA}.{enum_name}")
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")

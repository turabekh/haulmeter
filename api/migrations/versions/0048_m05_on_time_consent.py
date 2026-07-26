"""M5 — the per-load opt-in for the on-time arrival notice

PRD §8.5 FR1 says the notice is "opt-in per load". It had nowhere to live: the
endpoint took a boolean per call, so the choice could not survive the drive.

It sits in M5 rather than on F5's `Stop` because whether to tell a broker you have
arrived is a protection decision, and F5 should stay a generic load record. Keyed by
LOAD because that is the unit the driver agrees to, while the notice fires per stop.

The consent gates the NOTICE only. The proof artifact is filed on every arrival
regardless — it is the driver's own protection, and someone who declined to notify
the broker still wants to be able to prove when they got there.

Revision ID: 0048_m05_on_time_consent
Revises: 0047_f04_shared_pack
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0048_m05_on_time_consent"
down_revision: str | None = "0047_f04_shared_pack"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "m05"


def upgrade() -> None:
    op.create_table(
        "on_time_consent",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("load_ref", sa.Uuid(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("counterparty_email", sa.String(length=320), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["account_id"], ["f01.account.id"], ondelete="CASCADE"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_m05_on_time_consent_account", "on_time_consent", ["account_id"], schema=SCHEMA
    )
    op.create_index(
        "ix_m05_on_time_consent_load", "on_time_consent", ["load_ref"], unique=True, schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_m05_on_time_consent_load", "on_time_consent", schema=SCHEMA)
    op.drop_index("ix_m05_on_time_consent_account", "on_time_consent", schema=SCHEMA)
    op.drop_table("on_time_consent", schema=SCHEMA)

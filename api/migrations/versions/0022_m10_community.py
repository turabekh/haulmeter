"""M10 community & points — contribution log, handoff relay, facility Q&A

Revision ID: 0022_m10_community
Revises: 0021_m09_money
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_m10_community"
down_revision: str | None = "0021_m09_money"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "m10"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    handoff_state = sa.Enum(
        "open", "claimed", "confirmed", "expired", "canceled",
        name="handoff_state", schema=SCHEMA,
    )

    op.create_table(
        "contribution_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["account_id"], ["f01.account.id"], ondelete="CASCADE",
            name="fk_contribution_log_account_id_account",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_contribution_log_account_id", "contribution_log", ["account_id"], schema=SCHEMA)
    op.create_index("ix_contribution_log_created_at", "contribution_log", ["created_at"], schema=SCHEMA)

    op.create_table(
        "handoff",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("facility_ref", sa.Uuid(), nullable=False),
        sa.Column("broadcaster_id", sa.Uuid(), nullable=False),
        sa.Column("claimer_id", sa.Uuid(), nullable=True),
        sa.Column("leaving_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", handoff_state, nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["broadcaster_id"], ["f01.account.id"], ondelete="CASCADE",
            name="fk_handoff_broadcaster_id_account",
        ),
        sa.ForeignKeyConstraint(
            ["claimer_id"], ["f01.account.id"], ondelete="SET NULL",
            name="fk_handoff_claimer_id_account",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_handoff_facility_ref", "handoff", ["facility_ref"], schema=SCHEMA)
    op.create_index("ix_handoff_broadcaster_id", "handoff", ["broadcaster_id"], schema=SCHEMA)

    op.create_table(
        "facility_question",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("facility_ref", sa.Uuid(), nullable=False),
        sa.Column("asker_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["asker_id"], ["f01.account.id"], ondelete="CASCADE",
            name="fk_facility_question_asker_id_account",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_facility_question_facility_ref", "facility_question", ["facility_ref"], schema=SCHEMA)

    op.create_table(
        "facility_answer",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("answerer_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("presence_proven", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["question_id"], [f"{SCHEMA}.facility_question.id"], ondelete="CASCADE",
            name="fk_facility_answer_question_id_facility_question",
        ),
        sa.ForeignKeyConstraint(
            ["answerer_id"], ["f01.account.id"], ondelete="CASCADE",
            name="fk_facility_answer_answerer_id_account",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_facility_answer_question_id", "facility_answer", ["question_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("facility_answer", schema=SCHEMA)
    op.drop_table("facility_question", schema=SCHEMA)
    op.drop_table("handoff", schema=SCHEMA)
    op.drop_table("contribution_log", schema=SCHEMA)
    op.execute(f"DROP TYPE IF EXISTS {SCHEMA}.handoff_state")
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")

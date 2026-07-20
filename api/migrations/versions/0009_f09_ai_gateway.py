"""F9 AI gateway — prompt registry, fixtures, budgets, calls, embeddings

Revision ID: 0009_f09_ai_gateway
Revises: 0008_f08_notifications
Create Date: 2026-07-20

AI-CONTEXT: self-contained local MetaData + create_all (decision #27): `ai_task`
is shared by two tables. Vector(16) matches provider.EMBED_DIM (placeholder; the
real embedding dimension is set at F9 activation — a migration). Requires the
pgvector `vector` extension (present via infra/postgres/init).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0009_f09_ai_gateway"
down_revision: str | None = "0008_f08_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f09"
EMBED_DIM = 16


def _tables():
    meta = sa.MetaData()
    ai_task = sa.Enum(
        "document_parse", "drafting", "embedding", "stt", "tts", "classify",
        name="ai_task", schema=SCHEMA,
    )

    sa.Table("account", meta, sa.Column("id", sa.Uuid(), primary_key=True), schema="f01")

    prompt = sa.Table(
        "prompt",
        meta,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("task", ai_task, nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("model_hint", sa.String(120), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("key", "version", name="uq_prompt_key_version"),
        sa.Index("ix_prompt_key", "key"),
        schema=SCHEMA,
    )

    prompt_fixture = sa.Table(
        "prompt_fixture",
        meta,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("prompt_key", sa.String(120), nullable=False),
        sa.Column("input", sa.JSON(), nullable=True),
        sa.Column("expected", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Index("ix_prompt_fixture_prompt_key", "prompt_key"),
        schema=SCHEMA,
    )

    module_budget = sa.Table(
        "module_budget",
        meta,
        sa.Column("module", sa.String(40), primary_key=True),
        sa.Column("budget_micros", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        schema=SCHEMA,
    )

    ai_call = sa.Table(
        "ai_call",
        meta,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("module", sa.String(40), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("task", ai_task, nullable=False),
        sa.Column("prompt_key", sa.String(120), nullable=True),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_micros", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["account_id"], ["f01.account.id"], ondelete="SET NULL",
            name="fk_ai_call_account_id_account", use_alter=True,
        ),
        sa.Index("ix_ai_call_module", "module"),
        schema=SCHEMA,
    )

    embedding = sa.Table(
        "embedding",
        meta,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_kind", sa.String(40), nullable=False),
        sa.Column("owner_ref", sa.Uuid(), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("vector", Vector(EMBED_DIM), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Index("ix_embedding_owner_kind", "owner_kind"),
        sa.Index("ix_embedding_owner_ref", "owner_ref"),
        schema=SCHEMA,
    )
    return meta, [prompt, prompt_fixture, module_budget, ai_call, embedding]


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    meta, tables = _tables()
    meta.create_all(op.get_bind(), tables=tables)


def downgrade() -> None:
    meta, tables = _tables()
    meta.drop_all(op.get_bind(), tables=tables)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")

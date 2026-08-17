"""AI-CONTEXT: model answers — the thing a driver SHADOWS (M15-FR5).

FR5's loop is eight steps and one of them is "hear a clear model answer, repeat it". There
was nowhere to put one. `phrase_variant` is explicitly "one way an OFFICER might say an
intent"; a model answer is the other half of the exchange, and hanging it off the officer's
table would make `teachable_variants` — which the session loop draws its questions from —
capable of asking the driver a question the driver is supposed to answer.

SO IT IS ITS OWN TABLE, SHAPED LIKE `phrase_variant` ON PURPOSE: same `status`, same
`version`, same `audio_ref`. That is what lets the Q-6 publish pipeline, the admin review
surface and the TTS synthesis job all treat it as content without special-casing it. A
different shape would have meant three near-copies of code that already exists.

`locale` is on the row because a model answer is spoken ENGLISH — that is what a driver is
practising — while the coaching that explains it is in their own language. The column is
there so the distinction stays visible rather than assumed, and so a future locale is a
content pass rather than a migration.

No unique constraint over (intent, version): an intent may hold several released model
answers, for the same reason it holds several phrasings. Trap 4a's lesson is about
NULLABLE columns in unique indexes, and the fix there was to stop pretending a constraint
existed; here the honest statement is that there is no uniqueness to enforce.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0088_m15_model_answer"
down_revision = "0087_m15_hidden"
branch_labels = None
depends_on = None

SCHEMA = "m15"


def upgrade() -> None:
    op.create_table(
        "model_answer",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("intent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("locale", sa.String(12), nullable=False, server_default="en"),
        sa.Column("audio_ref", postgresql.UUID(as_uuid=True), nullable=True),
        # AI-CONTEXT: the enum ALREADY EXISTS (created by 0084 for phrase_variant), so it
        # is referenced rather than re-created. A bare sa.Enum here would emit its own
        # CREATE TYPE and roll the whole migration back reporting success — trap 2.
        sa.Column(
            "status",
            postgresql.ENUM(name="content_status", schema=SCHEMA, create_type=False),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["intent_id"], [f"{SCHEMA}.intent.id"], name="fk_model_answer_intent"
        ),
        sa.ForeignKeyConstraint(
            ["audio_ref"], ["f06.document.id"], name="fk_model_answer_audio"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_model_answer_intent_status", "model_answer", ["intent_id", "status"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_model_answer_intent_status", table_name="model_answer", schema=SCHEMA)
    op.drop_table("model_answer", schema=SCHEMA)

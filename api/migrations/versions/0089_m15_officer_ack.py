"""AI-CONTEXT: the officer says "alright" (M15-FR3) — connective tissue, as content.

WHAT THIS FIXES. The loop was: question, answer, question, answer. No human conducts an
interview that way. A real officer says "okay", "alright", "thank you" between things —
and the absence of that is most of what made the simulation feel like a form with a
microphone attached. The owner used it and said so.

IT IS ITS OWN TABLE, NOT AN INTENT, and that is the whole point. If acknowledgements lived
as an `Intent` with phrase variants, two things would go wrong the moment somebody looked
away: the scenario engine could ASK "alright?" as a question, and the drill's
`unseen_variants` — which walks every intent — would set a driver practising how to answer
"okay". A separate table cannot be reached by either, by construction rather than by a
filter someone has to remember.

Shaped like `model_answer` and `phrase_variant` on purpose: same `status`, `version`,
`audio_ref`. The Q-6 publish path, the admin review surface and the TTS synthesis job all
handle it with no special case. Third time this shape has paid for itself.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0089_m15_officer_ack"
down_revision = "0088_m15_model_answer"
branch_labels = None
depends_on = None

SCHEMA = "m15"


def upgrade() -> None:
    op.create_table(
        "officer_ack",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("locale", sa.String(12), nullable=False, server_default="en"),
        sa.Column("audio_ref", postgresql.UUID(as_uuid=True), nullable=True),
        # the enum already exists (0084) — referencing it, never re-creating it (trap 2)
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
            ["audio_ref"], ["f06.document.id"], name="fk_officer_ack_audio"
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_officer_ack_status", "officer_ack", ["status"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_officer_ack_status", table_name="officer_ack", schema=SCHEMA)
    op.drop_table("officer_ack", schema=SCHEMA)

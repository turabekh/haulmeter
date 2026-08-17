"""AI-CONTEXT: repair branches, a stop that begins and ends, and the officer echoing you.

THREE THINGS, one migration, because they are one complaint: *"still not a real life like
conversation."* Each is specified in E3 and none was built.

**1. `repair_line` — FR2's repair/clarification branches.** E3 §E3.1.2 names them
outright — *"plus repair/clarification branches ('I'm asking where you picked UP this
load')"* — and FR2's own validation requires *"at least one repair branch reached and
recovered from"*. When a driver answers the wrong question, a real officer does not repeat
himself and does not shrug and move on: he says which question he asked. That is the single
most human thing missing from the loop, and entry 184 got it half wrong — a wrong answer
should not get the same question REPEATED, but it should get CLARIFIED, once.

**2. `officer_ack.kind` — a stop that starts and stops.** Real stops open ("Afternoon.
Licence and registration.") and close ("Alright, you're good to go."). The simulation began
mid-interrogation and ended by silently running out of questions. The column reuses the
table rather than adding two more that would be the same shape a fourth and fifth time.

**3. `audio_fragment` — the officer says your city back to you.** E3 budgets for exactly
this: *"only small dynamic slot fragments (names, cities, hours) touch TTS at runtime"*.
"Chicago. Okay." is a different experience from "Okay.", and it is the difference between
a machine that scored you and a person who heard you. CACHED BY TEXT, so "Chicago" is
synthesized once for the life of the product and every later driver who says it pays
nothing — which is what keeps a runtime call inside the latency and COGS budgets.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0090_m15_repair_echo"
down_revision = "0089_m15_officer_ack"
branch_labels = None
depends_on = None

SCHEMA = "m15"


def upgrade() -> None:
    # 1. repair/clarification branches, one pool per intent
    op.create_table(
        "repair_line",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("intent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("locale", sa.String(12), nullable=False, server_default="en"),
        sa.Column("audio_ref", postgresql.UUID(as_uuid=True), nullable=True),
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
            ["intent_id"], [f"{SCHEMA}.intent.id"], name="fk_repair_line_intent"
        ),
        sa.ForeignKeyConstraint(
            ["audio_ref"], ["f06.document.id"], name="fk_repair_line_audio"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_repair_line_intent_status", "repair_line", ["intent_id", "status"], schema=SCHEMA
    )

    # 2. openings and closings, in the table acknowledgements already use.
    # A plain string rather than a PG enum: the set is small, and a new enum type here
    # would be a third `CREATE TYPE` in this schema for no gain (trap 2's neighbourhood).
    op.add_column(
        "officer_ack",
        sa.Column("kind", sa.String(16), nullable=False, server_default="ack"),
        schema=SCHEMA,
    )
    op.create_index("ix_officer_ack_kind", "officer_ack", ["kind", "status"], schema=SCHEMA)

    # 3. the runtime slot-echo cache. UNIQUE on text is the whole design: it is what turns
    # a per-turn TTS call into a once-ever one.
    op.create_table(
        "audio_fragment",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("text", sa.String(200), nullable=False),
        sa.Column("locale", sa.String(12), nullable=False, server_default="en"),
        sa.Column("audio_ref", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("text", "locale", name="uq_audio_fragment_text_locale"),
        sa.ForeignKeyConstraint(
            ["audio_ref"], ["f06.document.id"], name="fk_audio_fragment_audio"
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("audio_fragment", schema=SCHEMA)
    op.drop_index("ix_officer_ack_kind", table_name="officer_ack", schema=SCHEMA)
    op.drop_column("officer_ack", "kind", schema=SCHEMA)
    op.drop_index("ix_repair_line_intent_status", table_name="repair_line", schema=SCHEMA)
    op.drop_table("repair_line", schema=SCHEMA)

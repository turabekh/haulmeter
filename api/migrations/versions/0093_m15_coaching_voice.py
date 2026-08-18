"""AI-CONTEXT: the coaching explanation gets a voice, because reading is not the skill.

WHY A DRIVER NEEDS TO HEAR THIS. M15 teaches English to people whose reading in ANY
language may be weaker than their listening — and the coaching explanation is the one piece
of text in the module written in the driver's own language. A driver who cannot comfortably
read Uzbek gets nothing from an Uzbek paragraph, which makes the whole Q-9 apparatus
(no silent English, an honest "not yet in your language") protect a thing they still cannot
use. E3 §E3.4.2 budgets for this in as many words: "officer AND UZBEK COACH voices".

The column was simply absent. `coaching_content` carried `explanation`, `glosses` and a
review status and no way to attach audio at all — so "Uzbek with voice" was not a content
gap, it was a schema gap, and nothing in the module could have discovered that by running.

THE VOICE IS PER LOCALE AND NOT THE OFFICER'S. The officer speaks US English; an Uzbek
explanation read in `en-US-Ethan` is not accented Uzbek, it is English phonemes applied to
Uzbek words. `audio.coach_voice(locale)` resolves it, and Azure has two native uz-UZ voices
(Sardor, Madina) — checked before this migration was written, because a column for audio we
cannot synthesize would be a promise the vendor does not keep.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0093_m15_coaching_voice"
down_revision = "0092_m15_audio_voice"
branch_labels = None
depends_on = None

SCHEMA = "m15"


def upgrade() -> None:
    op.add_column(
        "coaching_content",
        sa.Column("audio_ref", postgresql.UUID(as_uuid=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_coaching_content_audio",
        "coaching_content",
        "document",
        ["audio_ref"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema="f06",
    )
    # the synthesis job's query: released rows with no voice yet, same shape as every
    # other content table's
    op.create_index(
        "ix_coaching_content_needs_audio",
        "coaching_content",
        ["review_status"],
        schema=SCHEMA,
        postgresql_where=sa.text("audio_ref IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_coaching_content_needs_audio", table_name="coaching_content", schema=SCHEMA)
    op.drop_constraint("fk_coaching_content_audio", "coaching_content", schema=SCHEMA)
    op.drop_column("coaching_content", "audio_ref", schema=SCHEMA)

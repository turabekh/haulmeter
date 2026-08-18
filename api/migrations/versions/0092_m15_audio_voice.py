"""AI-CONTEXT: the runtime audio cache remembers WHICH VOICE said it.

THE BUG THIS PREVENTS IS AUDIBLE, AND IT ARRIVES THE MOMENT ANYONE CHANGES THE VOICE.
`audio_fragment` is a cache keyed on `(text, locale)` — which was right while the voice was
a constant in the adapter. It is now an operator setting (`m15.officer_voice`), chosen by
ear, and the owner has already changed it once. With a text-only key, every sentence
synthesized before the change keeps being served in the OLD voice while new ones arrive in
the new one: an officer who changes voice halfway through a traffic stop.

Nothing would have failed. The cache would have been working exactly as designed, the tests
would have stayed green, and the defect would have been a driver saying "it sounds like two
different people" — the same shape as every other bug this module has had to be told about
by a person rather than by a suite.

The unique constraint moves to `(text, locale, voice)`, so a voice change simply misses the
cache and re-synthesizes. Old rows are backfilled with the voice that actually made them —
`en-US-GuyNeural`, the adapter's hardcoded default before any of this — rather than with
the current setting, because labelling old audio with a voice that did not speak it would
make the cache lie in the one place it is now supposed to tell the truth.
"""

import sqlalchemy as sa
from alembic import op

revision = "0092_m15_audio_voice"
down_revision = "0091_m15_deferred_scoring"
branch_labels = None
depends_on = None

SCHEMA = "m15"

# what the adapter said before `m15.officer_voice` existed; every existing row is this
LEGACY_VOICE = "en-US-GuyNeural"


def upgrade() -> None:
    op.add_column(
        "audio_fragment",
        sa.Column("voice", sa.String(64), nullable=False, server_default=LEGACY_VOICE),
        schema=SCHEMA,
    )
    op.drop_constraint("uq_audio_fragment_text_locale", "audio_fragment", schema=SCHEMA)
    op.create_unique_constraint(
        "uq_audio_fragment_text_locale_voice",
        "audio_fragment",
        ["text", "locale", "voice"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    # a text+locale pair can now legitimately have several rows, one per voice — so the old
    # constraint cannot simply be restored. Keep the newest per pair and drop the rest.
    op.execute(
        f"""
        DELETE FROM {SCHEMA}.audio_fragment a
        USING {SCHEMA}.audio_fragment b
        WHERE a.text = b.text AND a.locale = b.locale AND a.created_at < b.created_at
        """
    )
    op.drop_constraint("uq_audio_fragment_text_locale_voice", "audio_fragment", schema=SCHEMA)
    op.create_unique_constraint(
        "uq_audio_fragment_text_locale", "audio_fragment", ["text", "locale"], schema=SCHEMA
    )
    op.drop_column("audio_fragment", "voice", schema=SCHEMA)

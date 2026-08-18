"""AI-CONTEXT: re-record every released officer line in the CURRENT voice.

WHY THIS EXISTS. The voice used to be a constant inside the adapter; it is now an operator
setting chosen by ear (`m15.officer_voice`). Runtime fragments handle a change on their own
— migration 0092 put the voice in their cache key, so a new voice simply misses and
re-synthesizes. **Released CONTENT does not**: openings, closings, acknowledgements, phrase
variants, model answers and repair lines all carry an `audio_ref` to a file that was
rendered once, by whichever voice was current that day. Change the voice and a stop opens
in one man's voice and continues in another's.

Nothing fails. The rows are valid, the audio plays, the suite is green — and a driver hears
two people. That is the shape of every defect this module has had to be told about by a
person rather than by a test.

WHAT IT DOES: clears `audio_ref` on RELEASED content, which is precisely the condition
`audio.variants_needing_audio` looks for, so the existing `m15_content_audio` worker job
re-renders everything on its next pass. It does not delete the old F6 documents — audio is
retention-managed and orphaning a row is not the same as deciding to destroy it.

DRAFT CONTENT IS LEFT ALONE: it has no audio yet and Q-6 keeps it that way until a human
releases it.
"""

from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.m15_roadside.domain.audio import officer_voice
from app.modules.m15_roadside.domain.enums import ContentStatus
from app.modules.m15_roadside.domain.models import (
    CoachingContent,
    ModelAnswer,
    OfficerAck,
    PhraseVariant,
    RepairLine,
)
from app.wiring import require_object_storage
from db_registry import import_all_models


def main() -> None:
    import_all_models()
    # AI-CONTEXT: a script is not a server. Without this, `default_storage()` is the
    # in-memory fallback and anything written here dies with the process while its
    # database row survives — see `wiring.require_object_storage`.
    require_object_storage("m15_revoice")
    db = SessionLocal()
    try:
        settings = officer_voice(db)
        cleared = {}
        for table in (PhraseVariant, ModelAnswer, OfficerAck, RepairLine):
            rows = list(
                db.scalars(
                    select(table).where(
                        table.status == ContentStatus.released,
                        table.audio_ref.isnot(None),
                    )
                )
            )
            for row in rows:
                row.audio_ref = None
            cleared[table.__name__] = len(rows)
        # AI-CONTEXT: THE COACH WAS LEFT OUT, and its column is why. `CoachingContent`
        # gates on `review_status` rather than `status`, so it falls out of any sweep
        # written as a loop over tables — the same reason `variants_needing_audio` has to
        # name it separately. The consequence was that changing a voice re-recorded the
        # officer and left every explanation in the old one.
        coaching = list(
            db.scalars(
                select(CoachingContent).where(
                    CoachingContent.review_status == ContentStatus.released,
                    CoachingContent.audio_ref.isnot(None),
                )
            )
        )
        for row in coaching:
            row.audio_ref = None
        cleared["CoachingContent"] = len(coaching)
        db.commit()
        print(
            f"voice now: {settings['voice']} "
            f"style={settings['style']!r} rate={settings['rate']!r}"
        )
        for name, n in cleared.items():
            print(f"  {name}: {n} lines queued for re-recording")
        print("the m15_content_audio worker job re-renders them on its next pass (15 min).")
    finally:
        db.close()


if __name__ == "__main__":
    main()

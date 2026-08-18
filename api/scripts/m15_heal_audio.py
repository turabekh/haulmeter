"""AI-CONTEXT: re-queue every released line whose audio bytes are not actually there.

WHY THIS EXISTS — TRAPS 85, TWICE. A synthesis pass run without object storage wired
writes its mp3s into an in-memory dict that dies with the process, and commits the
`audio_ref` anyway. What is left is the worst state this module can be in: the database
says every line is voiced, `variants_needing_audio` therefore returns nothing and the
worker has no work forever, and every play button fetches a key that was never written.

**Nothing is red.** The rows are valid, the suite is green, the admin console shows a full
content pack. Both times it was found by a person tapping a button and hearing silence.

WHAT IT DOES: asks storage for the bytes behind every released `audio_ref` and clears the
ref where they are missing — which is precisely what the `m15_content_audio` worker job
looks for, so the next pass re-renders them properly. It does NOT delete the F6 document
rows: audio is retention-managed, and orphaning a row is not the same as deciding to
destroy it (the rule `m15_revoice` follows).

SAFE ON A HEALTHY BOX. It probes each object rather than clearing everything released, so
a good deployment reports `healed: 0` and spends nothing. Run it anywhere a play button
has gone quiet.
"""

from app.core.db import SessionLocal
from app.modules.m15_roadside.domain.audio import heal_missing_audio
from app.wiring import require_object_storage
from db_registry import import_all_models


def main() -> None:
    import_all_models()
    # AI-CONTEXT: a script is not a server, and this script exists BECAUSE of that
    # difference — running it against the in-memory fallback would report every object
    # missing and clear every ref on the box.
    require_object_storage("m15_heal_audio")
    db = SessionLocal()
    try:
        summary = heal_missing_audio(db)
        db.commit()
        print(f"checked {summary['checked']} released lines")
        print(f"  {summary['healed']} had no bytes and are queued for re-recording")
        if summary["healed"]:
            print("the m15_content_audio worker job re-renders them on its next pass.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

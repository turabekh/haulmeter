"""AI-CONTEXT: live key smoke for M15's three providers (E3 §E3.4, Session B step 2).

DELIBERATELY NOT A TEST. It reaches three paid APIs over the public internet, so it runs
when someone asks for it (`make m15-key-smoke`) and never inside `make ci` — a suite that
fails when the wifi does is a suite people learn to ignore.

The Deepgram half feeds it the audio Azure just produced, which makes it a round trip
rather than two unrelated pings: if the synthesized officer line comes back as text, both
providers work AND they work on each other's formats — which is the actual integration
question, and the one a fixture clip could not answer.

Every audio call is metered through F9 so the budget rows exist from the first minute
(E3 §E3.4.4, the F-17 invariant).
"""

import os
import pathlib
import sys

from db_registry import import_all_models

import_all_models()

from app.core.db import SessionLocal  # noqa: E402
from app.foundation.f01_identity.domain import telegram  # noqa: E402
from app.foundation.f09_ai_gateway import public as ai  # noqa: E402
from app.foundation.f09_ai_gateway.domain import speech  # noqa: E402
from app.foundation.f09_ai_gateway.domain.enums import AiTask  # noqa: E402

OUT = pathlib.Path(os.environ.get("SMOKE_OUT", "/repo/docs/voice-samples"))

OFFICER_LINE_EN = "Good afternoon. Where are you headed today?"
COACH_LINE_UZ = (
    "Ofitser sizdan qayerga ketayotganingizni so'rayapti. "
    "Shahar nomini ayting: masalan, Chicago."
)
VOICES = [
    ("officer_en", "en-US", "en-US-GuyNeural", OFFICER_LINE_EN),
    ("coach_uz_sardor", "uz-UZ", "uz-UZ-SardorNeural", COACH_LINE_UZ),
    ("coach_uz_madina", "uz-UZ", "uz-UZ-MadinaNeural", COACH_LINE_UZ),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    ai.set_module_budget(db, "m15", 25_000_000)
    db.commit()
    failures = []

    # --- Telegram: read-only identity, no sends ------------------------------------
    print("== TELEGRAM getMe (read-only, no sends) ==")
    try:
        import httpx

        token = telegram._bot_token()
        r = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=30.0)
        r.raise_for_status()
        me = r.json()["result"]
        print(f"  OK  bot id={me['id']} username=@{me.get('username')} "
              f"is_bot={me.get('is_bot')} can_join_groups={me.get('can_join_groups')}")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"telegram: {exc}")
        print(f"  FAIL {exc}")

    # --- Azure TTS: three clips ------------------------------------------------------
    print("== AZURE TTS ==")
    clips = {}
    try:
        tts = speech.resolve_tts()
        for name, locale, voice, text in VOICES:
            audio = tts.synthesize(text, locale=locale, voice=voice)
            path = OUT / f"{name}.mp3"
            path.write_bytes(audio)
            clips[name] = audio
            minutes = max(len(text) / 900.0, 0.02)
            cost = speech.record_audio_minutes(db, "m15", AiTask.tts, minutes)
            # AI-CONTEXT: NOT stored in F6 here. Content audio is permanent-class and
            # belongs to a released phrase variant; these three clips exist for the
            # owner's native spot-check, and storing spot-check output as content is how
            # an unreviewed Uzbek voice would end up attached to a driver-facing line.
            print(f"  OK  {name:18s} voice={voice:22s} bytes={len(audio):7d} "
                  f"cost_micros={cost} -> {path}")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"azure tts: {exc}")
        print(f"  FAIL {exc}")

    # --- Deepgram: transcribe the officer line Azure just produced -------------------
    print("== DEEPGRAM STT (round trip on the Azure clip) ==")
    try:
        stt = speech.resolve_stt()
        audio = clips.get("officer_en")
        if audio is None:
            raise RuntimeError("no Azure clip to transcribe — TTS failed above")
        transcript, confidence = stt.transcribe(audio, locale="en")
        cost = speech.record_audio_minutes(db, "m15", AiTask.stt, 0.05)
        print(f"  spoken : {OFFICER_LINE_EN!r}")
        print(f"  heard  : {transcript!r}")
        print(f"  OK  confidence={confidence:.3f} cost_micros={cost}")
        if not transcript.strip():
            failures.append("deepgram: empty transcript")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"deepgram: {exc}")
        print(f"  FAIL {exc}")

    db.commit()

    # --- the budget rows, queried ------------------------------------------------------
    print("== F9 BUDGET ROWS (queried, not assumed) ==")
    used = ai.budget_used(db, "m15")
    print(f"  m15 budget_used_micros={used}  remaining={ai.budget_remaining(db, 'm15')}")
    db.close()

    print()
    if failures:
        print("SMOKE FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"SMOKE PASSED — voice samples in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

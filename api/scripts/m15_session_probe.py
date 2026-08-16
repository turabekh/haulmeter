"""AI-CONTEXT: the Session-B DoD observation — a full session with REAL speech.

WHAT THIS PROVES, and what it deliberately does not.

It drives `domain/session_loop` end to end as a GUEST principal against the DEV_SEED draft
scenario, using both real providers: Azure synthesizes each driver answer, Deepgram
transcribes it back. So the transcripts scored here were never typed — they went out as
audio and came back as text, which is the only way "the branch followed their actual
answer" means anything.

It does NOT go through the WebSocket, and the reason is a rule rather than a shortcut:
`m15_roadside` must stay `enabled IS NULL` this session, and every HTTP route is gated on
that flag. Exercising the socket would mean switching the module on, which is the owner's
decision and not a probe's. The socket's own coverage is an integration test with the
module dependency overridden — named in the handoff so nobody mistakes one for the other.

Latency is measured around the part a driver waits for: transcribe + score. Synthesis of
the ANSWER is excluded because a real driver's mouth is not on our latency budget.
"""

import os
import pathlib
import statistics
import sys
import uuid

from db_registry import import_all_models

import_all_models()

from app.core.db import SessionLocal  # noqa: E402
from app.foundation.f01_identity.domain import guests  # noqa: E402
from app.foundation.f09_ai_gateway.domain import speech  # noqa: E402
from app.foundation.f09_ai_gateway.domain.enums import AiTask  # noqa: E402
from app.modules.m15_roadside.domain import models as m  # noqa: E402
from app.modules.m15_roadside.domain import session_loop as loop  # noqa: E402
from app.modules.m15_roadside.domain.scoring import DeterministicRubric  # noqa: E402

OUT = pathlib.Path(os.environ.get("PROBE_OUT", "/repo/docs/voice-samples/session"))

# what the "driver" says to each intent, spoken aloud through Azure and heard by Deepgram
ANSWERS = {
    "destination": "I am going to Chicago",
    "hos_hours_driven": "I have been driving six hours today",
    "logbook_request": "Yes here is my logbook",
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    import time

    scenario = (
        db.query(m.ScenarioVersion)
        .filter(m.ScenarioVersion.status == m.ContentStatus.draft)
        .order_by(m.ScenarioVersion.created_at.desc())
        .first()
    )
    if scenario is None:
        print("FAIL no DEV_SEED scenario — run `make seed` first")
        return 1

    principal = guests.issue_guest(db, "m15")
    session = loop.start_session(
        db, scenario=scenario, guest_token=principal.token, consented=True,
        driver_state=loop.DriverState.IDLE,
    )
    db.commit()
    print(f"session={session.id} guest={principal.token}")
    print(f"scenario={scenario.id} status={scenario.status.value} "
          f"intents={scenario.allowed_intents}")

    tts = speech.resolve_tts()
    stt = speech.resolve_stt()
    latencies = []
    rubric = DeterministicRubric()

    while True:
        officer = loop.next_officer_turn(db, session, allow_draft=True)
        if officer is None:
            break
        print(f"\n-- turn {officer.seq}: [{officer.intent_key}] {officer.text!r}")

        spoken = ANSWERS.get(officer.intent_key, "I do not understand")
        audio = tts.synthesize(spoken, locale="en-US", voice="en-US-GuyNeural")
        (OUT / f"answer_{officer.seq}.mp3").write_bytes(audio)

        # the clock covers exactly what a driver waits for
        started = time.perf_counter()
        transcript, confidence = stt.transcribe(audio, locale="en")
        turn = loop.record_driver_turn(
            db, session, officer=officer, transcript=transcript,
            asr_confidence=confidence, rubric=rubric,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        latencies.append(elapsed_ms)

        speech.record_audio_minutes(db, "m15", AiTask.stt, max(len(audio) / 320_000.0, 0.02))
        db.commit()
        print(f"   spoke : {spoken!r}")
        print(f"   heard : {transcript!r} (conf {confidence:.3f})")
        print(f"   slots : {turn.observed_slots}  tags={turn.failure_tags}")
        print(f"   scores: {turn.scores}")
        print(f"   latency: {elapsed_ms:.0f} ms")

    verdict = loop.complete_session(db, session)
    db.commit()

    print("\n== RESULT ==")
    print(f"  band={verdict.band.value} provisional={verdict.provisional} "
          f"label_key={verdict.label_key}")
    print(f"  score={verdict.score} agreement={verdict.agreement_pct} "
          f"sample={verdict.sample_size}")
    print(f"  review_needed_turns={loop.review_needed_count(db, session)}")

    if latencies:
        ordered = sorted(latencies)
        p75 = statistics.quantiles(ordered, n=4)[2] if len(ordered) > 1 else ordered[0]
        p95 = ordered[min(int(len(ordered) * 0.95), len(ordered) - 1)]
        print("\n== LATENCY (transcribe + score; answer synthesis excluded) ==")
        print(f"  n={len(latencies)} raw_ms={[round(x) for x in ordered]}")
        print(f"  p75={p75:.0f} ms  (budget 1300)  {'MET' if p75 <= 1300 else 'MISSED'}")
        print(f"  p95={p95:.0f} ms  (budget 1800)  {'MET' if p95 <= 1800 else 'MISSED'}")

    # --- the claim, so the guest's work survives ---------------------------------------
    from app.foundation.f01_identity import public as identity
    from app.modules.m15_roadside import public as m15

    email = f"probe-{uuid.uuid4().hex[:8]}@example.com"
    account = identity.register_account(db, email, "pw-123456")
    db.flush()
    guests.claim_guest(db, principal.token, account.id)
    moved = m15.claim_guest_sessions(db, principal.token, account.id)
    db.commit()
    print(f"\n== CLAIM ==\n  account={account.id} sessions_moved={moved}")
    print(f"\nPROBE_SESSION_ID={session.id}")
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""AI-CONTEXT: M15's HTTP + WebSocket surface (M15-FR3, E3 §E3.1.5).

THIS IS THE FIRST WEBSOCKET IN THIS CODEBASE, and the two things that make it survivable
were both learned by `events.py` doing them the hard way over SSE.

**1. THE DATABASE SESSION IS NOT HELD OPEN FOR THE SOCKET'S LIFE.** `events.py` records the
outage this prevents — "QueuePool limit of size 5 overflow 10 reached" — from holding a
pooled connection across a long-lived response. A roadside session lasts minutes, so a
`Depends(get_db)` here would pin one connection per talking driver and exhaust the pool at
about a dozen of them. Every turn opens a session, does its work, commits and closes.

**2. A BROWSER CANNOT SET HEADERS ON A WEBSOCKET.** Same constraint EventSource has, same
resolution, and the same cost recorded rather than hidden: the token rides the query
string, where it reaches access logs. `events.py` §23 entry 103 names the upgrade — a
single-use stream ticket — and it applies here identically when this leaves testing.

WHAT THE SOCKET DOES NOT DO: it does not score, branch, or decide anything. Every one of
those lives in `domain/session_loop.py` and is tested without a socket. This file moves
frames and translates exceptions into close codes, so a latency problem in the transport
can never quietly become a scoring problem.
"""

from __future__ import annotations

import base64
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from app.api.deps import current_account, get_db, require_module
from app.api.media import KIND_DOCUMENT, SIZE_FULL, media_url
from app.core.db import SessionLocal
from app.foundation.f01_identity import public as identity
from app.foundation.f09_ai_gateway.domain import speech
from app.foundation.f09_ai_gateway.domain.enums import AiTask
from app.modules.m15_roadside import public as m15
from app.modules.m15_roadside.domain import session_loop as loop
from app.modules.m15_roadside.domain.rubric_f9 import F9Rubric, RubricUnavailable

router = APIRouter(
    prefix="/roadside",
    tags=["roadside"],
    # PRD §6: the module's own flag gates every route (§23 entry 105)
    dependencies=[Depends(require_module("m15_roadside"))],
)

# close codes. 4001-4999 is the application range; each names a REASON a driver's client
# can act on differently, because "the socket closed" is not an instruction.
CLOSE_NO_CONSENT = 4001
CLOSE_DRIVING = 4002
CLOSE_NO_CONTENT = 4003
CLOSE_BAD_SESSION = 4004


@router.get("/scenarios")
def scenarios(db: Session = Depends(get_db)) -> dict:
    """What a driver may be offered, and the only way a client can learn a scenario id.

    AI-CONTEXT: this route did not exist and the surface could not have. `POST /session`
    takes a `scenario_version_id`, and the only thing that had ever supplied one was the
    dev probe, which queries the database directly. A driver app has no database.

    `startable_scenarios` is the whole policy and it lives in `domain/content.py` beside
    Q-5 and Q-6 rather than here — an endpoint that filtered content itself would be a
    second place for those laws to be decided, which is the shape of the defect this
    module already had once (entry 180).

    AN EMPTY LIST IS THE EXPECTED ANSWER TODAY and is not an error: no content has been
    through review yet. The surface renders its empty state, which is the honest thing to
    show, and a 404 here would say "no such feature" about a feature that exists and has
    nothing reviewed in it.
    """
    from app.modules.m15_roadside.domain import content

    return {
        "scenarios": [
            {
                "id": str(s.id),
                "difficulty": s.difficulty.value,
                "intents": list(s.allowed_intents or []),
            }
            for s in content.startable_scenarios(db)
        ]
    }


@router.post("/session", status_code=status.HTTP_201_CREATED)
def open_session(
    body: dict,
    db: Session = Depends(get_db),
    account: identity.Account | None = Depends(current_account),
) -> dict:
    """Open a session for a guest or an authenticated driver.

    AI-CONTEXT: consent is a REQUEST FIELD rather than a stored preference, and that is
    M15-FR3 read strictly. Consent is given for a recording, not once for all time, so it
    travels with the thing being consented to.
    """
    scenario = db.get(m15.ScenarioVersion, uuid.UUID(str(body["scenario_version_id"])))
    if scenario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such scenario")

    guest_token = body.get("guest_token")
    try:
        session = loop.start_session(
            db,
            scenario=scenario,
            account_id=account.id if account else None,
            guest_token=uuid.UUID(str(guest_token)) if guest_token else None,
            consented=bool(body.get("consented")),
            driver_state=loop.DriverState(body.get("driver_state", "IDLE")),
        )
    except loop.ConsentRequired as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except loop.RefusedInMotion as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    db.commit()
    return {"session_id": str(session.id), "consent_at": session.consent_at.isoformat()}


@router.get("/session/{session_id}/result")
def session_result(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    account: identity.Account | None = Depends(current_account),
) -> dict:
    """The result surface's data. The band ALWAYS carries its provisional state (Q-8)."""
    session = db.get(m15.Session, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such session")

    from app.modules.m15_roadside.domain.diagnosis import band_for

    turns = [t for t in _driver_turns(db, session_id)]
    verdict = band_for(db, [t.scores for t in turns if t.scores])
    return {
        "session_id": str(session.id),
        "band": verdict.band.value,
        "provisional": verdict.provisional,
        # AI-CONTEXT: `label_key` rather than a rendered string, and no naked percentage.
        # E3 §E3.1.4 forbids the percentage because it invites comparison on a scale
        # nobody has calibrated — which is the same reason `provisional` exists.
        "label_key": verdict.label_key,
        "agreement_pct": verdict.agreement_pct,
        "review_needed_turns": loop.review_needed_count(db, session),
        "failure_tags": sorted({tag for t in turns for tag in (t.failure_tags or [])}),
    }


@router.get("/session/{session_id}/coaching")
def session_coaching(
    session_id: uuid.UUID,
    locale: str = "en",
    db: Session = Depends(get_db),
) -> dict:
    """The teaching loop's material for every miss in a session (M15-FR5).

    AI-CONTEXT: `locale` is a QUERY PARAMETER rather than an account preference, because
    the driver who most needs coaching in Uzbek is the one who has not made an account
    yet — a guest. The client already knows which language it is rendering in.

    `explanation: null` is Q-9 and the surface must render it as "not yet in your
    language", never by falling back to the English row. That decision is made in
    `coaching.py`; this route only carries it.
    """
    from app.modules.m15_roadside.domain import coaching

    session = db.get(m15.Session, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such session")

    plans = []
    for turn in _driver_turns(db, session_id):
        plan = coaching.coaching_for(db, turn=turn, locale=locale)
        if plan is None:
            continue
        plans.append({
            "intent_key": plan.intent_key,
            "missed_question": plan.missed_question,
            "missed_question_audio": _audio_url(plan.missed_question_audio),
            "explanation": plan.explanation,
            "glosses": plan.glosses,
            "phrase_family": [
                {"text": v.text, "audio_url": _audio_url(v.audio_ref)} for v in plan.phrase_family
            ],
            "model_answer": plan.model_answer,
            "model_answer_audio": _audio_url(plan.model_answer_audio),
            "retest_variant_id": str(plan.retest_variant_id) if plan.retest_variant_id else None,
            "retest_question": plan.retest_question,
        })
    return {"coaching": plans}


@router.post("/coaching/{variant_id}/attempt")
def coaching_attempt(
    variant_id: uuid.UUID,
    body: dict,
    db: Session = Depends(get_db),
    account: identity.Account | None = Depends(current_account),
) -> dict:
    """The retest at the end of the loop. Scores one spoken attempt and records practice.

    AI-CONTEXT: NO SLOT CHECKING, and that is not laziness. Slots are resolved from a
    scenario's hidden state — "six hours" is correct because THIS scenario says so — and a
    retest happens outside any scenario. Asking whether the driver produced a fact nobody
    gave them would fail every attempt. What is being retested is the thing that was
    missed: did they understand the question and answer it.

    A GUEST GETS SCORED AND RECORDS NOTHING (`record_practice` returns None). That is the
    schema being honest — skill state belongs to a person — and the result surface already
    offers the claim that turns their work into a record.
    """
    from app.modules.m15_roadside.domain import coaching
    from app.modules.m15_roadside.domain.scoring import score_turn

    variant = db.get(m15.PhraseVariant, variant_id)
    if variant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such phrasing")

    audio = base64.b64decode(body.get("audio_b64") or "")
    if audio:
        stt = speech.resolve_stt()
        transcript, confidence = stt.transcribe(audio, locale="en")
        speech.record_audio_minutes(db, "m15", AiTask.stt, max(len(audio) / 320_000.0, 0.02))
    else:
        transcript = body.get("transcript") or ""
        confidence = float(body.get("confidence", 0.9))

    intent = db.get(m15.Intent, variant.intent_id)
    try:
        rubric = F9Rubric(db, account_id=account.id if account else None)
        scored = score_turn(
            officer_line=variant.text,
            transcript=transcript,
            intent_key=intent.key,
            expected_slots={},
            asr_confidence=confidence,
            rubric=rubric,
        )
    except RubricUnavailable:
        # the same refusal the session makes: no verdict is invented about a driver
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "scoring unavailable") from None

    passed = bool(scored.scores) and scored.scores.get("comprehension", 0) > 0
    coaching.record_practice(
        db,
        account_id=account.id if account else None,
        variant_id=variant.id,
        success=passed,
    )
    db.commit()
    return {
        "transcript": transcript,
        "passed": passed,
        "review_needed": scored.review_needed,
        "recorded": account is not None,
    }


def _audio_url(ref):
    return media_url(KIND_DOCUMENT, ref, size=SIZE_FULL) if ref else None


def _driver_turns(db: Session, session_id):
    from sqlalchemy import select

    return list(
        db.scalars(
            select(m15.Turn)
            .where(m15.Turn.session_id == session_id, m15.Turn.speaker == m15.Speaker.driver)
            .order_by(m15.Turn.seq)
        )
    )


@router.websocket("/session/{session_id}/stream")
async def session_stream(websocket: WebSocket, session_id: uuid.UUID) -> None:
    """The live loop. One frame in, one frame out, one database session per turn.

    Protocol, deliberately small:
      client -> {"type": "ready", "driver_state": "IDLE"}      ask for the next officer line
      server -> {"type": "officer", "text", "audio_url", "seq", "intent_key"}
      client -> {"type": "answer", "audio_b64", "driver_state"}
      server -> {"type": "scored", "transcript", "confidence", "tags", "review_needed",
                 "latency_ms"}
      server -> {"type": "complete", "band", "provisional", "label_key"}

    AI-CONTEXT: `latency_ms` is measured HERE, at the server boundary, and reported to the
    client rather than logged — the p75/p95 budget in M15-FR3 is about what a driver
    perceives, and a number the server keeps to itself cannot be checked against that.
    The probe reads these frames.
    """
    await websocket.accept()
    try:
        while True:
            message = await websocket.receive_json()
            kind = message.get("type")

            if kind == "ready":
                if not await _officer_frame(websocket, session_id, message):
                    return
            elif kind == "answer":
                if not await _answer_frame(websocket, session_id, message):
                    return
            elif kind == "bye":
                await websocket.close()
                return
            else:
                await websocket.send_json({"type": "error", "detail": f"unknown frame {kind!r}"})
    except WebSocketDisconnect:
        return


async def _officer_frame(websocket: WebSocket, session_id, message) -> bool:
    """Send the next officer line, or close. Opens and closes its own DB session."""
    db = SessionLocal()
    try:
        session = db.get(m15.Session, session_id)
        if session is None:
            await websocket.close(code=CLOSE_BAD_SESSION)
            return False
        try:
            # AI-CONTEXT: `allow_draft` IS NOT READ FROM THE FRAME, and this line used to
            # read it. The dev seam's entire safety is that nothing in the request path
            # passes it — `session_loop.py` says so in its docstring and
            # `test_session_loop.py` asserts the domain DEFAULT, which cannot testify
            # about what an HTTP layer chooses to pass. This layer was passing it, off
            # the client's own JSON, so any browser could ask for unreleased content and
            # be served it. Q-6 is "content ships reviewed or not at all"; F9 drafts the
            # text, and a client-set boolean turned the review pipeline into a
            # suggestion. The refusal now belongs to the server in every case.
            officer = loop.next_officer_turn(
                db,
                session,
                driver_state=loop.DriverState(message.get("driver_state", "IDLE")),
            )
        except loop.RefusedInMotion:
            db.commit()
            await websocket.close(code=CLOSE_DRIVING)
            return False
        except loop.NoContentAvailable:
            await websocket.close(code=CLOSE_NO_CONTENT)
            return False

        if officer is None:
            verdict = loop.complete_session(db, session)
            db.commit()
            await websocket.send_json({
                "type": "complete",
                "band": verdict.band.value,
                "provisional": verdict.provisional,
                "label_key": verdict.label_key,
            })
            return True

        db.commit()
        await websocket.send_json({
            "type": "officer",
            "seq": officer.seq,
            "intent_key": officer.intent_key,
            "text": officer.text,
            # AI-CONTEXT: cached audio is referenced, never streamed through this socket.
            # E3 §E3.1.2 is explicit that pre-synthesized officer audio is what holds the
            # simulation to sub-1.3s and ~$0.10 COGS; pushing bytes down the control
            # channel would put synthesis latency inside the turn.
            #
            # THE URL MUST BE SIGNED. This was a hand-built `/media/document/{ref}` with no
            # `exp` and no `sig`, and `serve_media` requires both — so the moment any line
            # had audio, the player would have got a 422 instead of a voice. It could not be
            # seen because `audio_ref` has been null on every row that ever existed: the
            # synthesis path is still a named remainder. `media_url` is the only correct way
            # to address F6, and SIZE_FULL because there is no such thing as a thumbnail of
            # a recording.
            "audio_url": (
                media_url(KIND_DOCUMENT, officer.audio_ref, size=SIZE_FULL)
                if officer.audio_ref
                else None
            ),
        })
        return True
    finally:
        db.close()


async def _answer_frame(websocket: WebSocket, session_id, message) -> bool:
    """Transcribe, score, reply. The latency clock covers exactly what the driver waits for."""
    started = time.perf_counter()
    db = SessionLocal()
    try:
        session = db.get(m15.Session, session_id)
        if session is None:
            await websocket.close(code=CLOSE_BAD_SESSION)
            return False

        driver_state = loop.DriverState(message.get("driver_state", "IDLE"))
        try:
            loop.assert_may_continue(driver_state)
        except loop.RefusedInMotion:
            await websocket.close(code=CLOSE_DRIVING)
            return False

        officer = _last_officer(db, session_id)
        if officer is None:
            await websocket.send_json({"type": "error", "detail": "no officer turn to answer"})
            return True

        audio = base64.b64decode(message.get("audio_b64") or "")
        transcript, confidence = "", 0.0
        if audio:
            stt = speech.resolve_stt()
            transcript, confidence = stt.transcribe(audio, locale="en")
            speech.record_audio_minutes(db, "m15", AiTask.stt, max(len(audio) / 320_000.0, 0.02))
        else:
            transcript = message.get("transcript") or ""
            confidence = float(message.get("confidence", 0.9))

        # AI-CONTEXT: a rubric that cannot answer produces REVIEW_NEEDED, not a verdict.
        # `RubricUnavailable` is raised for an outage, an exhausted budget or unreadable
        # output — and every one of those would otherwise become a statement about this
        # driver's English invented by an accident.
        try:
            rubric = F9Rubric(db, account_id=session.account_id)
            turn = loop.record_driver_turn(
                db, session, officer=officer, transcript=transcript,
                asr_confidence=confidence, rubric=rubric,
            )
        except RubricUnavailable:
            turn = loop.record_driver_turn(
                db, session, officer=officer, transcript=transcript,
                asr_confidence=0.0, rubric=_ReviewOnly(),
            )
        db.commit()

        await websocket.send_json({
            "type": "scored",
            "seq": turn.seq,
            "transcript": transcript,
            "confidence": confidence,
            "tags": turn.failure_tags or [],
            "review_needed": turn.review_status.value == "review_needed",
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        })
        return True
    finally:
        db.close()


class _ReviewOnly:
    """Forces a turn into REVIEW_NEEDED without opining about the driver."""

    def judge(self, *, officer_line, transcript, intent_key):
        from app.modules.m15_roadside.domain.scoring import RubricVerdict

        return RubricVerdict(intent_matched=False, intelligible=True)


def _last_officer(db: Session, session_id):
    from sqlalchemy import select

    row = db.scalar(
        select(m15.Turn)
        .where(m15.Turn.session_id == session_id, m15.Turn.speaker == m15.Speaker.officer)
        .order_by(m15.Turn.seq.desc())
        .limit(1)
    )
    if row is None:
        return None
    intent = db.get(m15.Intent, row.intent_id) if row.intent_id else None
    return loop.OfficerTurn(
        intent_key=intent.key if intent else "",
        variant_id=None,
        text=row.transcript or "",
        audio_ref=row.audio_ref,
        seq=row.seq,
    )

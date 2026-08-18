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
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_account, get_db, require_module
from app.api.media import KIND_DOCUMENT, SIZE_FULL, media_url
from app.core.db import SessionLocal
from app.foundation.f01_identity import public as identity
from app.foundation.f06_documents import public as documents
from app.foundation.f09_ai_gateway.domain import speech
from app.foundation.f09_ai_gateway.domain.enums import AiTask
from app.modules.m15_roadside import public as m15
from app.modules.m15_roadside.domain import audio as m15_audio
from app.modules.m15_roadside.domain import conversation
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

    from app.modules.m15_roadside.domain.deferred_scoring import settle_session_scores
    from app.modules.m15_roadside.domain.diagnosis import band_for

    # AI-CONTEXT: the result screen is the reader that MUST NOT see a partial set. Turns
    # are scored off the conversation path (3.41s of every exchange, measured), so a
    # session can reach this endpoint with the model's judgement still owed on some of
    # them. Settling here rather than trusting the worker is what makes the deferral safe:
    # a worker that is down makes this slower, never wrong.
    if settle_session_scores(db, session):
        db.commit()

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


@router.get("/drill/today")
def drill_today(
    db: Session = Depends(get_db),
    account: identity.Account | None = Depends(current_account),
) -> dict:
    """Today's drill (M15-FR6). A guest gets an honest empty answer, not a 403.

    AI-CONTEXT: `plan: null` covers three different situations on purpose — a guest, a
    driver with nothing due, and a driver who has finished today. The surface distinguishes
    them from what it already knows (is anyone signed in, was the day completed), and none
    of the three is an error worth a status code.

    NO REMINDER IS SENT FROM ANYWHERE. P-1 `readiness_reminder` is an unsigned owner fork
    (entry 177): a driver who opens the app finds their drill, and a driver who does not is
    the half that waits for that signature.
    """
    from app.modules.m15_roadside.domain import drills

    plan = drills.todays_drill(db, account.id if account else None)
    if plan is None:
        return {"plan": None}

    items = []
    for raw in plan.items.get("variant_ids", []):
        variant = db.get(m15.PhraseVariant, uuid.UUID(raw))
        if variant is None:
            continue
        items.append({
            "variant_id": str(variant.id),
            "text": variant.text,
            "audio_url": _audio_url(variant.audio_ref),
        })
    db.commit()
    return {
        "plan": {
            "id": str(plan.id),
            "day": plan.plan_day,
            "completed": plan.completed_at is not None,
            "items": items,
        }
    }


@router.post("/drill/{plan_id}/complete")
def drill_complete(
    plan_id: uuid.UUID,
    db: Session = Depends(get_db),
    account: identity.Account | None = Depends(current_account),
) -> dict:
    from app.modules.m15_roadside.domain import drills

    plan = db.get(m15.DrillPlan, plan_id)
    if plan is None or account is None or plan.account_id != account.id:
        # a plan belongs to one driver; not-yours and not-there are the same answer
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such plan")
    drills.complete_drill(db, plan)
    db.commit()
    return {"id": str(plan.id), "completed": True}


def _audio_url(ref):
    return media_url(KIND_DOCUMENT, ref, size=SIZE_FULL) if ref else None


def _audio_inline(db, ref) -> str | None:
    """The audio BYTES, base64, for a socket that is already open.

    AI-CONTEXT: THE LARGEST REMAINING LATENCY WAS NOT ON THE SERVER AT ALL. Measured from a
    client on the other side of the world: the `officer_audio` frame arrived at 1.93s, and
    the browser then spent **1050ms fetching the mp3** — a fresh DNS/TCP/TLS/HTTP round
    trip, plus signed-URL validation, for 17KB — before a single sound came out. Real time
    to first speech was ~3.0s while every server-side number said 1.9s.

    The WebSocket is already open, already authenticated and already carrying the sentence.
    Sending the bytes down it costs ~23KB of base64 and removes the round trip completely.
    `audio_url` still rides along: it is what the retention story and the replay affordances
    are built on, and a client that cannot decode inline audio still has something to fetch.
    """
    if ref is None:
        return None
    try:
        document = db.get(documents.Document, ref)
        if document is None:
            return None
        blob = documents.get_document_bytes(db, document)
    except Exception:
        # a voice that cannot be read inline is not worth failing a turn over — the frame
        # still carries `audio_url`, which is the path that already worked
        return None
    return base64.b64encode(blob).decode() if blob else None


def _thinking_urls(db, seq: int) -> list[str] | None:
    """The officer's listening noises, handed over ONCE at the start of the stop.

    AI-CONTEXT: sent with the FIRST officer frame only. These cover the ~1.5s between a
    driver falling silent and the officer speaking, so a clip fetched at the moment it is
    needed would arrive exactly too late to be the thing that covers the wait. The client
    holds the pool and picks one itself the instant the microphone closes.
    """
    if seq > 1:
        return None
    return [
        url for url in (_audio_url(line.audio_ref) for line in loop.thinking_lines(db)) if url
    ]


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
        # AI-CONTEXT: THE IMPROVISING OFFICER (entry 189). The model chooses what is said;
        # everything about what it is WORTH stays where it was. If it is unavailable, over
        # budget or unparseable we fall through to the scripted loop rather than to
        # silence — a driver mid-stop gets a stiffer officer, not a dead screen, and the
        # scripted path is fully reviewed content that always works.
        if conversation.officer_mode(db) == "llm":
            try:
                improvised = conversation.conversational_officer(db, session)
            except conversation.OfficerUnavailable:
                improvised = None
            if improvised is not None:
                if improvised.done:
                    verdict = loop.complete_session(db, session)
                    db.commit()
                    # AI-CONTEXT: A SYNTHESIS FAILURE HERE USED TO EAT THE VERDICT. The
                    # closing frame is the only thing that sends a driver to their result
                    # screen, and it was built with an unguarded `fragment_audio` call
                    # inline in the dict — so Azure failing on the last line of the stop
                    # raised out of the handler, the frame never went, and the socket
                    # closed. The surface reads an unexpected close as FAILED. Their score
                    # was already committed one line above: a finished stop, a saved
                    # verdict, and a failure screen. A missing voice costs the closing
                    # words, never the result.
                    #
                    # This branch stays ONE frame deliberately, unlike the turn below.
                    # The closing frame is what triggers navigation, so splitting it would
                    # leave a driver on the closing screen if the audio frame never
                    # arrived — trading ~1.2s once, at the end, for a way to strand
                    # someone on the screen before their results. Not worth it.
                    try:
                        closing_audio_url = _audio_url(
                            m15_audio.fragment_audio(db, improvised.line)
                        )
                        db.commit()
                    except Exception:
                        db.rollback()
                        closing_audio_url = None
                    await websocket.send_json({
                        "type": "complete",
                        "band": verdict.band.value,
                        "provisional": verdict.provisional,
                        "label_key": verdict.label_key,
                        "closing": improvised.line,
                        "closing_audio_url": closing_audio_url,
                    })
                    return True

                turn = loop.record_improvised_officer_turn(db, session, improvised)
                db.commit()
                # AI-CONTEXT: THE LINE GOES BEFORE THE VOICE. Measured on the box, not
                # guessed and not measured from a laptop: the model takes 3.0–4.5s to
                # choose the line and Azure 0.25s to say it (0 when `fragment_audio`
                # hits the text cache, which repeated lines do). So this split buys about
                # a quarter second, NOT the 1.2s an earlier version of this comment
                # claimed from a laptop in Tashkent — the box sits next door to Azure.
                #
                # It is kept on correctness rather than that quarter second: before it, a
                # TTS failure took the whole turn down with it. The turn's real cost is
                # the model, and only a different model changes that (entry 190).
                #
                # So the text ships the moment it exists and the audio follows on its own
                # frame. `audio_pending` is what stops the surface treating "no audio_url"
                # as "he has finished speaking" and opening the mic over the top of him —
                # a driver would be recorded answering a question they had not yet heard.
                # (Short recurring lines like "Alright." do still hit the text cache; the
                # long ones a driver actually waits on generally do not.)
                await websocket.send_json({
                    "type": "officer",
                    "seq": turn.seq,
                    "intent_key": improvised.intent_key,
                    "text": improvised.line,
                    "audio_url": None,
                    "audio_pending": True,
                    "opening": None,
                    "opening_audio_url": None,
                    "thinking_audio_urls": _thinking_urls(db, turn.seq),
                })
                try:
                    audio_ref = m15_audio.fragment_audio(db, improvised.line)
                    db.commit()
                    audio_url = _audio_url(audio_ref)
                except Exception:
                    # AI-CONTEXT: a voice that fails must not leave the driver waiting for
                    # one. The line is already on their screen; sending this frame anyway
                    # is what releases the mic. Silence with a question showing beats a
                    # live mic that never opens.
                    db.rollback()
                    audio_url = None
                await websocket.send_json({
                    "type": "officer_audio",
                    "seq": turn.seq,
                    "audio_url": audio_url,
                    # the bytes themselves, so the browser does not spend a second
                    # fetching them over a fresh connection before it can make a sound
                    "audio_b64": _audio_inline(db, audio_ref) if audio_url else None,
                })
                return True

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
            # AI-CONTEXT: a stop ENDS. It used to stop by running out of questions, which
            # is how a form ends, not how a person lets you go.
            closing = loop.pick_line(db, "closing")
            db.commit()
            await websocket.send_json({
                "type": "complete",
                "band": verdict.band.value,
                "provisional": verdict.provisional,
                "label_key": verdict.label_key,
                "closing": closing.text if closing else None,
                "closing_audio_url": _audio_url(closing.audio_ref) if closing else None,
            })
            return True

        # AI-CONTEXT: the greeting rides the FIRST officer frame. It used to come back from
        # `POST /session`, which is answered on the CONSENT screen — so a driver would have
        # heard "Afternoon" while still deciding whether to agree to be recorded, and the
        # session surface never received it at all. One source, and it is the one the
        # driver is looking at.
        first = (
            db.scalar(
                select(func.count(m15.Turn.id)).where(
                    m15.Turn.session_id == session_id,
                    m15.Turn.speaker == m15.Speaker.officer,
                )
            )
            or 0
        ) <= 1
        opening = loop.pick_line(db, "opening") if first else None

        db.commit()
        await websocket.send_json({
            "type": "officer",
            "seq": officer.seq,
            "intent_key": officer.intent_key,
            "text": officer.text,
            "opening": opening.text if opening else None,
            "opening_audio_url": _audio_url(opening.audio_ref) if opening else None,
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

        # AI-CONTEXT: THE RUBRIC IS NOT ON THIS PATH ANY MORE, and that is the single
        # biggest thing this module did to stop feeling slow. Measured on the box it was
        # 3.41s of a ~5.5s exchange — the largest cost in a spoken conversation, spent
        # computing what a driver reads on the RESULT screen. Nobody was waiting for it;
        # every driver was.
        #
        # `rubric=None` writes the turn with everything the CONVERSATION needs — the slots
        # are deterministic, so the officer can still say "Dallas." back — and marks it
        # `pending`. `deferred_scoring.settle_session_scores` finishes it before any band
        # is derived, so a driver waits once, at the end, where waiting is what you do.
        #
        # DEFERRED ONLY WHILE THE OFFICER IMPROVISES, and the reason is the ack rule below
        # rather than caution. The scripted path suppresses its acknowledgement when the
        # answer missed the question — measured on a live session, where the officer said
        # "Thank you." and then corrected the driver in the same breath — and that rule
        # reads INTENT_MISUNDERSTOOD, which is the rubric's verdict. Defer it there and the
        # tag is simply absent, so the ack would come back on a schedule and the fallback
        # would get WORSE at the moment it is being relied on. The improvising officer has
        # no separate ack to suppress: his own line opens by saying the fact back.
        improvising = conversation.officer_mode(db) == "llm"
        if improvising:
            turn = loop.record_driver_turn(
                db, session, officer=officer, transcript=transcript,
                asr_confidence=confidence, rubric=None,
            )
        else:
            # AI-CONTEXT: a rubric that cannot answer produces REVIEW_NEEDED, not a
            # verdict — an outage or an exhausted budget must never become a statement
            # about this driver's English invented by an accident.
            try:
                turn = loop.record_driver_turn(
                    db, session, officer=officer, transcript=transcript,
                    asr_confidence=confidence,
                    rubric=F9Rubric(db, account_id=session.account_id),
                )
            except RubricUnavailable:
                turn = loop.record_driver_turn(
                    db, session, officer=officer, transcript=transcript,
                    asr_confidence=0.0, rubric=_ReviewOnly(),
                )
        db.commit()

        # AI-CONTEXT: the acknowledgement rides the SCORED frame rather than getting one
        # of its own. A separate frame would need its own ordering guarantee against the
        # next officer line, and the client would have to sequence two sounds it received
        # independently — the ack belongs to the answer that earned it.
        # AI-CONTEXT: NO ACKNOWLEDGEMENT WHEN A CLARIFICATION IS COMING. Measured on a live
        # session: the officer said "Thank you." and then immediately "I'm asking how long
        # you've been driving today, not where you're headed" — nobody thanks you and then
        # corrects you in the same breath. When the answer missed the question, the REPAIR
        # is the response; an ack in front of it is a machine being polite on a schedule.
        # AI-CONTEXT: NO SEPARATE ACKNOWLEDGEMENT WHILE THE OFFICER IMPROVISES. Two
        # reasons, and the second is the one that matters. (1) The suppression rule this
        # replaced read INTENT_MISUNDERSTOOD, which the rubric produces — and the rubric
        # is no longer on this path, so the tag is not here to read. (2) It is redundant:
        # the improvising officer's prompt now REQUIRES him to open by saying the fact
        # back ("Six hours. Let me see your logbook."), so a separate "Okay." in front of
        # that is the machine acknowledging twice. The scripted path still uses its acks.
        misunderstood = "INTENT_MISUNDERSTOOD" in (turn.failure_tags or [])
        ack = None if (improvising or misunderstood) else loop.pick_acknowledgement(db)
        # AI-CONTEXT: THE OFFICER SAYS YOUR ANSWER BACK. "Chicago. Okay." is a different
        # experience from "Okay." — it is the difference between a machine that scored you
        # and a person who heard you, and E3 budgets the runtime TTS for exactly this. The
        # fragment is cached by text, so the first driver to say Chicago pays one call and
        # every later one pays nothing.
        # AI-CONTEXT: NO SEPARATE ECHO WHILE THE OFFICER IMPROVISES — he already says it.
        # His prompt requires him to open with the fact the driver just gave ("Six hours.
        # Let me see your logbook."), so a spoken "Six hours." in front of that is the
        # officer saying it twice, and it costs a synthesis and a playback gap to do it.
        # The scripted officer has no such opening, so it keeps its echo.
        echo_text = (
            None if improvising else next(iter((turn.observed_slots or {}).values()), None)
        )
        echo_ref = (
            m15_audio.fragment_audio(db, str(echo_text)) if echo_text else None
        )
        await websocket.send_json({
            "type": "scored",
            "seq": turn.seq,
            "echo": str(echo_text) if echo_text else None,
            "echo_audio_url": _audio_url(echo_ref),
            "ack": ack.text if ack else None,
            "ack_audio_url": _audio_url(ack.audio_ref) if ack else None,
            "transcript": transcript,
            "confidence": confidence,
            "tags": turn.failure_tags or [],
            "review_needed": turn.review_status.value == "review_needed",
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        })
    finally:
        db.close()

    # AI-CONTEXT: THE OFFICER ANSWERS IN THE SAME BREATH, rather than waiting to be asked.
    # The client used to receive `scored`, wait out a beat, and send `ready` — so every
    # exchange paid a client-side pause plus a full round trip before the model was even
    # asked for the next line. At a window nobody prompts the officer to continue.
    #
    # Opens its own DB session (the `finally` above closed this one) for the same reason
    # every frame does: a talking driver must never pin a pooled connection for minutes.
    return await _officer_frame(websocket, session_id, message)


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

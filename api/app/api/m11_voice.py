"""AI-CONTEXT: M11 Voice Copilot HTTP endpoints — thin over m11_voice.public.
Voice/text intent routing over the app's own data, the motion-aware policy, the
English-out comms ghostwriter, and the conversational claim assistant. The F9
model provider is a dev seam (FakeModelProvider) wired to a real STT/TTS/LLM at
activation.
"""

import base64
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_account, get_db, require_module
from app.foundation.f01_identity import public as identity
from app.foundation.f09_ai_gateway import public as ai
from app.foundation.f15_localization import public as f15
from app.modules.m11_voice import public as m11

log = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"],
    # PRD §6: the module's own flag, gating every route in it (§23 entry 105)
    dependencies=[Depends(require_module("m11_voice"))],
)
_PROVIDER = ai.resolve_provider()  # F9: real Claude when ANTHROPIC_API_KEY set, else Fake


class AskIn(BaseModel):
    text: str
    driving: bool = False
    context: dict = {}
    locale: str | None = None


class ListenIn(BaseModel):
    """A recording from the driver's microphone.

    AI-CONTEXT: base64 rather than multipart, matching M15's coaching attempt — the client
    is a PWA holding a `MediaRecorder` blob, and one JSON body keeps the offline write
    queue (F12) able to carry the request unchanged.
    """

    audio_b64: str
    # what MediaRecorder actually produced: Chrome `audio/webm;codecs=opus`, iOS Safari
    # `audio/mp4`. Declared rather than assumed — see `service.listen`.
    mime: str | None = None
    driving: bool = False
    context: dict = {}
    locale: str | None = None


class DraftIn(BaseModel):
    kind: str
    facts: str
    tone: str = "neutral"


def _response(resp: m11.VoiceResponse, transcript: str | None = None) -> dict:
    """AI-CONTEXT: `audio_b64` REPLACED `audio_ref`, and the rename is the fix.

    `audio_ref` held `audio://{locale}/{sha256[:12]}` — a `FakeModelProvider` string in a
    scheme nothing serves — on production, for the module's whole life. A field named
    `_ref` promises something fetchable, which is precisely how the fake survived: no
    consumer ever tried. `audio_b64` either carries mp3 bytes or is absent, and there is
    no third state to mistake for one (entry 209).

    The bytes ride the response rather than F6 because a copilot answer is heard once by
    one driver — see `service.speak`.
    """
    return {
        "intent": resp.intent,
        "spoken": resp.spoken,
        "data": resp.data,
        "needs_confirmation": resp.needs_confirmation,
        "mode": resp.mode,
        "audio_b64": base64.b64encode(resp.audio).decode() if resp.audio else None,
        # what we heard, so a driver can tell a wrong answer from a misheard question
        # (§14.5 — never pretend to understand)
        "transcript": transcript,
    }


@router.post("/ask")
def ask(
    body: AskIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    # AI-CONTEXT: M11-FR6 — the classifier is locale-aware and this endpoint
    # carried no locale at all, so every driver was routed as an English speaker.
    # Precedence: explicit body > context > the driver's stored F15 locale.
    locale = body.locale or body.context.get("locale") or f15.get_user_locale(db, account)
    resp = m11.route(
        db,
        account.id,
        body.text,
        context={**body.context, "locale": locale},
        driving=body.driving,
        provider=_PROVIDER,
    )
    return _response(resp)


@router.post("/listen")
def listen(
    body: ListenIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    """Microphone in, answer out — the copilot's ears (M11-FR1/FR6).

    AI-CONTEXT: the module HAD no reachable STT path. `handle_utterance` existed, was
    exported, was tested, and no endpoint called it — and it passed an `audio_ref` to a
    provider method that on the live provider returns `"[uz] transcript of <ref>"`. The
    real recognition was the browser's `SpeechRecognition`, which does not exist in Safari
    on iOS, so an iPhone driver had a microphone button that did nothing. This routes the
    same Deepgram seam M15 has used since Session A (entry 209).

    Everything after the transcript is the EXISTING router, untouched: the same intents,
    the same F15 locale precedence, the same M11-FR2 motion policy. Changing the ears was
    never a reason to re-litigate the brain.
    """
    try:
        audio = base64.b64decode(body.audio_b64, validate=True)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "audio_b64 is not base64"
        ) from exc
    if not audio:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "empty recording")

    locale = body.locale or body.context.get("locale") or f15.get_user_locale(db, account)
    try:
        resp, transcript = m11.handle_utterance(
            db, _PROVIDER, account.id, audio,
            locale=locale,
            context={**body.context, "locale": locale, "content_type": body.mime},
            driving=body.driving,
        )
    except Exception as exc:
        # AI-CONTEXT: a recogniser that failed is not a driver who said nothing. M15 paid
        # for this distinction with a whole session dying on a vendor 400 (entry 203); the
        # copilot answers with a status a surface can act on instead.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "speech is unavailable") from exc
    # AI-CONTEXT: DIAGNOSTIC WITHOUT THE WORDS. Twice now a "copilot not working" report
    # has cost a round of guessing that a single line here would have settled — which
    # vendor was asked, in which language, and whether it heard anything. The TRANSCRIPT
    # IS DELIBERATELY NOT LOGGED: M15 records a driver's speech only behind an explicit
    # consent screen with a 30-day class, and the copilot has neither, so putting
    # utterances in container logs would be a retention decision made by a debugging
    # convenience. Length and confidence say what is needed.
    log.info(
        "m11.listen locale=%s vendor=%s bytes=%d mime=%s heard_chars=%d conf=%.2f intent=%s",
        locale, ai.resolve_stt(locale).name, len(audio), body.mime or "-",
        len(transcript or ""), resp.data.get("confidence", 1.0) if resp.data else 1.0,
        resp.intent,
    )
    db.commit()
    return _response(resp, transcript)


@router.get("/claims")
def claims(
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [
        {
            "kind": i.kind,
            "amount_cents": i.amount_cents,
            "state": i.state,
            "next_action": i.next_action,
        }
        for i in m11.claim_assistant(db, account.id)
    ]


@router.post("/draft")
def draft(
    body: DraftIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    m11.register_module(db)  # idempotent: ensure the F9 drafting prompt exists
    text = m11.draft_counterparty_message(
        db, _PROVIDER, account.id, body.kind, body.facts, tone=body.tone
    )
    return {"draft": text, "outbound_language": "en"}

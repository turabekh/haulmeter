"""AI-CONTEXT: M11 Voice Copilot HTTP endpoints — thin over m11_voice.public.
Voice/text intent routing over the app's own data, the motion-aware policy, the
English-out comms ghostwriter, and the conversational claim assistant. The F9
model provider is a dev seam (FakeModelProvider) wired to a real STT/TTS/LLM at
activation.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_account, get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f09_ai_gateway import public as ai
from app.modules.m11_voice import public as m11

router = APIRouter(prefix="/voice", tags=["voice"])
_PROVIDER = ai.resolve_provider()  # F9: real Claude when ANTHROPIC_API_KEY set, else Fake


class AskIn(BaseModel):
    text: str
    driving: bool = False
    context: dict = {}


class DraftIn(BaseModel):
    kind: str
    facts: str
    tone: str = "neutral"


def _response(resp: m11.VoiceResponse) -> dict:
    return {
        "intent": resp.intent,
        "spoken": resp.spoken,
        "data": resp.data,
        "needs_confirmation": resp.needs_confirmation,
        "mode": resp.mode,
        "audio_ref": resp.audio_ref,
    }


@router.post("/ask")
def ask(
    body: AskIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    resp = m11.route(
        db,
        account.id,
        body.text,
        context=body.context,
        driving=body.driving,
        provider=_PROVIDER,
    )
    return _response(resp)


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

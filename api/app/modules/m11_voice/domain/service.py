"""AI-CONTEXT: M11 Voice Copilot & AI Communications (PRD §8.11) — the AI-native
UX layer: hands-free access to everything over the app's OWN structured data
(not open-domain), plus a ghostwriter that removes the tone problem suppressing
claims. A SCHEMA-LESS serving layer (F11/M8 precedent): no tables — it routes
intents to the modules below it and drafts through F9.

- Voice intents (M11-FR1): a deterministic keyword router over ≥15 intents that
  dispatch to M1/M3/M4/M7/M8/M10 publics; STT/TTS is the F9 seam. The router is
  the honest bootstrap; F9 classify is the upgrade path (both hit the same
  eval-fixture accuracy target).
- Motion policy (M11-FR2): voice-first + audio while DRIVING; committing actions
  (start clock, book) defer their confirmation to on-screen-when-stopped.
- Comms ghostwriter (M11-FR3): counterparty drafts via F9 with tone presets;
  the driver approves; outbound is ALWAYS English (F15) and sent via F8.
- Claim assistant (M11-FR4): "what am I owed and the next action on each" over
  the M3/M4 receivable state.
- Multilingual (M11-FR6): utterances transcribe in any launch locale; the
  ghostwriter accepts any language and always outputs English.

Composes f08 + f09 + m04 + m07 + m08 + m10. Runs behind the F13 flag m11_voice.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.foundation.f08_notifications import public as notifications
from app.foundation.f09_ai_gateway import public as ai
from app.modules.m04_accessorial import public as m4
from app.modules.m07_fuel import public as m7
from app.modules.m08_intelligence import public as m8
from app.modules.m10_community import public as m10

FLAG_KEY = "m11_voice"
MODULE = "m11"
GHOSTWRITER_PROMPT = "m11_ghostwriter"

# committing intents whose confirmation is deferred to on-screen-when-stopped
_CONFIRM_INTENTS = {"start_detention", "book_parking"}

# tone presets (M11-FR3): relationship-preserving -> firm
TONES = {
    "relationship": "warm and relationship-preserving",
    "neutral": "professional and neutral",
    "firm": "firm, direct, and citing the rate confirmation",
}

# next action per receivable state (M11-FR4)
_NEXT_ACTION = {
    "invoiced": "send a reminder",
    "acknowledged": "await payment",
    "disputed": "escalate with your GPS evidence",
    "escalated": "await resolution or consider collections",
    "recovered": "paid — nothing to do",
    "written_off": "closed",
}

# ordered classification rules — first match wins (deterministic, no ML)
# each rule: (intent, required_all, any_of)
_RULES: list[tuple[str, list[str], list[str]]] = [
    ("start_detention", ["start"], ["detention", "clock", "meter"]),
    ("detention_risk", ["risk"], ["detention", "hold"]),
    ("detention_status", [], ["detention", "meter", "clock", "accruing"]),
    ("fuel_savings", [], ["saved", "savings", "save"]),
    ("fuel_nearby", [], ["fuel", "diesel", "gas"]),
    ("book_parking", ["book"], ["parking", "spot", "lot", "reserve"]),
    ("sleep_tonight", [], ["sleep", "rest tonight", "where do i sleep", "overnight"]),
    ("parking_nearby", [], ["parking", "park", "spot", "lot"]),
    ("best_hour", [], ["best time", "what time", "fastest", "best hour"]),
    ("dwell_time", [], ["dwell", "how long", "unload"]),
    ("facility_info", [], ["facility", "receiver", "shipper", "entrance", "dock"]),
    ("next_action", [], ["next action", "what should i do", "next step"]),
    ("money_owed", [], ["owed", "owe", "what am i owed", "money"]),
    ("points_balance", [], ["points", "reward"]),
    ("help", [], ["help", "what can you do"]),
]
INTENTS = [r[0] for r in _RULES] + ["unknown"]


@dataclass
class VoiceResponse:
    intent: str
    spoken: str
    data: dict = field(default_factory=dict)
    needs_confirmation: bool = False
    mode: str = "visual"  # voice while driving, visual when stopped
    audio_ref: str | None = None


@dataclass
class ClaimItem:
    kind: str
    amount_cents: int
    state: str
    next_action: str


def register_module(db: Session) -> None:
    from app.foundation.f13_flags import public as flags
    from app.foundation.f14_admin import public as admin

    flags.register_flag(db, FLAG_KEY, description="M11 Voice Copilot & AI Communications")
    admin.register_admin_view(db, "m11.voice", MODULE, "Voice & Comms", "/admin/m11/voice")
    if ai.get_active_prompt(db, GHOSTWRITER_PROMPT) is None:
        ai.register_prompt(
            db,
            GHOSTWRITER_PROMPT,
            ai.AiTask.drafting,
            "Write a {tone} {kind} to the counterparty in ENGLISH. Facts: {facts}",
        )


# --- Intent routing (M11-FR1) + motion policy (M11-FR2) ---
def classify_intent(utterance: str) -> str:
    u = utterance.lower()
    for intent, required, any_of in _RULES:
        if all(term in u for term in required) and (
            not any_of or any(term in u for term in any_of)
        ):
            return intent
    return "unknown"


def interaction_mode(driving: bool) -> str:
    return "voice" if driving else "visual"


def _dispatch(db: Session, account_id, intent: str, context: dict) -> tuple[str, dict]:
    if intent in ("money_owed", "next_action"):
        items = claim_assistant(db, account_id)
        total = sum(i.amount_cents for i in items if i.state not in ("recovered", "written_off"))
        return (
            f"You're owed ${total / 100:.2f} across {len(items)} claims."
            if items
            else "You're all paid up — nothing owed right now.",
            {"claims": [i.__dict__ for i in items]},
        )
    if intent == "points_balance":
        pts = m10.points_balance(db, account_id)
        return f"You have {pts} points.", {"points": pts}
    if intent == "fuel_savings":
        saved = m7.driver_analytics(db, account_id).savings_cents
        return f"You've saved ${saved / 100:.2f} on fuel so far.", {"fuel_saved_cents": saved}
    if intent == "sleep_tonight":
        if {"lat", "lon", "hos_minutes_remaining"} <= context.keys():
            plan = m8.where_to_sleep(
                db,
                account_id,
                context["lat"],
                context["lon"],
                context.get("heading_deg", 0),
                context["hos_minutes_remaining"],
            )
            n = len(plan.stops)
            return f"I found {n} stops within your hours.", {"stops": n}
        return "How many hours do you have left?", {"clarify": "hos"}
    if intent == "detention_status":
        owed = sum(
            r["amount_cents"] for r in m4.money_owed(db, account_id) if r["kind"] == "detention"
        )
        return (
            f"Detention on record: ${owed / 100:.2f}."
            if owed
            else "No detention on record right now.",
            {"detention_cents": owed},
        )
    if intent == "help":
        return (
            "Ask me about parking, fuel, your detention clock, "
            "what you're owed, or to draft a message.",
            {},
        )
    if intent == "unknown":
        return "I didn't catch that — try 'parking ahead' or 'what am I owed'.", {}
    # remaining query intents acknowledge and hand to the on-screen surface
    return f"Pulling up {intent.replace('_', ' ')}.", {"handoff": intent}


def route(
    db: Session,
    account_id,
    utterance: str,
    context: dict | None = None,
    driving: bool = False,
    provider=None,
) -> VoiceResponse:
    context = context or {}
    intent = classify_intent(utterance)
    needs_conf = intent in _CONFIRM_INTENTS
    if needs_conf and driving:
        # M11-FR2: never commit an action in motion — confirm on screen when stopped
        spoken = "I'll set that up — confirm on screen when you're stopped."
        return VoiceResponse(
            intent,
            spoken,
            {"deferred": True},
            needs_confirmation=True,
            mode="voice",
            audio_ref=_maybe_tts(db, provider, spoken, context),
        )
    spoken, data = _dispatch(db, account_id, intent, context)
    return VoiceResponse(
        intent,
        spoken,
        data,
        needs_confirmation=needs_conf,
        mode=interaction_mode(driving),
        audio_ref=_maybe_tts(db, provider, spoken, context) if driving else None,
    )


def _maybe_tts(db: Session, provider, text: str, context: dict) -> str | None:
    if provider is None:
        return None
    return ai.synthesize(db, provider, MODULE, text, locale=context.get("locale", "en"))


def handle_utterance(
    db: Session,
    provider,
    account_id,
    audio_ref: str,
    locale: str = "en",
    context: dict | None = None,
    driving: bool = False,
) -> VoiceResponse:
    # M11-FR1/FR6: STT in the driver's locale, then route the transcript
    transcript = ai.transcribe(db, provider, MODULE, audio_ref, locale=locale)
    ctx = {**(context or {}), "locale": locale}
    return route(db, account_id, transcript, ctx, driving=driving, provider=provider)


# --- Comms ghostwriter (M11-FR3) ---
def draft_counterparty_message(
    db: Session, provider, account_id, kind: str, facts: str, tone: str = "neutral"
) -> str:
    # F9 drafting seam; outbound is ALWAYS English (F15) — enforced by the prompt
    return ai.complete(
        db,
        provider,
        MODULE,
        GHOSTWRITER_PROMPT,
        {"kind": kind, "tone": TONES.get(tone, TONES["neutral"]), "facts": facts},
        account_id=account_id,
    )


def approve_and_send(db: Session, thread, body: str, gateway, to_ref: str):
    # the driver approved the draft — send the English message via F8
    return notifications.send_counterparty_message(db, thread, body, gateway, to_ref)


# --- Conversational claim assistant (M11-FR4) ---
def claim_assistant(db: Session, account_id) -> list[ClaimItem]:
    return [
        ClaimItem(
            kind=r["kind"],
            amount_cents=r["amount_cents"],
            state=r["state"],
            next_action=_NEXT_ACTION.get(r["state"], "review"),
        )
        for r in m4.money_owed(db, account_id)
    ]

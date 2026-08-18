"""AI-CONTEXT: M11 Voice Copilot & AI Communications (PRD §8.11) — the AI-native
UX layer: hands-free access to everything over the app's OWN structured data
(not open-domain), plus a ghostwriter that removes the tone problem suppressing
claims. A SCHEMA-LESS serving layer (F11/M8 precedent): no tables — it routes
intents to the modules below it and drafts through F9.

- Voice intents (M11-FR1): a deterministic router over ≥15 intents that dispatch
  to M1/M3/M4/M7/M8/M10 publics; STT/TTS is the F9 seam. The router is the
  honest bootstrap; F9 classify is the upgrade path (both hit the same
  eval-fixture accuracy target). ALL vocabulary and matching live in
  `lexicon.py` — six locales, token-phrase matching, specificity scoring.
  Nothing here classifies; this module only dispatches what came back.
- Motion policy (M11-FR2): voice-first + audio while DRIVING; committing actions
  (start clock, book) defer their confirmation to on-screen-when-stopped.
- Comms ghostwriter (M11-FR3): counterparty drafts via F9 with tone presets;
  the driver approves; outbound is ALWAYS English (F15) and sent via F8.
- Claim assistant (M11-FR4): "what am I owed and the next action on each" over
  the M3/M4 receivable state.
- Multilingual (M11-FR6): utterances transcribe in any launch locale and
  CLASSIFY in it — the locale scopes the vocabulary, with English always in
  scope for embedded trucking jargon. The ghostwriter accepts any language and
  always outputs English. The ANSWER is localized too (N-01): every spoken
  string comes from F15's message catalogue via `messages.py`, keyed by the
  driver's locale, falling back to compiled English if a row is missing.

Composes f08 + f09 + f15 + m04 + m07 + m08 + m10. Runs behind the F13 flag
m11_voice.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.foundation.f08_notifications import public as notifications
from app.foundation.f09_ai_gateway import public as ai
from app.foundation.f15_localization import public as localization
from app.modules.m04_accessorial import public as m4
from app.modules.m07_fuel import public as m7
from app.modules.m08_intelligence import public as m8
from app.modules.m10_community import public as m10

from . import lexicon, messages

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

INTENTS = lexicon.INTENTS


@dataclass
class VoiceResponse:
    intent: str
    spoken: str
    data: dict = field(default_factory=dict)
    needs_confirmation: bool = False
    mode: str = "visual"  # voice while driving, visual when stopped
    # AI-CONTEXT: BYTES, and the field was renamed from `audio_ref` on purpose. `audio_ref`
    # named a thing that could be fetched, and for its whole life it held `audio://…`,
    # which could not. A name that promises a resource is how a fake survives review.
    audio: bytes | None = None


@dataclass
class ClaimItem:
    kind: str
    amount_cents: int
    state: str
    next_action: str


def register_module(db: Session) -> None:
    from app.foundation.f13_flags import public as flags
    from app.foundation.f14_admin import public as admin

    flags.register_flag(
        db, FLAG_KEY, description="M11 Voice Copilot & AI Communications", default_on=True
    )
    admin.register_admin_view(db, "m11.voice", MODULE, "Voice & Comms", "/admin/m11/voice")
    if ai.get_active_prompt(db, GHOSTWRITER_PROMPT) is None:
        ai.register_prompt(
            db,
            GHOSTWRITER_PROMPT,
            ai.AiTask.drafting,
            "Write a {tone} {kind} to the counterparty in ENGLISH. Facts: {facts}",
        )
    register_voice_messages(db)


def register_voice_messages(db: Session) -> None:
    """AI-CONTEXT: N-01 — this is F15's message catalogue's FIRST producer in the
    product. `register_message` was written, exported and called by nothing but F15's
    own test, which is the same built-and-inert shape as F-09's purge.

    Idempotent by `register_message`'s own upsert, so an edited string here is what the
    box serves after the next boot rather than needing a migration. N-02 generalised the
    loop into `f15.register_catalogue`, which every notification table now uses too.
    """
    localization.register_catalogue(db, messages.KEY_PREFIX, messages.VOICE_MESSAGES)


# --- Intent routing (M11-FR1) + motion policy (M11-FR2) ---
def classify_intent(utterance: str, locale: str = lexicon.DEFAULT_LOCALE) -> str:
    return lexicon.classify(utterance, locale)


def interaction_mode(driving: bool) -> str:
    return "voice" if driving else "visual"


# AI-CONTEXT: finding N-01 — the copilot understood six languages and answered in one.
# Every string it speaks comes from F15's catalogue now, keyed by the driver's locale.
#
# A MISSING ROW FALLS BACK TO THE COMPILED ENGLISH rather than to a blank, a raw key, or
# a refusal. That is F-17's third option applied again: `main.py` only warns if boot
# registration fails, so a strict lookup would turn one missing row into a silent voice
# on the surface a driver is using at speed.
def _say(db: Session, key: str, locale: str, **values) -> str:
    default = messages.VOICE_MESSAGES[key][messages.DEFAULT_LOCALE_KEY]
    text = localization.get_message(db, messages.KEY_PREFIX + key, locale) or default
    return text.format(**values) if values else text


def _money(cents: int) -> str:
    # NOT localized, deliberately. F15 fixes units imperial and currency USD in every
    # locale because this is a US trucking product; a driver reading "1.234,56 €" would
    # be reading about a different country's money.
    return f"${cents / 100:.2f}"


def _dispatch(db: Session, account_id, intent: str, context: dict) -> tuple[str, dict]:
    locale = context.get("locale", lexicon.DEFAULT_LOCALE)
    if intent in ("money_owed", "next_action"):
        items = claim_assistant(db, account_id)
        total = sum(i.amount_cents for i in items if i.state not in ("recovered", "written_off"))
        return (
            _say(db, "money_owed", locale, amount=_money(total), count=len(items))
            if items
            else _say(db, "money_owed_none", locale),
            {"claims": [i.__dict__ for i in items]},
        )
    if intent == "points_balance":
        pts = m10.points_balance(db, account_id)
        return _say(db, "points_balance", locale, points=pts), {"points": pts}
    if intent == "fuel_savings":
        saved = m7.driver_analytics(db, account_id).savings_cents
        return (
            _say(db, "fuel_savings", locale, amount=_money(saved)),
            {"fuel_saved_cents": saved},
        )
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
            return _say(db, "sleep_found", locale, count=n), {"stops": n}
        return _say(db, "sleep_clarify", locale), {"clarify": "hos"}
    if intent == "detention_status":
        owed = sum(
            r["amount_cents"] for r in m4.money_owed(db, account_id) if r["kind"] == "detention"
        )
        return (
            _say(db, "detention_status", locale, amount=_money(owed))
            if owed
            else _say(db, "detention_none", locale),
            {"detention_cents": owed},
        )
    if intent == "help":
        return _say(db, "help", locale), {}
    if intent == "unknown":
        return _say(db, "unknown", locale), {}
    # remaining query intents acknowledge and hand to the on-screen surface. Each has its
    # OWN key: interpolating `intent.replace("_", " ")` spoke an English slug inside a
    # Spanish sentence, which is worse than either language on its own.
    return _say(db, f"handoff.{intent}", locale), {"handoff": intent}


def route(
    db: Session,
    account_id,
    utterance: str,
    context: dict | None = None,
    driving: bool = False,
    provider=None,
) -> VoiceResponse:
    context = context or {}
    intent = classify_intent(utterance, context.get("locale", lexicon.DEFAULT_LOCALE))
    needs_conf = intent in _CONFIRM_INTENTS
    if needs_conf and driving:
        # M11-FR2: never commit an action in motion — confirm on screen when stopped.
        # This one is ALWAYS spoken aloud (mode="voice"), so it is the string N-01
        # matters most for: the driver cannot read the screen to recover from it.
        spoken = _say(db, "deferred", context.get("locale", lexicon.DEFAULT_LOCALE))
        return VoiceResponse(
            intent,
            spoken,
            {"deferred": True},
            needs_confirmation=True,
            mode="voice",
            audio=speak(db, spoken, locale=context.get("locale", "en")),
        )
    spoken, data = _dispatch(db, account_id, intent, context)
    return VoiceResponse(
        intent,
        spoken,
        data,
        needs_confirmation=needs_conf,
        mode=interaction_mode(driving),
        audio=speak(db, spoken, locale=context.get("locale", "en")) if driving else None,
    )


# AI-CONTEXT: the copilot's own voice map, and it is NOT M15's.
#
# `m15.coach_voices` carries `uz` alone, because M15 speaks the driver's language only to
# explain a mistake; everything else it says is a US officer. The copilot answers the
# driver in whatever language the driver asked in, so it needs all six — and a locale
# missing from this map is silence, not English (§14.5, and the same argument Q-9 makes
# for M15's coaching text).
#
# EVERY NAME HERE WAS VERIFIED AGAINST AZURE'S LIVE VOICE LIST, not remembered. A voice
# name that does not exist is a 502 at the moment a driver asks a question, which is the
# worst possible place to discover a typo — the officer voice's own comment records that
# lesson about styles. Config, not a constant, so an operator can change a voice without
# a deploy.
COPILOT_VOICES_KEY = "m11.copilot_voices"
COPILOT_VOICES_DEFAULT = {
    "en": "en-US-AriaNeural",
    # es-US rather than es-ES: the driver is in the United States and so is the Spanish
    "es": "es-US-PalomaNeural",
    "ru": "ru-RU-SvetlanaNeural",
    # the same voice M15 coaches in, deliberately — one product, one Uzbek voice
    "uz": "uz-UZ-SardorNeural",
    "pa": "pa-IN-OjasNeural",
    "so": "so-SO-MuuseNeural",
}


def copilot_voice(db: Session, locale: str) -> dict | None:
    """The voice for an answer in `locale`, or None if we cannot speak it."""
    from app.foundation.f13_flags import public as flags

    voices = flags.get_config(db, COPILOT_VOICES_KEY, COPILOT_VOICES_DEFAULT) or {}
    name = voices.get((locale or "").split("-")[0])
    if not name:
        return None
    # no style and no rate, for the reason M15's `coach_voice` records: the emotional-style
    # inventory differs per voice and a style a voice lacks is a 502.
    return {"voice": str(name), "style": None, "rate": None}


def speak(db: Session, text: str, *, locale: str = "en") -> bytes | None:
    """The answer as real audio, or None when we genuinely cannot say it.

    AI-CONTEXT: THIS REPLACED A FAKE THAT WAS LIVE ON PRODUCTION. `_maybe_tts` called
    `ai.synthesize`, which lands on `AnthropicModelProvider.synthesize` — and that
    delegates to `self._fallback`, the `FakeModelProvider`, which returns
    `audio://{locale}/{sha256[:12]}`. Every spoken answer this module ever produced was a
    hash in a scheme nothing serves, nothing stores and nothing plays; the UI never read
    the field, so it was never even visible as a broken link (entry 209).

    RETURNS BYTES, NOT A REF, and that is the one place this diverges from M15. M15 stores
    every clip in F6 because its content is authored once and heard by thousands — the
    storage pays for itself on the second listen. A copilot answer is unique to one driver
    and heard once, so storing it would add a document per question, a retention class and
    a signed URL, all to serve a file nobody will ever request again. The bytes ride the
    response.

    None has one meaning only: we cannot speak this language. It is never a fake.
    """
    if not text or not text.strip():
        return None
    if not ai.tts_configured():
        # a dev box without Azure is not a fault; the surface falls back to its own voice
        return None
    settings = copilot_voice(db, locale)
    if settings is None:
        return None
    try:
        audio = ai.resolve_tts().synthesize(text, locale=locale, **settings)
    except Exception:
        # a voice we could not fetch is silence, not an error a driver can act on — the
        # answer is already on screen and the text is the product
        return None
    # metered against m11's own budget, not m15's: the copilot's audio is per-ask and
    # uncached, which is exactly the spend worth watching separately
    ai.record_audio_minutes(db, MODULE, ai.AiTask.tts, max(len(audio) / 320_000.0, 0.02))
    return audio


# AI-CONTEXT: the same floor M15 scores against (`scoring.ASR_CONFIDENCE_FLOOR`). Stated
# here rather than imported because a module may not reach into another module's domain,
# and duplicating a number is cheaper than a public export nobody else needs. If one
# moves, this comment is how the other is found.
ASR_CONFIDENCE_FLOOR = 0.55


def listen(db: Session, audio: bytes, *, locale: str = "en") -> tuple[str, float]:
    """Driver audio to text, through the same Deepgram seam M15 uses.

    AI-CONTEXT: the ears the copilot never had. Recognition was the BROWSER's
    `SpeechRecognition`, which does not exist in Safari on iOS at all — so on an iPhone
    there was no microphone button that did anything, while a paid Deepgram key sat in the
    same settings object serving M15.
    """
    transcript, confidence = ai.resolve_stt().transcribe(audio, locale=locale)
    ai.record_audio_minutes(db, MODULE, ai.AiTask.stt, max(len(audio) / 320_000.0, 0.02))
    return transcript, confidence


def handle_utterance(
    db: Session,
    provider,
    account_id,
    audio: bytes,
    locale: str = "en",
    context: dict | None = None,
    driving: bool = False,
) -> tuple[VoiceResponse, str]:
    """Real driver audio in; the routed answer and what we heard, out.

    AI-CONTEXT: THIS TOOK AN `audio_ref: str` AND HAD NO CALLER. It passed that ref to
    `ai.transcribe`, which on the live provider delegates to `FakeModelProvider` and
    returns the literal string `"[uz] transcript of <ref>"` — so the module's only STT path
    produced a sentence describing itself, and nothing in production ever ran it. The
    copilot's real ears were the browser's, which do not exist on iOS (entry 209).

    RETURNS THE TRANSCRIPT ALONGSIDE THE ANSWER, deliberately. §14.5 says never pretend to
    understand, and a driver cannot tell a wrong answer from a misheard question unless the
    surface shows them what it heard. That is the same argument Q-2 makes in M15 for
    showing a driver their own transcript.
    """
    transcript, confidence = listen(db, audio, locale=locale)
    ctx = {**(context or {}), "locale": locale}

    # AI-CONTEXT: A LOW-CONFIDENCE TRANSCRIPT IS NOT A COMMAND. §14.5 says never pretend
    # to understand, and this module can START THINGS — `_CONFIRM_INTENTS` exists because
    # some of what a driver can say commits an action. Routing a guess is exactly the
    # failure that rule names, and it is worse here than in M15: a misheard practice
    # answer costs a score, a misheard copilot instruction costs a claim.
    #
    # Caught by running it: Deepgram returned `('one of my art', 0.73)` for "what am I
    # owed" on the first real round trip. The answer is to say what we heard and ask
    # again — never to act on it.
    if confidence < ASR_CONFIDENCE_FLOOR:
        spoken = _say(db, "unknown", locale)
        return (
            VoiceResponse(
                "unknown",
                spoken,
                {"unclear": True, "confidence": round(confidence, 2)},
                mode=interaction_mode(driving),
                audio=speak(db, spoken, locale=locale) if driving else None,
            ),
            transcript,
        )

    resp = route(db, account_id, transcript, ctx, driving=driving, provider=provider)
    return resp, transcript


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
    """The driver approved the draft — record the message; the sweep sends it.

    AI-CONTEXT: the last unkeyed send path, and the only one where a double tap could
    still put two emails in a broker's inbox. Every other purpose has a natural identity —
    a claim, a receivable, a stop — and this one does not: a driver may legitimately write
    to the same counterparty twice about different things, so keying on the thread alone
    would silence the second one.

    What IS a duplicate is the same approved words to the same thread. That is a second
    tap, a replayed request, or a driver who did not see the first one land — never a
    deliberate second message, because a driver who means to say something else says
    something else. So the key is the thread plus a digest of the body, which is exactly
    "the same purpose and intent" for text that has no other identity.

    SHA-256 rather than the raw body: `dedupe_key` is 200 characters and a ghostwritten
    message is longer than that, so a prefix would collide on two messages sharing an
    opening line — which is the normal case for templated prose.
    """
    import hashlib

    digest = hashlib.sha256(body.strip().encode()).hexdigest()[:32]
    return notifications.send_counterparty_message(
        db, thread, body, gateway, to_ref, dedupe_key=f"voice:{thread.id}:{digest}"
    )


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

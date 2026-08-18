"""AI-CONTEXT: officer lines get a VOICE (E3 §E3.1.2, M15-FR3).

THE GAP THIS CLOSES, stated plainly because it shipped without it. M15 went live with 8
released phrase variants and **zero audio**: the adapter worked, Azure answered, and
nothing had ever called it for content. A driver opened a simulated roadside stop and read
the officer's question off a silent screen. E3 is explicit that this is not the design —
*"pre-synthesized officer audio is what holds the simulation to sub-1.3s and ~$0.10
COGS"* — the synthesis path was left a named remainder in Session A and stayed one.

PRE-SYNTHESIZED, NOT ON DEMAND. Synthesizing inside a turn would put Azure's latency
inside the driver's wait, which is exactly the budget M15-FR3 is measured against. So this
runs as a worker job over released content and the socket only ever references bytes that
already exist.

RELEASED ONLY, AND NEVER A HOLDOUT. It reads `teachable_variants`, the same generator the
turn does, rather than querying variants itself — Q-5 and Q-6 are enforced in one place and
a second query here would be a second place for them to drift. Giving a holdout a voice
would not leak it by itself, but it would spend money synthesizing lines that must never be
taught, and it is the first step toward serving them.

THE OWNER OF CONTENT AUDIO. `f06.document.account_id` is NOT NULL, and an officer line
belongs to no driver — so content audio is owned by one system account that has no
credential and cannot sign in. The alternative was making the column nullable, which
touches every account-scoped read in F6 to solve a problem that has exactly one instance.
The account is created on demand and is idempotent.

RETENTION IS `permanent`, which is the default, and that is the distinction the retention
sweep exists to make: a driver's recording expires in 30 days, an officer's line is content
and does not. `retention.py` says the sweep may select on ONE thing — the retention class —
and this is the other side of that rule.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.foundation.f01_identity import public as identity
from app.foundation.f06_documents import public as documents
from app.foundation.f09_ai_gateway import public as ai

from .content import teachable_variants
from .enums import ContentStatus
from .models import (
    AudioFragment,
    CoachingContent,
    Intent,
    ModelAnswer,
    OfficerAck,
    RepairLine,
)

# AI-CONTEXT: a mailbox nobody reads on a domain the owner controls. It exists to satisfy
# an ownership column, never to receive anything, and it holds no credential — F1 will not
# issue a session for an account with no auth method.
CONTENT_ACCOUNT_EMAIL = "content@haulmeter.online"

# MP3 at Azure's default rate. Named here rather than inferred from the bytes, because
# `is_audio` in F6 decides Range support from the content type and a wrong one silently
# turns off seeking.
AUDIO_CONTENT_TYPE = "audio/mpeg"


# AI-CONTEXT: HOW THE OFFICER SOUNDS, as operator config rather than a constant.
#
# The owner's complaint was "now it is reading a text", and a voice is a matter of taste
# that nobody settles by reasoning — it is settled by listening. So these are three F13
# keys and they are DECLARED (see `register_config`), which is the lesson from the officer
# kill switch: `set_config` writes whether or not a key is declared, so an undeclared knob
# works and cannot be found, and a knob nobody can find is not a control.
#
# THE OWNER CHOSE `en-US-Ethan:MAI-Voice-2-Flash` BY EAR, from every voice this
# subscription offers. Two things measured on the box afterwards, both of which matter more
# than they look:
#
#   · **it is faster to LISTEN TO, which beats being faster to synthesize.** Ethan takes
#     0.54s to render against Guy's 0.24s — and produces 3.0s of speech where Guy produced
#     5.3s for the same sentence. The driver hears a finished line ~2s sooner. Synthesis
#     latency is the number that is easy to measure and the wrong one to optimise.
#   · **it has NO conversational style, and sending one is a 502.** Its style list is
#     emotional only (angry, excited, whispering…); `conversation`, `chat` and even
#     `general` are absent, and `general` was tried and returned 502 rather than being
#     ignored. So the style default is EMPTY here, where a Kai or Davis default would carry
#     one. This is exactly why the three are separate keys rather than one "voice" setting:
#     they are not independent, and a voice swap that leaves a stale style behind is a
#     silent outage of every officer line.
#
# The rate default is empty too: Ethan already speaks at a natural clip, and the owner asked
# for speed. `-4%` renders correctly on it (3.0s → 3.2s) if a slower register is ever wanted.
VOICE_KEY = "m15.officer_voice"
STYLE_KEY = "m15.officer_style"
RATE_KEY = "m15.officer_rate"
VOICE_DEFAULT = "en-US-Ethan:MAI-Voice-2-Flash"
STYLE_DEFAULT = ""
RATE_DEFAULT = ""


def officer_voice(db: DbSession) -> dict:
    """The voice, style and pace to synthesize an officer line with.

    Returned as kwargs so a caller cannot pass some of them and forget the rest — the
    three travel together or the register is wrong in a way nobody notices until a driver
    says it sounds like a machine again.
    """
    from app.foundation.f13_flags import public as flags

    style = flags.get_config(db, STYLE_KEY, STYLE_DEFAULT)
    rate = flags.get_config(db, RATE_KEY, RATE_DEFAULT)
    return {
        "voice": str(flags.get_config(db, VOICE_KEY, VOICE_DEFAULT)),
        # empty string is a real answer meaning "this voice has no style" — sending a
        # style a voice does not support is a 400, not a shrug
        "style": str(style) or None,
        "rate": str(rate) or None,
    }


# AI-CONTEXT: THE COACH IS NOT THE OFFICER, and the difference is not decoration. The
# officer speaks US English at a driver; the coach explains, in the DRIVER'S language, why
# an answer missed. An Uzbek explanation read by `en-US-Ethan` is not accented Uzbek — it is
# English phonemes applied to Uzbek words, which is worse than silence because it teaches a
# pronunciation nobody uses.
#
# A map rather than a key per locale, because the set grows one language at a time and a
# new locale should be an operator edit rather than a deploy. Checked against Azure before
# shipping: uz-UZ has two native voices, ru-RU seven, es-MX twenty-three, pa-IN and so-SO
# two each — and tg-TJ has NONE, which is why Tajik coaching would be text-only and why the
# owner dropped it. A locale absent from this map has no coach voice and its explanation
# stays text, which is a degradation and not a failure.
COACH_VOICES_KEY = "m15.coach_voices"
COACH_VOICES_DEFAULT = {"uz": "uz-UZ-SardorNeural"}


def coach_voice(db: DbSession, locale: str) -> dict | None:
    """The voice for a coaching explanation in `locale`, or None if we cannot speak it."""
    from app.foundation.f13_flags import public as flags

    voices = flags.get_config(db, COACH_VOICES_KEY, COACH_VOICES_DEFAULT) or {}
    name = voices.get((locale or "").split("-")[0])
    if not name:
        return None
    # no style, no rate: the emotional-style lists differ per locale and a style a voice
    # lacks is a 502 (see the officer's note above). Plain speech is the safe default for
    # a language whose voice inventory we have not individually verified.
    return {"voice": str(name), "style": None, "rate": None}


def register_config(db: DbSession) -> None:
    """Declare them, so an operator can hear a change without a deploy."""
    from app.foundation.f13_flags import public as flags

    flags.register_config(
        db, VOICE_KEY, VOICE_DEFAULT,
        description="Azure voice for the officer, e.g. en-US-KaiNeural, en-US-DavisNeural.",
    )
    flags.register_config(
        db, STYLE_KEY, STYLE_DEFAULT,
        description=(
            "Speaking style for that voice — EMPTY unless the voice actually lists one. "
            "Kai has 'conversation', Davis has 'chat'; the MAI voices list only emotional "
            "styles and reject anything else with a 502, which silences every line."
        ),
    )
    flags.register_config(
        db, RATE_KEY, RATE_DEFAULT,
        description="SSML prosody rate, e.g. '-4%'. Negative is slower and more deliberate.",
    )
    flags.register_config(
        db, COACH_VOICES_KEY, COACH_VOICES_DEFAULT,
        description=(
            "Voice per coaching language, e.g. {\"uz\": \"uz-UZ-SardorNeural\"}. The coach "
            "speaks the DRIVER'S language, not the officer's. A locale missing here has no "
            "coach voice and its explanation stays text — tg-TJ has no Azure voice at all."
        ),
    )


def content_account(db: DbSession):
    """The system account that owns synthesized content. Idempotent."""
    existing = db.scalar(
        select(identity.Account).where(identity.Account.email == CONTENT_ACCOUNT_EMAIL)
    )
    if existing is not None:
        return existing
    account = identity.Account(email=CONTENT_ACCOUNT_EMAIL)
    db.add(account)
    db.flush()
    return account


def variants_needing_audio(db: DbSession) -> list:
    """Released content that has no voice yet — officer lines AND model answers.

    Officer lines go through `teachable_variants` per intent rather than being queried
    directly (see the module docstring), so Q-5 and Q-6 are enforced in one place.

    MODEL ANSWERS NEED A VOICE FOR THE SAME REASON THE QUESTIONS DO, and arguably more:
    FR5's step is "hear a clear model answer, repeat it". A model answer a driver can only
    READ cannot be shadowed — shadowing is an ear-and-mouth exercise, and text turns it
    into a reading test, which is the one thing this module is not.

    An intent with nothing released contributes nothing, which is why this returns an empty
    list on a box where no content has been reviewed.
    """
    out: list = []
    for intent in db.scalars(select(Intent)):
        out.extend(v for v in teachable_variants(db, intent.id) if v.audio_ref is None)
    for table in (ModelAnswer, OfficerAck, RepairLine):
        out.extend(
            db.scalars(
                select(table).where(
                    table.status == ContentStatus.released,
                    table.audio_ref.is_(None),
                )
            )
        )
    # AI-CONTEXT: COACHING EXPLANATIONS TOO, and they are the odd one out twice over — the
    # column is `review_status` rather than `status`, and the text is in the DRIVER'S
    # language rather than English. Both differences are handled at synthesis time
    # (`_speech_for`), not here; what matters here is that a released explanation with no
    # voice is work, exactly like every other line. Without this entry the migration that
    # added the column would have been a promise nothing kept.
    out.extend(
        db.scalars(
            select(CoachingContent).where(
                CoachingContent.review_status == ContentStatus.released,
                CoachingContent.audio_ref.is_(None),
            )
        )
    )
    return out


def store_driver_audio(db: DbSession, blob: bytes, *, storage=None):
    """Keep what the driver actually said, under the 30-day class consent promised.

    AI-CONTEXT: THE PIECE THAT WAS NEVER WRITTEN. `Turn.audio_ref` has existed since the
    first migration and its own docstring says "the raw audio here is the 30-day TTL
    class"; `classify_audio_30d` exists; `run_audio_retention` sweeps it unflagged and
    documents at length why it must never be flagged. **The consent screen tells every
    driver about "the voice recording, the 30-day deletion with scores kept" before they
    may start.** Every part of that promise was built except the recording: the socket
    transcribed the audio and dropped it, so there was nothing to review, nothing to
    replay, and nothing for the sweep to delete.

    CLASSIFIED AT WRITE TIME, by the caller that knows what the bytes ARE — F6 cannot tell
    a driver's recording from a synthesized officer line by looking, and guessing is what
    the column exists to prevent. An officer line is `permanent` content; this is a
    person's voice and it goes away.
    """
    if not blob:
        return None
    owner = content_account(db)
    document = documents.store_document(
        db,
        owner.id,
        documents.DocType.other,
        blob,
        filename="driver-answer.webm",
        content_type="audio/webm",
        storage=storage,
    )
    documents.classify_audio_30d(document)
    db.flush()
    return document.id


def fragment_audio(db: DbSession, text: str, *, locale: str = "en", storage=None):
    """A synthesized scrap — a city, a number — cached by its text forever.

    AI-CONTEXT: this is what lets the officer say "Chicago." back to a driver. E3 budgets
    runtime TTS for exactly this ("only small dynamic slot fragments (names, cities, hours)
    touch TTS at runtime"), and the cache is what keeps the budget: the FIRST driver to say
    Chicago pays one Azure call, every later one pays nothing, for the life of the product.

    Returns None rather than raising when there is no key or the call fails. An officer who
    cannot say your city back still has an acknowledgement to fall back on, and a turn is
    not worth failing over a flourish.
    """
    text = (text or "").strip()
    if not text or len(text) > 200:
        return None
    # AI-CONTEXT: THE VOICE IS PART OF THE KEY (migration 0092). It used to be a constant
    # in the adapter, and is now an operator setting chosen by ear — so looking up on text
    # alone serves every older sentence in the PREVIOUS voice while new ones arrive in the
    # current one, and the officer changes voice halfway through a stop. Nothing fails; the
    # cache does exactly what it was told and a driver hears two people.
    settings = officer_voice(db)
    voice = settings["voice"]
    existing = db.scalar(
        select(AudioFragment).where(
            AudioFragment.text == text,
            AudioFragment.locale == locale,
            AudioFragment.voice == voice,
        )
    )
    if existing is not None:
        return existing.audio_ref

    try:
        tts = ai.resolve_tts()
        audio = tts.synthesize(text, locale=locale, **settings)
    except Exception:
        return None

    owner = content_account(db)
    document = documents.store_document(
        db,
        owner.id,
        documents.DocType.other,
        audio,
        filename=f"fragment-{abs(hash(text))}.mp3",
        content_type=AUDIO_CONTENT_TYPE,
        storage=storage,
    )
    db.add(AudioFragment(text=text, locale=locale, voice=voice, audio_ref=document.id))
    ai.record_audio_minutes(db, "m15", ai.AiTask.tts, max(len(audio) / 320_000.0, 0.02))
    db.flush()
    return document.id


def _speech_for(db: DbSession, item) -> tuple[str, str, dict] | None:
    """What to say, in which language, in whose voice — or None if we cannot say it.

    AI-CONTEXT: the one place the coach and the officer diverge. Everything else in this
    module is the officer speaking US English; a `CoachingContent` row is an explanation in
    the DRIVER'S language, and reading it in the officer's voice would be English phonemes
    applied to Uzbek words — worse than silence, because it teaches a pronunciation nobody
    uses. A locale with no configured voice returns None and keeps its text.
    """
    if isinstance(item, CoachingContent):
        settings = coach_voice(db, item.locale)
        if settings is None:
            return None
        return item.explanation, item.locale, settings
    return item.text, "en", officer_voice(db)


def synthesize_missing(db: DbSession, *, limit: int = 25, storage=None) -> dict:
    """Give every released line a voice. Returns a summary the worker logs.

    AI-CONTEXT: `limit` bounds one pass rather than the whole job — a first run on a real
    content pack is hundreds of lines and one tick should not hold a TTS connection open
    for all of them. The next tick picks up where this stopped, because the query is
    "released and has no audio" rather than a cursor.

    A FAILURE ON ONE LINE DOES NOT ABANDON THE REST. Azure refusing a single string (a
    quota, a bad character) would otherwise leave every later line silent for as long as
    the first one keeps failing, which is how one bad row becomes a mute product.
    """
    pending = variants_needing_audio(db)[:limit]
    if not pending:
        return {"synthesized": 0, "failed": 0, "pending": 0}

    try:
        tts = ai.resolve_tts()
    except ai.SpeechUnavailable:
        # no key on this deployment: say so in the summary rather than raising. The job
        # runs on every box, and a dev machine without Azure is not a fault.
        return {"synthesized": 0, "failed": 0, "pending": len(pending), "tts": "unavailable"}

    owner = content_account(db)
    made = failed = 0
    for variant in pending:
        spoken = _speech_for(db, variant)
        if spoken is None:
            # a language we have no voice for — its explanation stays text, which is a
            # degradation and not a failure, and must not be counted as one or the job
            # would report a fault on every tick forever
            continue
        text, locale, settings = spoken
        try:
            audio = tts.synthesize(text, locale=locale, **settings)
        except Exception:
            failed += 1
            continue
        document = documents.store_document(
            db,
            owner.id,
            documents.DocType.other,
            audio,
            filename=f"m15-{variant.id}.mp3",
            content_type=AUDIO_CONTENT_TYPE,
            storage=storage,
        )
        variant.audio_ref = document.id
        # the same budget the turn spends against — synthesis is not free just because it
        # happens off the driver's clock
        ai.record_audio_minutes(db, "m15", ai.AiTask.tts, max(len(audio) / 320_000.0, 0.02))
        made += 1

    return {
        "synthesized": made,
        "failed": failed,
        "pending": max(len(variants_needing_audio(db)) - made, 0),
    }

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
from .models import Intent, ModelAnswer, OfficerAck

# AI-CONTEXT: a mailbox nobody reads on a domain the owner controls. It exists to satisfy
# an ownership column, never to receive anything, and it holds no credential — F1 will not
# issue a session for an account with no auth method.
CONTENT_ACCOUNT_EMAIL = "content@haulmeter.online"

# MP3 at Azure's default rate. Named here rather than inferred from the bytes, because
# `is_audio` in F6 decides Range support from the content type and a wrong one silently
# turns off seeking.
AUDIO_CONTENT_TYPE = "audio/mpeg"


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
    for table in (ModelAnswer, OfficerAck):
        out.extend(
            db.scalars(
                select(table).where(
                    table.status == ContentStatus.released,
                    table.audio_ref.is_(None),
                )
            )
        )
    return out


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
        try:
            audio = tts.synthesize(variant.text, locale="en")
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

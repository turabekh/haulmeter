"""AI-CONTEXT: the teaching loop (M15-FR5) — what a driver is shown after they miss one.

FR5 names eight steps; this file assembles the material for them and decides nothing about
English. The steps that need content are:

    replay the missed question → explanation in the driver's language → phrase-family
    exposure (3–6 equivalents) → model answer to shadow → retest on a different phrasing

**EVERY PIECE IS RELEASED CONTENT OR IT IS ABSENT.** There is no fallback that invents
text, and no fallback to English for the explanation — Q-9 is explicit that a driver whose
language has no released coaching sees an honest "not yet in your language" rather than
silent English. So `explanation` is None rather than a substitute, and the surface says so.

**THE RETEST IS A DIFFERENT RELEASED VARIANT, NEVER A HOLDOUT** (owner decision, entry
185). Holdouts are reserved for FR7's reassessment, and Q-5 is the reason: a driver tested
on the item they just drilled has been measured on memory. It follows that passing this
retest is *not* proof of transfer, which is a thing to know rather than a thing to fix —
the reassessment is where transfer gets measured.

WHAT COUNTS AS A FAILURE WORTH TEACHING. Not every imperfect turn. Q-2's floor already
excludes what could not be heard, and a repeat request is a diagnostic rather than a miss
(entry 184) — coaching either of those would teach a driver that asking for clarity or
having a poor connection is a language problem, which is the opposite of true.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .content import teachable_variants
from .enums import ContentStatus
from .models import CoachingContent, Intent, ModelAnswer, SkillState, Turn
from .scoring import DIAGNOSTIC_ONLY, FailureTag

# how many equivalents FR5 asks a driver to hear. Fewer is allowed — the pool is what it
# is — but more is noise, and a driver working through eight phrasings of one question has
# stopped learning and started grinding.
PHRASE_FAMILY_MAX = 6

# AI-CONTEXT: tags that are NOT a language failure and must never trigger coaching.
# `REPETITION_REQUIRED` is diagnostic by `DIAGNOSTIC_ONLY`'s own definition, and
# `UNINTELLIGIBLE`/`NO_RESPONSE` are Q-2 states — the recogniser's problem or an empty
# recording, neither of which is evidence about a driver's English.
NOT_A_LANGUAGE_FAILURE = frozenset(
    {t.value for t in DIAGNOSTIC_ONLY}
    | {FailureTag.UNINTELLIGIBLE.value, FailureTag.NO_RESPONSE.value}
)


@dataclass
class CoachingPlan:
    """Everything the coaching surface needs for one missed intent."""

    intent_key: str
    missed_question: str
    missed_question_audio: object | None
    # None means NOT YET IN YOUR LANGUAGE (Q-9) — never a silent English substitute
    explanation: str | None
    # the explanation SPOKEN, in the driver's own language. None when the text exists but
    # the voice has not been synthesized, or when we have no voice for that language at
    # all — a separate absence from `explanation is None`, and the surface must not
    # conflate them: "not yet in your language" and "here, but only in writing" are
    # different things to tell a driver.
    explanation_audio: object | None = None
    glosses: dict = field(default_factory=dict)
    phrase_family: list = field(default_factory=list)
    model_answer: str | None = None
    model_answer_audio: object | None = None
    retest_variant_id: object | None = None
    retest_question: str | None = None


def is_worth_teaching(turn: Turn) -> bool:
    """A miss that says something about the driver's English, and nothing else."""
    tags = [t for t in (turn.failure_tags or [])]
    if not tags:
        return False
    real = [t for t in tags if t.split("(")[0] not in NOT_A_LANGUAGE_FAILURE]
    return bool(real)


def coaching_for(db: DbSession, *, turn: Turn, locale: str) -> CoachingPlan | None:
    """Assemble the loop for one failed turn, or None if there is nothing to teach."""
    if not is_worth_teaching(turn) or turn.intent_id is None:
        return None
    intent = db.get(Intent, turn.intent_id)
    if intent is None:
        return None

    officer = db.scalar(
        select(Turn)
        .where(
            Turn.session_id == turn.session_id,
            Turn.intent_id == intent.id,
            Turn.seq < turn.seq,
        )
        .order_by(Turn.seq.desc())
        .limit(1)
    )
    asked_text = officer.transcript if officer is not None else ""
    # AI-CONTEXT: FR5 STEP 1 IS REPLAY THE MISSED QUESTION, AND IT IS THE OFFICER'S OWN
    # RECORDING. It used to be found by matching his words against the released variants,
    # which held while every line he spoke came out of that table. Since entry 194 he
    # composes his own, the match never succeeds, and the button silently stopped
    # rendering — a driver reads the question they missed with no way to hear it. The
    # audio was never absent; it is on his turn, the exact sound the driver heard at the
    # stop, which is a better replay than a variant's rendering of the same sentence.
    asked_audio = officer.audio_ref if officer is not None else None

    pool = teachable_variants(db, intent.id)
    family = [v for v in pool if v.text != asked_text][:PHRASE_FAMILY_MAX]
    # the retest is a DIFFERENT phrasing; falling back to the asked one is honest when the
    # pool holds only that, and is why the content pass matters
    retest = family[0] if family else (pool[0] if pool else None)

    asked_variant = next((v for v in pool if v.text == asked_text), None)
    model = _model_answer(db, intent.id)

    return CoachingPlan(
        intent_key=intent.key,
        missed_question=asked_text,
        missed_question_audio=asked_audio or (asked_variant.audio_ref if asked_variant else None),
        explanation=_explanation(db, intent.id, locale),
        explanation_audio=_explanation_audio(db, intent.id, locale),
        glosses=_glosses(db, intent.id, locale),
        phrase_family=family,
        model_answer=model.text if model else None,
        model_answer_audio=model.audio_ref if model else None,
        retest_variant_id=retest.id if retest else None,
        retest_question=retest.text if retest else None,
    )


def _released_coaching(db: DbSession, intent_id, locale: str) -> CoachingContent | None:
    return db.scalar(
        select(CoachingContent)
        .where(
            CoachingContent.intent_id == intent_id,
            CoachingContent.locale == locale,
            CoachingContent.review_status == ContentStatus.released,
        )
        .order_by(CoachingContent.version.desc())
        .limit(1)
    )


def _explanation_audio(db: DbSession, intent_id, locale: str):
    """The explanation's voice, if it has been synthesized."""
    row = _released_coaching(db, intent_id, locale)
    return row.audio_ref if row else None


def _explanation(db: DbSession, intent_id, locale: str) -> str | None:
    row = _released_coaching(db, intent_id, locale)
    return row.explanation if row else None


def _glosses(db: DbSession, intent_id, locale: str) -> dict:
    row = _released_coaching(db, intent_id, locale)
    return dict(row.glosses or {}) if row else {}


def _model_answer(db: DbSession, intent_id) -> ModelAnswer | None:
    return db.scalar(
        select(ModelAnswer)
        .where(
            ModelAnswer.intent_id == intent_id,
            ModelAnswer.status == ContentStatus.released,
        )
        .order_by(ModelAnswer.version.desc())
        .limit(1)
    )


# --- skill state: the north star, which nothing wrote ----------------------------------

# SRS ladder from E3 §E3.1.2 FR6 (≈1/3/7/14 days). The intervals live here rather than in
# FR6's scheduler because the LADDER is a property of having practised something; the
# scheduler's job is only to ask what is due.
SRS_LADDER = [1, 3, 7, 14]


def record_practice(db: DbSession, *, account_id, variant_id, success: bool) -> SkillState | None:
    """One practice event against one phrasing. Returns None for a guest.

    AI-CONTEXT: FR5's whole validation is "a driver who failed an intent at baseline passes
    its holdout after the loop — **observed in `skill_state`**", and until this function
    existed the table had no writer at all. The measurement the module is aimed at could
    not be taken.

    GUESTS RECORD NOTHING, and that is a schema fact rather than a decision: `account_id`
    is NOT NULL because skill state belongs to a person, not a browser session. FR1's claim
    flow is what turns a guest's work into a record, and the result surface already asks.
    Returning None rather than raising keeps the loop usable for the guest in front of it.

    FAILURE RESETS THE LADDER rather than stepping back one rung. A phrase you got wrong
    today is not "nearly due in a week"; spaced repetition works because the interval
    reflects what you can currently do.
    """
    if account_id is None:
        return None

    state = db.scalar(
        select(SkillState).where(
            SkillState.account_id == account_id, SkillState.variant_id == variant_id
        )
    )
    if state is None:
        state = SkillState(account_id=account_id, variant_id=variant_id)
        db.add(state)

    state.exposure_count = (state.exposure_count or 0) + 1
    if success:
        state.success_count = (state.success_count or 0) + 1
        rung = min(_rung_of(state.srs_interval) + 1, len(SRS_LADDER) - 1)
    else:
        state.success_count = state.success_count or 0
        rung = 0
    state.srs_interval = SRS_LADDER[rung]
    state.srs_due_at = datetime.now(UTC) + timedelta(days=state.srs_interval)
    db.flush()
    return state


def _rung_of(interval: int | None) -> int:
    if not interval or interval not in SRS_LADDER:
        return -1
    return SRS_LADDER.index(interval)

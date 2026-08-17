"""AI-CONTEXT: the session state machine (M15-FR2 branch selection, M15-FR3 the loop).

TRANSPORT-FREE ON PURPOSE. Everything here works on a `Session` row and a driver's words;
the WebSocket in `api/` is a way to call it, not where it lives. That split is what lets
the whole loop — consent, DRIVING refusal, branch selection, scoring, bands — be tested
without a socket, and it is why a latency problem in the transport can never quietly
become a scoring problem.

THREE REFUSALS COME BEFORE ANY AUDIO, in this order, and the order is the design:

  1. **consent** (M15-FR3) — no consent, no mic. Checked first because it is the only one
     that is about permission rather than safety, and asking a driver to consent *after*
     recording has begun is not consent.
  2. **DRIVING** (Q-4) — refuse to start, hard-pause mid-session. Stricter than M11's
     defer-confirm because there is nothing to defer: a simulation you resume later is a
     different simulation.
  3. **content availability** — an intent with nothing to say cannot open a turn.

DRAFT CONTENT AND Q-6, which look like a contradiction and are not. Q-6 says content ships
reviewed or not at all; E3 §E3.8 says the engine builds against a DEV_SEED **draft**
scenario. Both hold because "a path to a driver" is the thing Q-6 forbids: `allow_draft`
exists, defaults False, and is passed by NOTHING in the request path — the only callers are
tests and the dev probe. A test asserts the production entry point cannot reach draft
content, which is the same structural technique Q-3 uses for org-facing queries. A silent
fallback to draft when nothing is released would be the actual violation, so an empty
released pool raises instead.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from .content import teachable_variants
from .diagnosis import band_for
from .enums import ContentStatus, SessionMode, Speaker, TurnReviewStatus
from .models import (
    Intent,
    OfficerAck,
    PhraseVariant,
    RepairLine,
    ScenarioVersion,
    Session,
    Turn,
)
from .scoring import ASR_CONFIDENCE_FLOOR, FailureTag, Rubric, score_turn


class DriverState(enum.Enum):
    """Mirrors the UI's state machine (`ui/src/core/state.js`) for the half the API needs.

    AI-CONTEXT: the API cannot observe motion — the handset does. So the client TELLS the
    server its state and the server enforces the consequence. That is not a trust hole
    worth closing here: a client that lies about not driving is a client that could simply
    not send the state at all, and the safety property that matters (we never keep a
    session running once we are told it is moving) is enforceable exactly as written.
    """

    IDLE = "IDLE"
    DRIVING = "DRIVING"
    ON_SITE = "ON_SITE"
    RESTING = "RESTING"


class ConsentRequired(PermissionError):
    """No consent recorded — no microphone, and no session."""


class RefusedInMotion(PermissionError):
    """Q-4: nothing interactive happens while the truck is moving."""


class NoContentAvailable(RuntimeError):
    """The scenario has no released content to ask. Never falls back to draft."""


@dataclass
class OfficerTurn:
    intent_key: str
    variant_id: object
    text: str
    audio_ref: object | None
    seq: int


def start_session(
    db: DbSession,
    *,
    scenario: ScenarioVersion,
    account_id=None,
    guest_token=None,
    mode: SessionMode = SessionMode.check,
    consented: bool = False,
    driver_state: DriverState = DriverState.IDLE,
    now: datetime | None = None,
) -> Session:
    """Open a session, or refuse. Consent first, motion second."""
    if not consented:
        raise ConsentRequired(
            "a Roadside Check records the driver's voice; no session opens without "
            "consent recorded first (M15-FR3)"
        )
    if driver_state is DriverState.DRIVING:
        raise RefusedInMotion(
            "sessions do not start in motion (Q-4); this is a refusal, not a deferral — "
            "a simulation resumed later is a different simulation"
        )

    session = Session(
        account_id=account_id,
        guest_token=guest_token,
        scenario_version_id=scenario.id,
        mode=mode,
        consent_at=now or datetime.now(UTC),
    )
    db.add(session)
    db.flush()
    return session


def assert_may_continue(driver_state: DriverState) -> None:
    """Called before every turn. Q-4's hard pause is this, mid-session."""
    if driver_state is DriverState.DRIVING:
        raise RefusedInMotion("session paused: the truck is moving (Q-4)")


def _pool_for(db: DbSession, intent: Intent, *, allow_draft: bool) -> list[PhraseVariant]:
    """The variants an officer may say for this intent.

    Released-only through `teachable_variants`, which also enforces Q-5 (holdouts never
    appear). `allow_draft` is the dev seam described in the module docstring and is passed
    by nothing in the request path.
    """
    pool = teachable_variants(db, intent.id)
    if pool:
        return pool
    if not allow_draft:
        raise NoContentAvailable(
            f"intent {intent.key!r} has no RELEASED variants. This refuses rather than "
            "falling back to draft: draft content reaching a driver is exactly what Q-6 "
            "forbids, and a silent fallback is how it would happen."
        )
    return list(
        db.scalars(
            select(PhraseVariant).where(
                PhraseVariant.intent_id == intent.id,
                PhraseVariant.holdout.is_(False),  # Q-5 holds even in the dev seam
                PhraseVariant.status == ContentStatus.draft,
            )
        )
    )


# AI-CONTEXT: WHEN AN OFFICER ASKS AGAIN (M15-FR2/FR3).
#
# The loop used to ask every intent exactly once, whatever came back. So a driver who said
# "sorry, could you say that again?" — which the scorer RECOGNISES, tags
# REPETITION_REQUIRED and correctly treats as diagnostic rather than a failure — was
# answered with a completely different question. That is not a conversation, and it taught
# a driver that asking for a repeat makes things worse.
#
# NO NEW CONTENT IS INVENTED HERE. A re-ask draws another RELEASED phrasing of the SAME
# intent, which is what the variant pool exists for and what a real officer does: the words
# change, the question does not. Anything else would be F9 text reaching a driver without
# review (Q-6).
#
# THREE TRIGGERS, and each is a moment a real officer would repeat themselves: the driver
# asked; nothing was said; or what was said could not be made out. A wrong answer is NOT a
# trigger — an officer who re-asks until you get it right is running a quiz, and E3's
# taxonomy already carries "misunderstood" as a finding rather than a thing to drill on the
# spot.
REASK_TRIGGERS = frozenset({
    FailureTag.REPETITION_REQUIRED.value,
    FailureTag.UNINTELLIGIBLE.value,
    FailureTag.NO_RESPONSE.value,
})

# ONE repeat, then the officer moves on — which is also what happens at a real window, and
# what stops a driver in a dead microphone from being trapped in a loop forever.
MAX_REASKS_PER_INTENT = 1


def pick_line(db: DbSession, kind: str, *, rng=None) -> OfficerAck | None:
    """One released officer utterance of a kind — "ack", "opening", "closing"."""
    pool = list(
        db.scalars(
            select(OfficerAck).where(
                OfficerAck.status == ContentStatus.released, OfficerAck.kind == kind
            )
        )
    )
    if not pool:
        return None
    if rng is None:
        import random

        return random.choice(pool)
    return pool[rng.randrange(len(pool))]


def repair_for(db: DbSession, intent_id, *, rng=None) -> RepairLine | None:
    """The clarification for an intent the driver answered past (M15-FR2).

    AI-CONTEXT: E3 names these — *"repair/clarification branches ('I'm asking where you
    picked UP this load')"* — and FR2's validation requires one reached and recovered from.
    They are the most human thing in the loop: a real officer neither repeats himself
    verbatim nor moves on in silence, he says which question he asked.

    Released only, like every other line a driver hears (Q-6). None means the officer has
    no clarification for this intent and the loop moves on rather than inventing one.
    """
    pool = list(
        db.scalars(
            select(RepairLine).where(
                RepairLine.intent_id == intent_id,
                RepairLine.status == ContentStatus.released,
            )
        )
    )
    if not pool:
        return None
    if rng is None:
        import random

        return random.choice(pool)
    return pool[rng.randrange(len(pool))]


def pick_acknowledgement(db: DbSession, *, rng=None) -> OfficerAck | None:
    """What the officer says before moving on. None when no ack has been released.

    AI-CONTEXT: this is the difference between an interview and a form, and it is the
    thing the owner named when they said the product felt robotic. A real officer says
    "alright" before the next question; the absence of that is most of what makes a
    question-answer-question loop feel like a machine.

    RANDOM, so a driver does not hear the same syllable six times in one stop — the same
    argument as the phrase-variant pool, applied to the smallest possible utterance.

    None is a legitimate answer and the socket simply omits the frame: an ack is content
    and content that has not been reviewed does not reach a driver (Q-6), even when it is
    one word long.
    """
    return pick_line(db, "ack", rng=rng)


def intent_to_repair(db: DbSession, session: Session) -> Intent | None:
    """The intent the driver answered PAST, if the officer should clarify it (M15-FR2).

    AI-CONTEXT: this is the correction to entry 184's reasoning, which said a wrong answer
    must not trigger a re-ask because "an officer who re-asks until you get it right is
    running a quiz". True of REPEATING the same question, and it left the loop shrugging at
    a misunderstanding and moving on — which no officer does. Clarifying is a different
    act: it happens ONCE, it says something new, and recovering from it is what FR2's
    validation is about.
    """
    last = db.scalar(
        select(Turn)
        .where(Turn.session_id == session.id, Turn.speaker == Speaker.driver)
        .order_by(Turn.seq.desc())
        .limit(1)
    )
    if last is None or last.intent_id is None:
        return None
    if FailureTag.INTENT_MISUNDERSTOOD.value not in (last.failure_tags or []):
        return None
    # once. A second clarification of the same question is the quiz entry 184 warned about.
    already = db.scalar(
        select(func.count(Turn.id)).where(
            Turn.session_id == session.id,
            Turn.speaker == Speaker.officer,
            Turn.intent_id == last.intent_id,
        )
    ) or 0
    if already > 1:
        return None
    return db.get(Intent, last.intent_id)


def _intent_to_reask(db: DbSession, session: Session) -> Intent | None:
    """The intent the officer should ask again, or None to move on."""
    last = db.scalar(
        select(Turn)
        .where(Turn.session_id == session.id, Turn.speaker == Speaker.driver)
        .order_by(Turn.seq.desc())
        .limit(1)
    )
    if last is None or last.intent_id is None:
        return None
    if not REASK_TRIGGERS.intersection(last.failure_tags or []):
        return None

    asked_times = (
        db.scalar(
            select(func.count(Turn.id)).where(
                Turn.session_id == session.id,
                Turn.speaker == Speaker.officer,
                Turn.intent_id == last.intent_id,
            )
        )
        or 0
    )
    if asked_times > MAX_REASKS_PER_INTENT:
        return None
    return db.get(Intent, last.intent_id)


def _already_said(db: DbSession, session: Session, intent_id) -> set[str]:
    """The phrasings this session has already used for an intent, so a repeat REPHRASES."""
    return set(
        db.scalars(
            select(Turn.transcript).where(
                Turn.session_id == session.id,
                Turn.speaker == Speaker.officer,
                Turn.intent_id == intent_id,
            )
        )
    )


def next_officer_turn(
    db: DbSession,
    session: Session,
    *,
    driver_state: DriverState = DriverState.IDLE,
    allow_draft: bool = False,
    rng=None,
) -> OfficerTurn | None:
    """Choose the next intent and one of its phrasings. None when the scenario is done.

    AI-CONTEXT: intent-first, which is E3 §E3.1.2's word and matters for anti-memorisation.
    The scenario names WHICH intents in which order; the phrasing is drawn from that
    intent's pool, so two drivers running the same scenario hear different sentences and a
    driver running it twice does not learn the script.
    """
    assert_may_continue(driver_state)

    scenario = db.get(ScenarioVersion, session.scenario_version_id)

    # AI-CONTEXT: REPAIR FIRST. A driver who answered the wrong question gets told which
    # question it was, once, before anything else happens — that is FR2's repair branch and
    # it outranks both a rephrase and moving on.
    repair_intent = intent_to_repair(db, session)
    if repair_intent is not None:
        repair = repair_for(db, repair_intent.id)
        if repair is not None:
            seq = int(
                db.scalar(
                    select(func.coalesce(func.max(Turn.seq), 0)).where(
                        Turn.session_id == session.id
                    )
                )
                or 0
            )
            turn = Turn(
                session_id=session.id,
                seq=seq + 1,
                speaker=Speaker.officer,
                intent_id=repair_intent.id,
                transcript=repair.text,
                expected_slots=expected_slots_for(repair_intent, scenario),
            )
            db.add(turn)
            db.flush()
            return OfficerTurn(
                intent_key=repair_intent.key,
                variant_id=repair.id,
                text=repair.text,
                audio_ref=repair.audio_ref,
                seq=turn.seq,
            )

    intent = _intent_to_reask(db, session)
    if intent is None:
        asked = set(
            db.scalars(
                select(Intent.key)
                .join(Turn, Turn.intent_id == Intent.id)
                .where(Turn.session_id == session.id, Turn.speaker == Speaker.officer)
            )
        )
        remaining = [k for k in (scenario.allowed_intents or []) if k not in asked]
        if not remaining:
            return None

        intent = db.scalar(select(Intent).where(Intent.key == remaining[0]))
        if intent is None:
            raise NoContentAvailable(
                f"scenario names intent {remaining[0]!r} which does not exist"
            )

    pool = _pool_for(db, intent, allow_draft=allow_draft)
    if not pool:
        raise NoContentAvailable(f"intent {intent.key!r} has an empty variant pool")

    # a repeat REPHRASES where the pool allows it — hearing the identical sentence twice
    # teaches nothing about understanding it, and the second phrasing is often the one that
    # lands. Falls back to the whole pool when every phrasing has been used.
    said = _already_said(db, session, intent.id)
    fresh = [v for v in pool if v.text not in said] or pool

    variant = fresh[0] if rng is None else fresh[rng.randrange(len(fresh))]
    seq = int(
        db.scalar(
            select(func.coalesce(func.max(Turn.seq), 0)).where(Turn.session_id == session.id)
        )
        or 0
    )

    turn = Turn(
        session_id=session.id,
        seq=seq + 1,
        speaker=Speaker.officer,
        intent_id=intent.id,
        transcript=variant.text,
        expected_slots=expected_slots_for(intent, scenario),
    )
    db.add(turn)
    db.flush()
    return OfficerTurn(
        intent_key=intent.key,
        variant_id=variant.id,
        text=variant.text,
        audio_ref=variant.audio_ref,
        seq=turn.seq,
    )


def expected_slots_for(intent: Intent, scenario: ScenarioVersion) -> dict[str, str]:
    """The FACTS this question expects, resolved from the scenario's hidden state.

    AI-CONTEXT: `intent.required_slots` names WHICH facts a question needs; the scenario's
    `hidden_state` holds what they actually are. Using the former as the answer key scored
    a driver who said "six hours today" as incomplete, because it checked whether they had
    said the word "required" — the defect a real session found and no unit test could,
    since every test supplied its expected slots directly.

    A slot the scenario has no fact for is DROPPED rather than kept unanswerable: a
    question we cannot mark cannot be failed.
    """
    facts = scenario.hidden_state or {}
    return {
        slot: str(facts[slot])
        for slot in (intent.required_slots or {})
        if slot in facts and facts[slot] not in (None, "")
    }


def record_driver_turn(
    db: DbSession,
    session: Session,
    *,
    officer: OfficerTurn,
    transcript: str | None,
    asr_confidence: float | None,
    rubric: Rubric,
    audio_ref=None,
    driver_state: DriverState = DriverState.IDLE,
) -> Turn:
    """Score the driver's answer and write the turn.

    A turn below the ASR floor is written as `REVIEW_NEEDED` with no scores — Q-2, and the
    place it actually takes effect.
    """
    assert_may_continue(driver_state)

    intent = db.scalar(select(Intent).where(Intent.key == officer.intent_key))
    scenario = db.get(ScenarioVersion, session.scenario_version_id)
    expected = expected_slots_for(intent, scenario) if intent and scenario else {}
    result = score_turn(
        officer_line=officer.text,
        transcript=transcript,
        intent_key=officer.intent_key,
        expected_slots=expected,
        asr_confidence=asr_confidence,
        rubric=rubric,
    )

    turn = Turn(
        session_id=session.id,
        seq=officer.seq + 1,
        speaker=Speaker.driver,
        intent_id=intent.id if intent else None,
        audio_ref=audio_ref,
        transcript=transcript,
        asr_confidence=asr_confidence,
        expected_slots=expected,
        observed_slots=result.slots.filled,
        scores=result.scores,
        failure_tags=result.failure_tags,
        review_status=(
            TurnReviewStatus.review_needed if result.review_needed else TurnReviewStatus.not_needed
        ),
    )
    db.add(turn)
    db.flush()
    return turn


def complete_session(db: DbSession, session: Session, *, now: datetime | None = None):
    """Close the session and compute its band. The band always carries `provisional`."""
    scores = list(
        db.scalars(
            select(Turn.scores).where(
                Turn.session_id == session.id, Turn.speaker == Speaker.driver
            )
        )
    )
    verdict = band_for(db, [s for s in scores if s])
    session.completed_at = now or datetime.now(UTC)
    session.band = verdict.band.value
    session.provisional = verdict.provisional
    db.flush()
    return verdict


def review_needed_count(db: DbSession, session: Session) -> int:
    """How many turns nobody could hear. Surfaced so a result screen can say so honestly."""
    return int(
        db.scalar(
            select(func.count())
            .select_from(Turn)
            .where(
                Turn.session_id == session.id,
                Turn.review_status == TurnReviewStatus.review_needed,
            )
        )
        or 0
    )


__all__ = [
    "ASR_CONFIDENCE_FLOOR",
    "ConsentRequired",
    "DriverState",
    "NoContentAvailable",
    "OfficerTurn",
    "RefusedInMotion",
    "assert_may_continue",
    "complete_session",
    "expected_slots_for",
    "next_officer_turn",
    "record_driver_turn",
    "review_needed_count",
    "start_session",
]

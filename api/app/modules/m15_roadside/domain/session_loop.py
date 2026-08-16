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
from .models import Intent, PhraseVariant, ScenarioVersion, Session, Turn
from .scoring import ASR_CONFIDENCE_FLOOR, Rubric, score_turn


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
        raise NoContentAvailable(f"scenario names intent {remaining[0]!r} which does not exist")

    pool = _pool_for(db, intent, allow_draft=allow_draft)
    if not pool:
        raise NoContentAvailable(f"intent {intent.key!r} has an empty variant pool")

    variant = pool[0] if rng is None else pool[rng.randrange(len(pool))]
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
        expected_slots=dict(intent.required_slots or {}),
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
    expected = dict(intent.required_slots or {}) if intent else {}
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
    "next_officer_turn",
    "record_driver_turn",
    "review_needed_count",
    "start_session",
]

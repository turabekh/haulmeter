"""AI-CONTEXT: the rubric runs after the conversation, not inside it.

WHY THIS MODULE EXISTS, measured rather than assumed. A full exchange cost ~5.5s from the
moment a driver stopped speaking to the moment the officer spoke again, and the legs on the
production box were: STT 0.32s, **rubric 3.41s**, echo synthesis 0.25s, the officer's own
line 1.24s, his voice 0.25s. The rubric was the largest single cost in a spoken
conversation — and what it produces is what a driver is told about their English ON THE
RESULT SCREEN. Nobody was waiting for it. Every driver was.

THE CORRECTNESS RULE THIS MODULE HOLDS: **a band is never computed over a partial set.**
`settle_session_scores` is called by the result path before any band is derived, so a
session with pending turns is finished first and only then judged. The worker sweep is the
FAST path, not the correct one — a worker that is down makes the result screen slower,
never wrong, and that is the whole reason the settle is a function the reader calls rather
than a state the reader hopes for.

WHAT A FAILING RUBRIC MEANS HERE, and it is the same answer as everywhere else in this
module: `RubricUnavailable` becomes REVIEW_NEEDED, never a verdict. An outage, an exhausted
budget or unreadable output must not become a statement about this driver's English
invented by an accident (Q-2). A turn that cannot be settled is marked `done` with
REVIEW_NEEDED rather than left `pending` forever — a queue that never drains would make the
result screen hang on a driver who has finished talking.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .enums import Speaker, TurnReviewStatus
from .models import Intent, Session, Turn
from .rubric_f9 import F9Rubric, RubricUnavailable
from .scoring import score_turn

PENDING = "pending"
DONE = "done"


def pending_turns(db: DbSession, session_id) -> list[Turn]:
    return list(
        db.scalars(
            select(Turn)
            .where(Turn.session_id == session_id, Turn.scoring_state == PENDING)
            .order_by(Turn.seq)
        )
    )


def _officer_line_before(db: DbSession, turn: Turn) -> str:
    officer = db.scalar(
        select(Turn)
        .where(
            Turn.session_id == turn.session_id,
            Turn.speaker == Speaker.officer,
            Turn.seq < turn.seq,
        )
        .order_by(Turn.seq.desc())
        .limit(1)
    )
    return (officer.transcript or "") if officer else ""


def settle_turn(db: DbSession, turn: Turn, *, rubric=None, account_id=None) -> Turn:
    """Run the model's judgement on one pending turn and write the result.

    AI-CONTEXT: re-scores through `score_turn` — the SAME function the inline path used —
    rather than patching the deterministic result. Two scorers that must agree is a bug
    waiting for a quiet afternoon; one scorer called later is just a scorer called later.
    """
    if turn.scoring_state != PENDING:
        return turn

    intent = db.get(Intent, turn.intent_id) if turn.intent_id else None
    rubric = rubric or F9Rubric(db, account_id=account_id)
    try:
        result = score_turn(
            officer_line=_officer_line_before(db, turn),
            transcript=turn.transcript,
            intent_key=intent.key if intent else "",
            expected_slots=turn.expected_slots or {},
            asr_confidence=turn.asr_confidence,
            rubric=rubric,
        )
    except RubricUnavailable:
        # never a verdict invented by an outage (Q-2) — and never left pending, because a
        # queue that does not drain becomes a result screen that does not load
        turn.review_status = TurnReviewStatus.review_needed
        turn.scoring_state = DONE
        db.flush()
        return turn

    turn.scores = result.scores
    turn.failure_tags = result.failure_tags
    turn.observed_slots = result.slots.filled
    turn.review_status = (
        TurnReviewStatus.review_needed if result.review_needed else TurnReviewStatus.not_needed
    )
    turn.scoring_state = DONE
    db.flush()
    return turn


def settle_session_scores(db: DbSession, session: Session, *, rubric=None) -> int:
    """Finish every pending turn in this session. Returns how many were settled.

    Called before a band is computed, which is what makes deferral safe: the result a
    driver reads is derived from a complete set or it is not derived at all.
    """
    turns = pending_turns(db, session.id)
    for turn in turns:
        settle_turn(db, turn, rubric=rubric, account_id=session.account_id)
    return len(turns)


def sweep(db: DbSession, *, limit: int = 50) -> dict:
    """The worker's pass: settle whatever is waiting, oldest first.

    AI-CONTEXT: the FAST path only. Correctness belongs to `settle_session_scores` on the
    result path — if this never ran at all, every driver would still get a right answer,
    just after a wait at the end. Bounded so one long session cannot monopolise a tick.
    """
    turns = list(
        db.scalars(
            select(Turn)
            .where(Turn.scoring_state == PENDING)
            .order_by(Turn.seq)
            .limit(limit)
        )
    )
    for turn in turns:
        session = db.get(Session, turn.session_id)
        settle_turn(db, turn, account_id=session.account_id if session else None)
    return {"settled": len(turns)}

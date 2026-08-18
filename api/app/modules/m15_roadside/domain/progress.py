"""AI-CONTEXT: what a driver has done and where they stand (M15-FR6's progress strip).

THE STRIP REPORTS WHAT THE TABLE KNOWS, NOT WHAT FR6's PROSE NAMES. FR6 describes a
"heard / understood / answered" three-state strip. `skill_state` carries `exposure_count`
and `success_count` and nothing between them — "understood" has no column, and no
combination of the two means it. Splitting one counter into three labels would put a
distinction on screen that the data cannot support, which is the failure this codebase
keeps paying for: a number that reads as measured and was invented. So the strip is
seen / passed / due, each of which is a column, and the third state waits for a column
that means it.

EVERY QUERY HERE TAKES AN ACCOUNT AND NOTHING ELSE. The history list hands session ids to
a surface, so its scoping is the thing standing between a driver and a stranger's stops.
There is no "all sessions" path in this module for a driver-facing caller to reach for.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from .enums import SessionMode
from .models import Session, SkillState

# How many past stops the history returns. A driver who has run more than this has a
# scrolling problem, not a memory problem — the surface is a program home, not an archive.
HISTORY_LIMIT = 20


@dataclass(frozen=True)
class Readiness:
    """The latest completed check, or nothing.

    `provisional` rides along from the session rather than being recomputed: Q-8 says a
    band is provisional until the calibration gate is met, and the band a driver was
    SHOWN is the one the row recorded. Re-deriving it here would let a screen disagree
    with the result screen about the same stop.
    """

    band: str | None
    provisional: bool
    checked_at: datetime | None


@dataclass(frozen=True)
class SkillSummary:
    seen: int
    passed: int
    due: int


def latest_readiness(db: DbSession, account_id: uuid.UUID | None) -> Readiness:
    if account_id is None:
        return Readiness(band=None, provisional=True, checked_at=None)
    row = db.scalars(
        select(Session)
        .where(
            Session.account_id == account_id,
            Session.completed_at.is_not(None),
            Session.band.is_not(None),
            # a practice run is not a reading of where the driver stands, and E3.1.4 makes
            # the distinction a column precisely so surfaces do not have to guess
            Session.mode.in_([SessionMode.check, SessionMode.reassessment]),
        )
        .order_by(Session.completed_at.desc())
        .limit(1)
    ).first()
    if row is None:
        return Readiness(band=None, provisional=True, checked_at=None)
    return Readiness(band=row.band, provisional=row.provisional, checked_at=row.completed_at)


def skill_summary(db: DbSession, account_id: uuid.UUID | None) -> SkillSummary:
    if account_id is None:
        return SkillSummary(seen=0, passed=0, due=0)
    now = datetime.now(UTC)
    seen, passed, due = db.execute(
        select(
            func.count(SkillState.id),
            func.count(SkillState.id).filter(SkillState.success_count > 0),
            func.count(SkillState.id).filter(SkillState.srs_due_at <= now),
        ).where(SkillState.account_id == account_id)
    ).one()
    return SkillSummary(seen=seen or 0, passed=passed or 0, due=due or 0)


def session_history(db: DbSession, account_id: uuid.UUID | None) -> list[Session]:
    """The driver's own stops, newest first.

    Started-but-abandoned sessions are INCLUDED. A driver who walked out of a stop
    half-way still did it, and hiding the row makes the history disagree with their
    memory — which is the surface's whole job.
    """
    if account_id is None:
        return []
    return list(
        db.scalars(
            select(Session)
            .where(Session.account_id == account_id)
            .order_by(Session.started_at.desc())
            .limit(HISTORY_LIMIT)
        ).all()
    )

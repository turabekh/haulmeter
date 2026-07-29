"""AI-CONTEXT: M10 Community & Points HTTP endpoints — thin over
m10_community.public. Points balance + reputation, the free-lot spot-handoff
relay (geofence-proven both ends), and moderated facility Q&A (answers from
geofence-present drivers). Redemption is only against M6 bookings (PRD §8.10).
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import canonical_facility_id, current_account, get_db, require_module
from app.api.events import publish_handoff
from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.modules.m10_community import public as m10

router = APIRouter(prefix="/community", tags=["community"],
    # PRD §6: the module's own flag, gating every route in it (§23 entry 105)
    dependencies=[Depends(require_module("m10_community"))],
)


class BroadcastIn(BaseModel):
    facility_id: uuid.UUID
    leaving_in_minutes: int


class QuestionIn(BaseModel):
    facility_id: uuid.UUID
    text: str


class AnswerIn(BaseModel):
    text: str


@router.get("/points")
def points(
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    rep = m10.reputation(db, account.id)
    return {
        "balance": m10.points_balance(db, account.id),
        "points_earned": rep.points_earned,
        "contribution_count": rep.contribution_count,
        "trust_score": rep.trust_score,
        "level": rep.level,
    }


@router.get("/leaderboard")
def leaderboard(
    limit: int = 10,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [
        {"account_id": str(r["account_id"]), "points": r["points"]}
        for r in m10.leaderboard(db, limit)
    ]


@router.post("/handoff", status_code=201)
def broadcast(
    body: BroadcastIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    now = datetime.now(UTC)
    try:
        handoff = m10.broadcast_handoff(
            db,
            account.id,
            canonical_facility_id(body.facility_id, db),
            now + timedelta(minutes=body.leaving_in_minutes),
            now,
        )
    except m10.NotFreeLot as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "handoffs are free-lot only") from exc
    except m10.NotPresent as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "must be on-site to relay") from exc
    # §23 entry 103: tell whoever is listening nearby, right now. This is the ONLY
    # thing the live channel adds — the row is already written and already returned by
    # /handoff/nearby, so a failed publish costs a driver freshness and nothing else.
    fac = facility.get_facility(db, handoff.facility_ref)
    if fac is not None:
        lat, lon = facility.coordinates(db, fac)
        publish_handoff(handoff, lat, lon)
    return {"handoff_id": str(handoff.id), "state": handoff.state.value}


@router.get("/handoff/nearby")
def nearby(
    lat: float,
    lon: float,
    radius_m: float = 8000,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> list[dict]:
    out = []
    for h in m10.nearby_handoffs(db, lat, lon, radius_m):
        fac = facility.get_facility(db, h.facility_ref)
        out.append(
            {
                "handoff_id": str(h.id),
                "facility_name": fac.name if fac else None,
                "leaving_at": h.leaving_at.isoformat(),
                "mine": h.broadcaster_id == account.id,
            }
        )
    return out


def _handoff_or_404(db: Session, handoff_id: uuid.UUID):
    h = db.get(m10.Handoff, handoff_id)
    if h is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "handoff not found")
    return h


@router.post("/handoff/{handoff_id}/claim", status_code=201)
def claim(
    handoff_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    h = _handoff_or_404(db, handoff_id)
    try:
        m10.claim_handoff(db, h, account.id, datetime.now(UTC))
    except m10.HandoffNotClaimable as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "already claimed") from exc
    return {"handoff_id": str(h.id), "state": h.state.value}


@router.post("/handoff/{handoff_id}/confirm", status_code=201)
def confirm(
    handoff_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    # the claimer's arrival confirms the handoff; both earn
    h = _handoff_or_404(db, handoff_id)
    try:
        m10.confirm_handoff(db, h, datetime.now(UTC))
    except m10.HandoffNotClaimable as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "not claimed") from exc
    except m10.NotPresent as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "claimer must be on-site") from exc
    return {"handoff_id": str(h.id), "state": h.state.value}


@router.get("/questions/{facility_id}")
def questions(
    facility_id: uuid.UUID = Depends(canonical_facility_id),
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [
        {
            "question_id": str(q.id),
            "text": q.text,
            "answers": [{"text": a.text, "presence_proven": a.presence_proven} for a in q.answers],
        }
        for q in m10.list_questions(db, facility_id)
    ]


@router.post("/questions", status_code=201)
def ask(
    body: QuestionIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    q = m10.ask_question(
        db, account.id, canonical_facility_id(body.facility_id, db), body.text, datetime.now(UTC)
    )
    return {"question_id": str(q.id)}


@router.post("/questions/{question_id}/answers", status_code=201)
def answer(
    question_id: uuid.UUID,
    body: AnswerIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    q = db.get(m10.FacilityQuestion, question_id)
    if q is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "question not found")
    a = m10.answer_question(db, account.id, q, body.text, datetime.now(UTC))
    return {"answer_id": str(a.id), "presence_proven": a.presence_proven}

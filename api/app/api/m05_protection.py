"""AI-CONTEXT: M5 Protection HTTP endpoints — thin over m05_protection.public.
Document wallet + inspection mode are reads; on-time proof / condition / incident
are captures (F4 evidence). F8 gateway seam (recording) in dev.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_account, get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f05_load import public as loads
from app.foundation.f08_notifications import public as notify
from app.modules.m05_protection import public as m5

router = APIRouter(prefix="/protection", tags=["protection"])

_GATEWAY = notify.RecordingNotificationGateway()  # F8 seam (dev)


class OnTimeIn(BaseModel):
    stop_id: uuid.UUID
    checked_in_at: str  # ISO 8601
    notify_counterparty: bool = False


class IncidentIn(BaseModel):
    kind: str
    note: str | None = None


@router.post("/on-time", status_code=201)
def on_time(
    body: OnTimeIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    from datetime import datetime

    stop = loads.get_stop(db, body.stop_id)
    if stop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stop not found")
    load = loads.get_load(db, stop.load_id)
    email = None
    if load is not None and load.counterparty_id is not None:
        cp = loads.get_counterparty(db, load.counterparty_id)
        email = cp.contact_email if cp is not None else None
    proof = m5.file_on_time_proof(
        db,
        stop,
        account.id,
        datetime.fromisoformat(body.checked_in_at),
        notify_counterparty=body.notify_counterparty,
        counterparty_ref=load.counterparty_id if load else None,
        counterparty_email=email,
        gateway=_GATEWAY,
    )
    return {
        "proof_id": str(proof.id),
        "within_window": proof.within_window,
        "notice_sent": proof.notice_sent,
    }


@router.get("/wallet")
def wallet(
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    return m5.wallet(db, account.id)


@router.get("/inspection")
def inspection(
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> list[dict]:
    return m5.inspection_mode(db, account.id)


@router.post("/incident", status_code=201)
def incident(
    body: IncidentIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    inc = m5.capture_incident(db, account.id, body.kind, note=body.note)
    return {"incident_id": str(inc.id), "evidence_log_ref": str(inc.evidence_log_ref)}


@router.get("/summary/{stop_id}")
def summary(
    stop_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    stop = loads.get_stop(db, stop_id)
    if stop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stop not found")
    return m5.protection_summary(db, stop)

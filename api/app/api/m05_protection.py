"""AI-CONTEXT: M5 Protection HTTP endpoints — thin over m05_protection.public.
Document wallet + inspection mode are reads; on-time proof / condition / incident
are captures (F4 evidence). F8 gateway seam (recording) in dev.
"""

import base64
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_account, get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f05_load import public as loads
from app.foundation.f08_notifications import public as notify
from app.foundation.f12_offline import public as offline
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
    idempotency_key: str | None = Header(default=None),
) -> dict:
    # F12: a key makes an offline-then-replayed incident create exactly one record
    result: dict = {}

    def _apply(_env):
        inc = m5.capture_incident(db, account.id, body.kind, note=body.note)
        result["incident_id"] = str(inc.id)
        result["evidence_log_ref"] = str(inc.evidence_log_ref)

    if idempotency_key:
        receipt = offline.ingest(
            db,
            account.id,
            idempotency_key,
            "incident",
            {"kind": body.kind},
            datetime.now(UTC),
            handler=_apply,
        )
        return {**result, "applied": receipt.applied}
    _apply(None)
    return {**result, "applied": True}


# --- Cargo-condition capture (M5-FR2): a guided, hash-chained photo sequence ---
class ConditionStartIn(BaseModel):
    stop_id: uuid.UUID
    phase: str = "delivery"  # pickup | delivery


@router.get("/condition/sequence")
def condition_sequence(
    account: identity.Account = Depends(current_account),
) -> list[str]:
    return m5.condition_sequence()


@router.post("/condition/start", status_code=201)
def condition_start(
    body: ConditionStartIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    stop = loads.get_stop(db, body.stop_id)
    if stop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stop not found")
    phase = m5.CapturePhase(body.phase)
    capture = m5.start_condition_capture(db, stop, account.id, phase)
    return {"capture_id": str(capture.id), "sequence": m5.condition_sequence()}


class ConditionPhotoIn(BaseModel):
    prompt: str
    content_b64: str | None = None  # the captured image; a dev placeholder if absent
    content_type: str | None = None  # the image MIME type, so it serves back honestly


@router.post("/condition/{capture_id}/photo", status_code=201)
def condition_photo(
    capture_id: uuid.UUID,
    body: ConditionPhotoIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None),
) -> dict:
    capture = db.get(m5.ConditionCapture, capture_id)
    if capture is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "capture not found")
    if capture.account_id != account.id:
        # never let another account append to someone's evidence chain (tampering)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your capture")

    def _apply(_env):
        content = (
            base64.b64decode(body.content_b64)
            if body.content_b64
            else f"photo:{body.prompt}".encode()
        )
        m5.add_condition_photo(
            db, capture, body.prompt, content=content, content_type=body.content_type
        )

    # F12: an offline photo replayed with its key appends exactly once (no dup chain)
    applied = True
    if idempotency_key:
        receipt = offline.ingest(
            db,
            account.id,
            idempotency_key,
            "condition_photo",
            {"capture_id": str(capture_id), "prompt": body.prompt},
            datetime.now(UTC),
            handler=_apply,
        )
        applied = receipt.applied
    else:
        _apply(None)
    return {
        "capture_id": str(capture.id),
        "photo_count": capture.photo_count,
        "prompt": body.prompt,
        "applied": applied,
    }


@router.get("/summary/{stop_id}")
def summary(
    stop_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    stop = loads.get_stop(db, stop_id)
    if stop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stop not found")
    load = loads.get_load(db, stop.load_id)
    if load is None or load.account_id != account.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your stop")
    return m5.protection_summary(db, stop)

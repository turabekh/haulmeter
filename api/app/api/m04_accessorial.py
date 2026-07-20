"""AI-CONTEXT: M4 Accessorial HTTP endpoints — thin over m04_accessorial.public.
TONU / layover / lumper file through the shared M3 invoice rail; /accessorial/owed
is the unified Money-Owed view. F8/F9 provider seams (recording gateway + fake
model) in dev until the real adapters are wired.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_account, get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f05_load import public as loads
from app.foundation.f08_notifications import public as notify
from app.foundation.f09_ai_gateway import public as ai
from app.modules.m04_accessorial import public as m4

router = APIRouter(prefix="/accessorial", tags=["accessorial"])

_GATEWAY = notify.RecordingNotificationGateway()  # F8 seam (dev)
_PROVIDER = ai.FakeModelProvider()  # F9 seam (dev)


class TonuIn(BaseModel):
    load_id: uuid.UUID
    amount_cents: int


class LayoverIn(BaseModel):
    stop_id: uuid.UUID
    layover_rate_cents: int


class LumperIn(BaseModel):
    load_id: uuid.UUID
    amount_cents: int


def _require_load(db, load_id):
    load = loads.get_load(db, load_id)
    if load is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "load not found")
    return load


def _claim_out(claim) -> dict:
    return {
        "claim_id": str(claim.id),
        "kind": claim.kind.value,
        "amount_cents": claim.amount_cents,
        "receivable_ref": str(claim.receivable_ref) if claim.receivable_ref else None,
    }


@router.post("/tonu", status_code=201)
def tonu(
    body: TonuIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    load = _require_load(db, body.load_id)
    return _claim_out(m4.file_tonu(db, load, body.amount_cents, gateway=_GATEWAY))


@router.post("/layover", status_code=201)
def layover(
    body: LayoverIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    stop = loads.get_stop(db, body.stop_id)
    if stop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stop not found")
    try:
        claim = m4.file_layover(db, stop, body.layover_rate_cents, gateway=_GATEWAY)
    except m4.NoLayover as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _claim_out(claim)


@router.post("/lumper", status_code=201)
def lumper(
    body: LumperIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    load = _require_load(db, body.load_id)
    claim = m4.file_lumper(
        db, load, _PROVIDER, receipt_bytes=b"", amount_cents=body.amount_cents, gateway=_GATEWAY
    )
    return _claim_out(claim)


@router.get("/owed")
def owed(
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> list[dict]:
    return m4.money_owed(db, account.id)

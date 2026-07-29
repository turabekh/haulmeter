"""AI-CONTEXT: M3 Detention HTTP endpoints — thin over m03_detention.public.
The counterparty-email send uses the F8 gateway seam (recording in dev until the
real transactional-email provider is wired at activation).
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_account, get_db, require_module
from app.foundation.f01_identity import public as identity
from app.foundation.f05_load import public as loads
from app.foundation.f08_notifications import public as notify
from app.modules.m03_detention import public as m3

router = APIRouter(prefix="/detention", tags=["detention"],
    # PRD §6: the module's own flag, gating every route in it (§23 entry 105)
    dependencies=[Depends(require_module("m03_detention"))],
)

_GATEWAY = notify.RecordingNotificationGateway()  # F8 seam (dev)


class StartIn(BaseModel):
    stop_id: uuid.UUID


@router.post("/start", status_code=201)
def start(
    body: StartIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    stop = loads.get_stop(db, body.stop_id)
    if stop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stop not found")
    claim = m3.start_claim(db, stop)
    return {"claim_id": str(claim.id), "mode": claim.mode.value}


def _load_claim(db: Session, claim_id: uuid.UUID, account: identity.Account) -> m3.DetentionClaim:
    # a detention claim is private to its driver: 404 if missing, 403 if not theirs
    claim = m3.get_claim(db, claim_id)
    if claim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "claim not found")
    if claim.account_id != account.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your claim")
    return claim


@router.get("/{claim_id}/clock")
def clock(
    claim_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    claim = _load_claim(db, claim_id, account)
    state = m3.clock(db, claim, now=datetime.now(UTC))
    return {
        "phase": state.phase.value,
        "free_time_remaining_seconds": state.free_time_remaining_seconds,
        "detention_seconds": state.detention_seconds,
        "amount_cents": state.amount_cents,
    }


@router.post("/{claim_id}/pack")
def pack(
    claim_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    claim = _load_claim(db, claim_id, account)
    result = m3.generate_pack(db, claim, now=datetime.now(UTC), gateway=_GATEWAY)
    return {
        "claim_id": str(claim.id),
        "amount_cents": claim.amount_cents,
        "state": claim.state.value,
        "chain_valid": result["pack"].verification["chain_valid"],
        "receivable_ref": str(claim.receivable_ref) if claim.receivable_ref else None,
    }

"""AI-CONTEXT: M3 Detention HTTP endpoints — thin over m03_detention.public.
The counterparty-email send uses the F8 gateway seam (recording in dev until the
real transactional-email provider is wired at activation).
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
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

# AI-CONTEXT: the REAL counterparty transport (§23 entry 122). This was a recording
# gateway — an in-memory list — at every one of the seven send sites, so the F8 rows
# said the notice was sent and nothing ever left the box. Resolves SMTP-or-recording
# at send time, so the suite (SMTP_HOST blanked in conftest) and the app differ by
# configuration alone.
_GATEWAY = notify.counterparty_gateway()


def already_filed(exc: m3.ClaimAlreadyFiled) -> HTTPException:
    """409, carrying the receivable the FIRST filing opened (finding F2).

    AI-CONTEXT: the status matters as much as the guard. A retry after a success — a
    double-tap, a queued request replayed when the truck comes back into signal — is not
    an error the driver did anything about, and reporting it as one invites them to try
    again on a claim that is already with the broker. 409 plus the existing
    `receivable_ref` lets the client say "already filed" and show the same money.
    Imported by `app.api.load` too, so both callers cannot drift apart.
    """
    claim = exc.claim
    return HTTPException(
        status.HTTP_409_CONFLICT,
        {
            "error": "already_filed",
            "claim_id": str(claim.id),
            "state": claim.state.value,
            "amount_cents": claim.amount_cents,
            "receivable_ref": str(claim.receivable_ref) if claim.receivable_ref else None,
        },
    )


class StartIn(BaseModel):
    stop_id: uuid.UUID


@router.post("/start")
def start(
    body: StartIn,
    response: Response,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    """Start (or return) the detention claim for a stop.

    AI-CONTEXT: finding F3 — this checked that the stop EXISTED and never that it was the
    caller's, so any authenticated driver could open a claim against any stop in the
    database and read its clock through `/detention/{id}/clock` after. Every other
    stop-scoped route in the product goes through `_owned_stop`; this one did not, and the
    web app never calls it, which is why nothing noticed.

    201 only on a true creation, 200 for the claim that was already there — `start_claim`
    is get-or-create now, and a caller that cannot tell the two apart cannot tell a
    duplicate submission from a fresh one.
    """
    stop = loads.get_stop(db, body.stop_id)
    if stop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stop not found")
    load = loads.get_load(db, stop.load_id)
    if load is None or load.account_id != account.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your stop")
    existing = m3.open_claim_for_stop(db, stop.id)
    claim = m3.start_claim(db, stop)
    response.status_code = status.HTTP_200_OK if existing else status.HTTP_201_CREATED
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
    try:
        result = m3.generate_pack(db, claim, now=datetime.now(UTC), gateway=_GATEWAY)
    except m3.ClaimAlreadyFiled as exc:
        raise already_filed(exc) from exc
    return {
        "claim_id": str(claim.id),
        "amount_cents": claim.amount_cents,
        "state": claim.state.value,
        "chain_valid": result["pack"].verification["chain_valid"],
        "receivable_ref": str(claim.receivable_ref) if claim.receivable_ref else None,
    }

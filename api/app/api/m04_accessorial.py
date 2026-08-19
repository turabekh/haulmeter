"""AI-CONTEXT: M4 Accessorial HTTP endpoints — thin over m04_accessorial.public.
TONU / layover / lumper file through the shared M3 invoice rail; /accessorial/owed
is the unified Money-Owed view. F8/F9 provider seams (recording gateway + fake
model) in dev until the real adapters are wired.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_account, get_db, require_module
from app.foundation.f01_identity import public as identity
from app.foundation.f05_load import public as loads
from app.foundation.f08_notifications import public as notify
from app.foundation.f09_ai_gateway import public as ai
from app.modules.m04_accessorial import public as m4

router = APIRouter(prefix="/accessorial", tags=["accessorial"],
    # PRD §6: the module's own flag, gating every route in it (§23 entry 105)
    dependencies=[Depends(require_module("m04_accessorial"))],
)

# AI-CONTEXT: the REAL counterparty transport (§23 entry 122). This was a recording
# gateway — an in-memory list — at every one of the seven send sites, so the F8 rows
# said the notice was sent and nothing ever left the box. Resolves SMTP-or-recording
# at send time, so the suite (SMTP_HOST blanked in conftest) and the app differ by
# configuration alone.
_GATEWAY = notify.counterparty_gateway()
_PROVIDER = ai.resolve_provider()  # F9: real Claude when ANTHROPIC_API_KEY set, else Fake


# AI-CONTEXT: `gt=0` here AND a guard in `_file` — deliberately two layers, not one.
# This one gives a driver a 422 that names the field; the service one covers every caller
# that never crosses a route. Each is tested with the other intact, so neither can rot
# behind the other.
class TonuIn(BaseModel):
    load_id: uuid.UUID
    amount_cents: int = Field(gt=0)


class LayoverIn(BaseModel):
    stop_id: uuid.UUID
    layover_rate_cents: int = Field(gt=0)


class LumperIn(BaseModel):
    load_id: uuid.UUID
    amount_cents: int = Field(gt=0)


def _owned_load(db, load_id, account):
    """AI-CONTEXT: this router had NO ownership check of any kind on any route.

    `_require_load` proved the load existed and stopped there, so any authenticated driver
    could file a TONU or a lumper fee against any load in the database — inventing a
    receivable on someone else's account and sending an invoice to their broker under
    their name. Every other stop- or load-scoped route in the product goes through the
    404-then-403 shape below; this one never did, and no test in this router asserted a
    403 until now.
    """
    load = loads.get_load(db, load_id)
    if load is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "load not found")
    if load.account_id != account.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your load")
    return load


def _already_filed(exc) -> HTTPException:
    """409 carrying the FIRST filing's refs — M3's `already_filed` shape (D3)."""
    claim = exc.claim
    return HTTPException(
        status.HTTP_409_CONFLICT,
        {
            "error": "already_filed",
            "claim_id": str(claim.id),
            "kind": claim.kind.value,
            "amount_cents": claim.amount_cents,
            "receivable_ref": str(claim.receivable_ref) if claim.receivable_ref else None,
        },
    )


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
    load = _owned_load(db, body.load_id, account)
    try:
        return _claim_out(m4.file_tonu(db, load, body.amount_cents, gateway=_GATEWAY))
    except m4.AlreadyFiled as exc:
        raise _already_filed(exc) from exc
    except m4.InvalidAmount as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.post("/layover", status_code=201)
def layover(
    body: LayoverIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    stop = loads.get_stop(db, body.stop_id)
    if stop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stop not found")
    _owned_load(db, stop.load_id, account)  # the stop is only reachable through its load
    try:
        claim = m4.file_layover(db, stop, body.layover_rate_cents, gateway=_GATEWAY)
    except m4.NoLayover as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except m4.AlreadyFiled as exc:
        raise _already_filed(exc) from exc
    except m4.InvalidAmount as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return _claim_out(claim)


@router.post("/lumper", status_code=201)
def lumper(
    body: LumperIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    # lumper is deliberately NOT deduped — see `_external_ref`. Multiple lumper fees per
    # load are legitimate, one per stop, and this route carries no stop to key on.
    load = _owned_load(db, body.load_id, account)
    try:
        claim = m4.file_lumper(
            db, load, _PROVIDER, receipt_bytes=b"", amount_cents=body.amount_cents,
            gateway=_GATEWAY,
        )
    except m4.InvalidAmount as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return _claim_out(claim)


@router.get("/unfiled")
def unfiled(
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Money already earned that no broker has been billed for (§23 entry 226).

    Its own read rather than a field on `/owed`: that route answers "what am I owed",
    and an unfiled claim is owed by nobody yet — no invoice exists and no counterparty
    has been told. Mixing them would put money in a total a driver could take to a
    broker who has never heard of it, which is the defect entry 142 removed.
    """
    return m4.unfiled_claims(db, account.id)


@router.get("/owed")
def owed(
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> list[dict]:
    return m4.money_owed(db, account.id)

"""AI-CONTEXT: M9 Driver Money & Tax Tools HTTP endpoints — thin over
m09_money.public. The earnings/North-Star DDD dashboard, the settlement auditor
(upload -> reconcile against the driver's own GPS-backed receivables -> flagged
discrepancies), and expense capture. Auditor output is "review with your
carrier", never legal advice (PRD §8.9).
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_account, get_db, require_module
from app.foundation.f01_identity import public as identity
from app.foundation.f07_ledger import public as ledger
from app.foundation.f08_notifications import public as notify
from app.modules.m09_money import public as m9

router = APIRouter(prefix="/money", tags=["money"],
    # PRD §6: the module's own flag, gating every route in it (§23 entry 105)
    dependencies=[Depends(require_module("m09_money"))],
)


class SettlementLineIn(BaseModel):
    kind: str
    amount_cents: int


class SettlementIn(BaseModel):
    carrier: str
    period_start: date
    period_end: date
    lines: list[SettlementLineIn]


class ReceiptIn(BaseModel):
    category: str
    amount_cents: int
    occurred_on: date


@router.get("/earnings")
def earnings(
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    s = m9.earnings_dashboard(db, account.id)
    return {
        "recovered_cents": s.recovered_cents,
        "fuel_saved_cents": s.fuel_saved_cents,
        "flagged_cents": s.flagged_cents,
        "ddd_cents": s.ddd_cents,
        # J1 part 4 — the year figure and the two halves it is made of, so the screen can
        # show what it is rather than only how big it is (§11.7)
        "recovered_year_gross_cents": s.recovered_year_gross_cents,
        "fees_year_cents": s.fees_year_cents,
        "recovered_year_net_cents": s.recovered_year_net_cents,
        "year": s.year,
        # what the empty state needs to say something true (§23 entry 215)
        "has_loads": s.has_loads,
        "open_claims": s.open_claims,
        "accrued_unfiled_cents": s.accrued_unfiled_cents,
    }


@router.post("/settlements/audit", status_code=201)
def audit(
    body: SettlementIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    settlement = m9.upload_settlement(
        db,
        account.id,
        body.carrier,
        body.period_start,
        body.period_end,
        lines=[line.model_dump() for line in body.lines],
    )
    discrepancies = m9.audit_settlement(db, settlement)
    return {
        "settlement_id": str(settlement.id),
        "discrepancies": [
            {
                "kind": d.kind,
                "owed_cents": d.owed_cents,
                "paid_cents": d.paid_cents,
                "missed_cents": d.missed_cents,
                "status": d.status.value,
            }
            for d in discrepancies
        ],
        "total_missed_cents": sum(d.missed_cents for d in discrepancies),
    }


@router.post("/receipts", status_code=201)
def add_receipt(
    body: ReceiptIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    r = m9.add_receipt(db, account.id, body.category, body.amount_cents, body.occurred_on)
    return {"receipt_id": str(r.id), "category": r.category, "amount_cents": r.amount_cents}


@router.get("/expenses/{year}")
def expenses(
    year: int,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    s = m9.expense_summary(db, account.id, year)
    return {
        "by_category": s.by_category,
        "total_cents": s.total_cents,
        "receipt_count": s.receipt_count,
        "year": year,
    }


# AI-CONTEXT: the REAL counterparty transport (§23 entry 122). This was a recording
# gateway — an in-memory list — at every one of the seven send sites, so the F8 rows
# said the notice was sent and nothing ever left the box. Resolves SMTP-or-recording
# at send time, so the suite (SMTP_HOST blanked in conftest) and the app differ by
# configuration alone.
_GATEWAY = notify.counterparty_gateway()


@router.post("/receivable/{receivable_id}/paid")
def mark_paid(
    receivable_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    """The driver records that a broker actually paid (§23 entry 108).

    AI-CONTEXT: nothing in this product could mark a receivable recovered before this
    — the state and F7's transition existed with no caller, so `recovered_cents` below
    was structurally zero. Driver-only by owner decision: the money lands in the
    driver's bank, so only they can know it arrived.
    """
    receivable = db.get(ledger.Receivable, receivable_id)
    if receivable is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "receivable not found")
    if receivable.account_id != account.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your receivable")
    try:
        receivable, _ = m9.mark_receivable_paid(db, receivable, account.id, gateway=_GATEWAY)
    except ledger.InvalidTransition as exc:
        # already recovered, or written off — the ledger owns that rule, not this route
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {
        "receivable_id": str(receivable.id),
        "state": receivable.state.value,
        "amount_cents": receivable.amount_cents,
    }


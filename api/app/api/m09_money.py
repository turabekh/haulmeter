"""AI-CONTEXT: M9 Driver Money & Tax Tools HTTP endpoints — thin over
m09_money.public. The earnings/North-Star DDD dashboard, the settlement auditor
(upload -> reconcile against the driver's own GPS-backed receivables -> flagged
discrepancies), and expense capture. Auditor output is "review with your
carrier", never legal advice (PRD §8.9).
"""

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_account, get_db, require_module
from app.foundation.f01_identity import public as identity
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

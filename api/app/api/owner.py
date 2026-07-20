"""AI-CONTEXT: Property-Owner portal endpoints (M6-FR5, the supply side). A
parking-property owner's view of their listings, bookings, and accrued payout
(the F7 owner_payable the platform owes them). Payout SETTLEMENT is the
Stripe/Connect seam (deferred); this shows what's owed on the ledger. Backs the
web-first Property-Owner portal (design-prd §18); requires a session.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_account, get_db
from app.foundation.f01_identity import public as identity
from app.modules.m06_parking import public as m6

router = APIRouter(prefix="/owner", tags=["owner"])


@router.get("/dashboard")
def dashboard(
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    properties = m6.owner_properties(db, account.id)
    return {
        "payout_cents": m6.owner_payable_cents(db, account.id),
        "properties": [
            {
                "id": str(p.id),
                "name": p.name,
                "vetted": p.vetted,
                "spots": [
                    {
                        "label": s.label,
                        "price_cents_per_night": s.price_cents_per_night,
                        "active": s.active,
                    }
                    for s in m6.property_spots(db, p.id)
                ],
            }
            for p in properties
        ],
        "bookings": [
            {
                "id": str(b.id),
                "nights": b.nights,
                "price_cents": b.price_cents,
                "owner_payout_cents": b.owner_payout_cents,
                "state": b.state.value,
            }
            for b in m6.owner_bookings(db, account.id)
        ],
    }

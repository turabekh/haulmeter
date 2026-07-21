"""AI-CONTEXT: Property-Owner portal endpoints (M6-FR5, the supply side). A
parking-property owner's view of their listings, bookings, and accrued payout
(the F7 owner_payable the platform owes them). Payout SETTLEMENT is the
Stripe/Connect seam (deferred); this shows what's owed on the ledger. Backs the
web-first Property-Owner portal (design-prd §18); requires a session.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_account, get_db
from app.foundation.f01_identity import public as identity
from app.modules.m06_parking import public as m6

router = APIRouter(prefix="/owner", tags=["owner"])


class PropertyIn(BaseModel):
    name: str
    lat: float
    lon: float


class SpotIn(BaseModel):
    label: str
    price_cents_per_night: int


class SpotPatch(BaseModel):
    price_cents_per_night: int | None = None
    active: bool | None = None


def _owned_property(db: Session, property_id: uuid.UUID, account: identity.Account):
    prop = m6.get_property(db, property_id)
    if prop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "property not found")
    if prop.owner_account_id != account.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your property")
    return prop


def _owned_spot(db: Session, spot_id: uuid.UUID, account: identity.Account):
    spot = m6.get_spot(db, spot_id)
    if spot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "spot not found")
    _owned_property(db, spot.property_id, account)  # ownership via the parent
    return spot


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


def _spot_json(s) -> dict:
    return {
        "id": str(s.id),
        "label": s.label,
        "price_cents_per_night": s.price_cents_per_night,
        "active": s.active,
    }


@router.post("/property", status_code=201)
def create_property(
    body: PropertyIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    # a new listing starts un-vetted; vetting is a platform/admin step (M6-FR5)
    prop = m6.create_property(db, account.id, body.name, body.lat, body.lon)
    return {"id": str(prop.id), "name": prop.name, "vetted": prop.vetted, "spots": []}


@router.post("/property/{property_id}/spot", status_code=201)
def add_spot(
    property_id: uuid.UUID,
    body: SpotIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    prop = _owned_property(db, property_id, account)
    spot = m6.add_spot(db, prop, body.label, body.price_cents_per_night)
    return _spot_json(spot)


@router.patch("/spot/{spot_id}")
def update_spot(
    spot_id: uuid.UUID,
    body: SpotPatch,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    spot = _owned_spot(db, spot_id, account)
    spot = m6.update_spot(
        db, spot, price_cents_per_night=body.price_cents_per_night, active=body.active
    )
    return _spot_json(spot)

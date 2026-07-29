"""AI-CONTEXT: M7 Fuel HTTP endpoints — thin over m07_fuel.public. The corridor
returns the driver's NET price ranked by true cost; a pump code is issued for
network stations (payment-partner charge is the deferred gateway seam) and
settles on the F7 ledger with spread accounting. Crowd confirmation keeps
non-network prices honest on the same layer.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import canonical_facility_id, current_account, get_db
from app.foundation.f01_identity import public as identity
from app.modules.m07_fuel import public as m7

router = APIRouter(prefix="/fuel", tags=["fuel"])


class PumpCodeIn(BaseModel):
    station_id: uuid.UUID
    gallons: float


class ConfirmPriceIn(BaseModel):
    facility_id: uuid.UUID
    price_cents_per_gal: int


@router.get("/corridor")
def corridor(
    lat: float,
    lon: float,
    heading_deg: float = 0,
    max_distance_m: float = 40000,
    gallons: float = m7.DEFAULT_GALLONS,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [
        {
            "facility_id": str(s.facility_id),
            "name": s.name,
            "distance_m": s.distance_m,
            "gross_cents_per_gal": s.gross_cents_per_gal,
            "net_cents_per_gal": s.net_cents_per_gal,
            "savings_cents_per_gal": s.savings_cents_per_gal,
            "true_cost_cents": s.true_cost_cents,
            "is_network": s.is_network,
        }
        for s in m7.corridor_fuel(db, account.id, lat, lon, heading_deg, max_distance_m, gallons)
    ]


@router.get("/analytics")
def analytics(
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    a = m7.driver_analytics(db, account.id)
    return {
        "gallons_milli": a.gallons_milli,
        "spend_cents": a.spend_cents,
        "savings_cents": a.savings_cents,
        "txn_count": a.txn_count,
    }


@router.post("/pump-code", status_code=201)
def pump_code(
    body: PumpCodeIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    try:
        txn = m7.issue_pump_code(db, account.id, body.station_id, body.gallons)
    except m7.NotAFuelPartner as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "not a fuel-network station") from exc
    return {
        "transaction_id": str(txn.id),
        "pump_code": txn.pump_code,
        "net_cents": txn.net_cents,
        "gallons_milli": txn.gallons_milli,
        "state": txn.state.value,
    }


@router.post("/confirm-price")
def confirm_price(
    body: ConfirmPriceIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    consensus = m7.confirm_price(
        db,
        account.id,
        canonical_facility_id(body.facility_id, db),
        body.price_cents_per_gal,
        datetime.now(UTC),
    )
    return {"consensus_cents_per_gal": consensus}

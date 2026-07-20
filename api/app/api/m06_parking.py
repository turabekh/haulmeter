"""AI-CONTEXT: M6 Parking HTTP endpoints — thin over m06_parking.public. Booking
runs the F7 ledger economics (Stripe charge is the deferred gateway seam). The
closing loop surfaces bookable inventory when nearby public lots are full.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_account, get_db
from app.foundation.f01_identity import public as identity
from app.modules.m06_parking import public as m6

router = APIRouter(prefix="/parking", tags=["parking"])


class BookIn(BaseModel):
    spot_id: uuid.UUID
    start_at: str
    end_at: str


@router.get("/bookable")
def bookable(
    lat: float,
    lon: float,
    radius_m: float = 8000,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [
        {
            "spot_id": str(b.spot_id),
            "property_name": b.property_name,
            "price_cents_per_night": b.price_cents_per_night,
            "lat": b.lat,
            "lon": b.lon,
        }
        for b in m6.bookable_near(db, lat, lon, radius_m)
    ]


@router.get("/closing-loop")
def closing_loop(
    lat: float,
    lon: float,
    radius_m: float = 8000,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    loop = m6.closing_loop(db, account.id, lat, lon, radius_m)
    return {
        "trigger": loop["trigger"],
        "bookable": [
            {
                "spot_id": str(b.spot_id),
                "property_name": b.property_name,
                "price_cents_per_night": b.price_cents_per_night,
            }
            for b in loop["bookable"]
        ],
    }


@router.post("/book", status_code=201)
def book(
    body: BookIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    spot = db.get(m6.ParkingSpot, body.spot_id)
    if spot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "spot not found")
    try:
        booking = m6.book(
            db,
            spot,
            account.id,
            datetime.fromisoformat(body.start_at),
            datetime.fromisoformat(body.end_at),
        )
    except m6.SpotUnavailable as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "spot unavailable") from exc
    return {
        "booking_id": str(booking.id),
        "nights": booking.nights,
        "price_cents": booking.price_cents,
        "state": booking.state.value,
    }

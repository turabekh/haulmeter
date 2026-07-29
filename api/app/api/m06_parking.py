"""AI-CONTEXT: M6 Parking HTTP endpoints — thin over m06_parking.public. Booking
runs the F7 ledger economics (Stripe charge is the deferred gateway seam). The
closing loop surfaces bookable inventory when nearby public lots are full.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_account, get_db, require_module
from app.foundation.f01_identity import public as identity
from app.foundation.f08_notifications import public as notify
from app.modules.m06_parking import public as m6

_GATEWAY = notify.RecordingNotificationGateway()  # F8 seam (dev)

router = APIRouter(prefix="/parking", tags=["parking"],
    # PRD §6: the module's own flag, gating every route in it (§23 entry 105)
    dependencies=[Depends(require_module("m06_parking"))],
)


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


@router.get("/bookings")
def my_bookings(
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    """The driver's own bookings — the read that had never existed (§23 entry 110)."""
    return {"bookings": m6.driver_bookings(db, account.id)}


@router.post("/booking/{booking_id}/cancel")
def cancel_booking(
    booking_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    """M6-FR7, which had been written and left unreachable (§23 entry 108).

    AI-CONTEXT: the whole cancellation/refund engine existed in the domain with no
    endpoint calling it — a booking could be made and never unmade. Either side may
    cancel: the driver who holds it, or the owner of the property it sits on. Which of
    them acted is what decides whether the driver is notified, so it is passed down
    rather than inferred.
    """
    booking = db.get(m6.Booking, booking_id)
    if booking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "booking not found")
    spot = db.get(m6.ParkingSpot, booking.spot_id)
    prop = db.get(m6.ParkingProperty, spot.property_id)
    if account.id not in (booking.driver_account_id, prop.owner_account_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your booking")
    if booking.state in (m6.BookingState.canceled, m6.BookingState.refunded):
        raise HTTPException(status.HTTP_409_CONFLICT, "booking already canceled")
    booking = m6.cancel(
        db,
        booking,
        datetime.now(UTC),
        actor_account_id=account.id,
        gateway=_GATEWAY,
    )
    return {
        "booking_id": str(booking.id),
        "state": booking.state.value,
        "refunded": booking.refund_entry_ref is not None,
    }


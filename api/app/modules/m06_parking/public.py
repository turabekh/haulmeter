"""AI-CONTEXT: Public interface for M6 Parking Marketplace.

The ONLY import surface other packages may use to reach M6 (import-linter
enforced). Listings, instant booking (F7 ledger economics; Stripe seam),
geofence check-in/out, refund engine, and the closing loop (imports m01). Runs
behind the F13 flag m06_parking (refund-policy + damage/liability gates).
"""

from .domain.enums import BookingState
from .domain.models import Booking, ParkingProperty, ParkingSpot
from .domain.service import (
    DEFAULT_TAKE_RATE_BPS,
    FLAG_KEY,
    GATES,
    MODULE,
    BookableSpot,
    SpotUnavailable,
    add_spot,
    book,
    bookable_near,
    cancel,
    check_in,
    check_out,
    closing_loop,
    create_property,
    is_overstay,
    owner_bookings,
    owner_payable_cents,
    owner_properties,
    property_spots,
    register_module,
)

__all__ = [
    "BookingState",
    "Booking",
    "ParkingProperty",
    "ParkingSpot",
    "DEFAULT_TAKE_RATE_BPS",
    "FLAG_KEY",
    "GATES",
    "MODULE",
    "BookableSpot",
    "SpotUnavailable",
    "add_spot",
    "book",
    "bookable_near",
    "cancel",
    "check_in",
    "check_out",
    "closing_loop",
    "create_property",
    "is_overstay",
    "owner_bookings",
    "owner_payable_cents",
    "owner_properties",
    "property_spots",
    "register_module",
]

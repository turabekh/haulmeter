"""AI-CONTEXT: M6 Parking Marketplace (PRD §8.6) — the transaction layer.
Instantly bookable private truck parking fused into the same map. The booking
economics run on the F7 double-entry ledger (driver payment -> owner payout +
platform take, always balanced); the actual card charge / Connect payout is the
F7 PaymentGateway SEAM (Stripe deferred, wired at activation). The take rate is
baked into the owner side so the driver sees one transparent price — no checkout
surprises (design-prd §21.8). Composes foundation publics + m01.public (the
closing loop). Runs behind the F13 flag m06_parking, gated on refund-policy +
damage/liability posture.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.foundation.f02_facility import public as facility_registry
from app.foundation.f03_location import public as location
from app.foundation.f07_ledger import public as ledger
from app.modules.m01_map import public as m1

from .enums import BookingState
from .models import Booking, ParkingProperty, ParkingSpot

FLAG_KEY = "m06_parking"
MODULE = "m06"
DEFAULT_TAKE_RATE_BPS = 1750  # 17.5% all-in (design-prd §9 / PRD §9) -> F13 config
CONFIG_TAKE_RATE_KEY = "m06_take_rate_bps"  # F13 pricing scope; editable in F14 admin
FULL_REFUND_HOURS = 24
GATES = ["refund_policy", "damage_liability_posture"]

_ACTIVE_STATES = {BookingState.booked, BookingState.checked_in, BookingState.checked_out}


class SpotUnavailable(Exception):
    pass


@dataclass
class BookableSpot:
    spot_id: object
    property_name: str
    price_cents_per_night: int
    lat: float
    lon: float


def register_module(db: Session) -> None:
    from app.foundation.f13_flags import public as flags
    from app.foundation.f14_admin import public as admin

    flags.register_flag(db, FLAG_KEY, description="M6 Parking Marketplace")
    for gate in GATES:
        flags.add_gate(db, FLAG_KEY, gate)
    admin.register_admin_view(
        db, "m06.bookings", MODULE, "Bookings & Payouts", "/admin/m06/bookings"
    )


# --- Listings (M6-FR1) ---
def create_property(
    db: Session, owner_account_id, name: str, lat: float, lon: float, vetted=False
) -> ParkingProperty:
    fac = facility_registry.create_facility(
        db, facility_registry.FacilityType.parking_property, name, lat, lon
    )
    prop = ParkingProperty(
        owner_account_id=owner_account_id, name=name, facility_ref=fac.id, vetted=vetted
    )
    db.add(prop)
    db.flush()
    return prop


def add_spot(
    db: Session, prop: ParkingProperty, label: str, price_cents_per_night: int
) -> ParkingSpot:
    spot = ParkingSpot(
        property_id=prop.id, label=label, price_cents_per_night=price_cents_per_night
    )
    db.add(spot)
    db.flush()
    return spot


# --- Instant booking (M6-FR2) ---
def _overlaps(db: Session, spot_id, start_at, end_at) -> bool:
    for booking in db.scalars(select(Booking).where(Booking.spot_id == spot_id)):
        if booking.state not in _ACTIVE_STATES:
            continue
        if booking.start_at < end_at and start_at < booking.end_at:
            return True
    return False


def _ledger_accounts(db: Session, owner_account_id):
    cash = ledger.get_or_create_account(
        db, ledger.LedgerAccountKind.cash_clearing, "cash:parking", ledger.Currency.usd
    )
    owner = ledger.get_or_create_account(
        db,
        ledger.LedgerAccountKind.owner_payable,
        f"owner:{owner_account_id}",
        ledger.Currency.usd,
        owner_ref=owner_account_id,
    )
    platform = ledger.get_or_create_account(
        db, ledger.LedgerAccountKind.platform_revenue, "revenue:parking", ledger.Currency.usd
    )
    return cash, owner, platform


def _configured_take_rate(db: Session) -> int:
    # the live take rate: F13 config (edited in the F14 admin console) falling back
    # to the compiled default — the activation knob the config editor opens (§21.8)
    from app.foundation.f13_flags import public as flags

    return int(flags.get_config(db, CONFIG_TAKE_RATE_KEY, DEFAULT_TAKE_RATE_BPS))


def book(
    db: Session,
    spot: ParkingSpot,
    driver_account_id,
    start_at: datetime,
    end_at: datetime,
    take_rate_bps: int | None = None,
    gateway=None,
) -> Booking:
    if _overlaps(db, spot.id, start_at, end_at):
        raise SpotUnavailable(str(spot.id))
    if take_rate_bps is None:  # unset -> the live F13-config rate (default fallback)
        take_rate_bps = _configured_take_rate(db)
    nights = max(1, (end_at.date() - start_at.date()).days)
    price = nights * spot.price_cents_per_night
    take = round(price * take_rate_bps / 10000)
    owner_payout = price - take

    prop = db.get(ParkingProperty, spot.property_id)
    if gateway is not None:  # Stripe seam (deferred); ledger is the source of truth
        gateway.create_payment_intent(price, f"booking:{spot.id}")
    cash, owner_acct, platform = _ledger_accounts(db, prop.owner_account_id)
    entry = ledger.post_entry(
        db,
        ledger.EntryType.booking_payment,
        [
            ledger.Posting(cash.id, ledger.Direction.debit, price),
            ledger.Posting(owner_acct.id, ledger.Direction.credit, owner_payout),
            ledger.Posting(platform.id, ledger.Direction.credit, take),
        ],
    )
    booking = Booking(
        spot_id=spot.id,
        driver_account_id=driver_account_id,
        start_at=start_at,
        end_at=end_at,
        nights=nights,
        price_cents=price,
        take_cents=take,
        owner_payout_cents=owner_payout,
        state=BookingState.booked,
        entry_ref=entry.id,
    )
    db.add(booking)
    db.flush()
    return booking


# --- Check-in / out via geofence (M6-FR4) ---
def _property_facility(db: Session, booking: Booking):
    spot = db.get(ParkingSpot, booking.spot_id)
    prop = db.get(ParkingProperty, spot.property_id)
    return prop.facility_ref


def check_in(
    db: Session, booking: Booking, now: datetime, require_presence: bool = True
) -> Booking:
    if require_presence and not location.is_present(
        db, booking.driver_account_id, _property_facility(db, booking)
    ):
        raise SpotUnavailable("driver not present at the property")
    booking.state = BookingState.checked_in
    booking.checked_in_at = now
    db.flush()
    return booking


def check_out(db: Session, booking: Booking, now: datetime) -> Booking:
    booking.state = BookingState.checked_out
    booking.checked_out_at = now
    db.flush()
    return booking


def is_overstay(booking: Booking, now: datetime) -> bool:
    return (
        booking.checked_out_at is None
        and booking.state == BookingState.checked_in
        and now > booking.end_at
    )


# --- Cancellation / refund engine (M6-FR7) ---
def cancel(db: Session, booking: Booking, now: datetime) -> Booking:
    fraction = 1.0 if (booking.start_at - now) >= timedelta(hours=FULL_REFUND_HOURS) else 0.5
    refund_total = round(booking.price_cents * fraction)
    if refund_total > 0:
        refund_take = round(booking.take_cents * fraction)
        refund_owner = refund_total - refund_take
        prop = db.get(ParkingProperty, db.get(ParkingSpot, booking.spot_id).property_id)
        cash, owner_acct, platform = _ledger_accounts(db, prop.owner_account_id)
        entry = ledger.post_entry(
            db,
            ledger.EntryType.adjustment,
            [
                ledger.Posting(owner_acct.id, ledger.Direction.debit, refund_owner),
                ledger.Posting(platform.id, ledger.Direction.debit, refund_take),
                ledger.Posting(cash.id, ledger.Direction.credit, refund_total),
            ],
            description=f"refund for booking {booking.id}",
        )
        booking.refund_entry_ref = entry.id
        booking.state = BookingState.refunded
    else:
        booking.state = BookingState.canceled
    db.flush()
    return booking


# --- Property-owner views (M6-FR5, the supply side) ---
def owner_properties(db: Session, owner_account_id) -> list[ParkingProperty]:
    return list(
        db.scalars(
            select(ParkingProperty).where(ParkingProperty.owner_account_id == owner_account_id)
        )
    )


def property_spots(db: Session, property_id) -> list[ParkingSpot]:
    return list(db.scalars(select(ParkingSpot).where(ParkingSpot.property_id == property_id)))


def owner_bookings(db: Session, owner_account_id) -> list[Booking]:
    prop_ids = [p.id for p in owner_properties(db, owner_account_id)]
    if not prop_ids:
        return []
    spot_ids = [
        s.id for s in db.scalars(select(ParkingSpot).where(ParkingSpot.property_id.in_(prop_ids)))
    ]
    if not spot_ids:
        return []
    return list(
        db.scalars(
            select(Booking).where(Booking.spot_id.in_(spot_ids)).order_by(Booking.created_at.desc())
        )
    )


def owner_payable_cents(db: Session, owner_account_id) -> int:
    # what the platform owes this owner (F7 owner_payable is credited on booking;
    # a credit balance is negative, so owed-to-owner is its negation)
    account = ledger.get_or_create_account(
        db,
        ledger.LedgerAccountKind.owner_payable,
        f"owner:{owner_account_id}",
        ledger.Currency.usd,
        owner_ref=owner_account_id,
    )
    return -int(ledger.balance(db, account))


# --- Bookable inventory + the closing loop (M6-FR3) ---
def bookable_near(db: Session, lat: float, lon: float, radius_m: float) -> list[BookableSpot]:
    facilities = facility_registry.nearest(
        db, lat, lon, radius_m, facility_type=facility_registry.FacilityType.parking_property
    )
    fac_ids = [f.id for f in facilities]
    if not fac_ids:
        return []
    props = {
        p.facility_ref: p
        for p in db.scalars(
            select(ParkingProperty).where(ParkingProperty.facility_ref.in_(fac_ids))
        )
    }
    out: list[BookableSpot] = []
    for fac in facilities:
        prop = props.get(fac.id)
        if prop is None:
            continue
        flat, flon = facility_registry.coordinates(db, fac)
        for spot in db.scalars(
            select(ParkingSpot).where(
                ParkingSpot.property_id == prop.id, ParkingSpot.active.is_(True)
            )
        ):
            out.append(BookableSpot(spot.id, prop.name, spot.price_cents_per_night, flat, flon))
    return out


def closing_loop(db: Session, account_id, lat: float, lon: float, radius_m: float) -> dict:
    # PRD M6-FR3: when M1 shows public lots Full nearby, surface bookable inventory
    pins = m1.map_overlay(db, account_id, lat, lon, radius_m, preset=m1.Preset.tonight)
    public_full = any(p.status == "full" for p in pins)
    return {"trigger": public_full, "bookable": bookable_near(db, lat, lon, radius_m)}

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
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.foundation.f02_facility import public as facility_registry
from app.foundation.f03_location import public as location
from app.foundation.f07_ledger import public as ledger
from app.foundation.f08_notifications import public as notify
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


def get_property(db: Session, property_id) -> ParkingProperty | None:
    return db.get(ParkingProperty, property_id)


def bookable_summary(db: Session, facility_ref, at: datetime | None = None) -> dict | None:
    # the cheapest AVAILABLE spot for tonight (no active booking overlapping the
    # next 24h) — backs the map's "Book" badge. Returns None when the property is
    # fully booked, so a booked lot drops its Book affordance on the map.
    at = at or datetime.now(UTC)
    window_end = at + timedelta(days=1)
    prop = db.scalar(select(ParkingProperty).where(ParkingProperty.facility_ref == facility_ref))
    if prop is None:
        return None
    available = [
        s
        for s in property_spots(db, prop.id)
        if s.active and not _overlaps(db, s.id, at, window_end)
    ]
    if not available:
        return None
    cheapest = min(available, key=lambda s: s.price_cents_per_night)
    return {"spot_id": str(cheapest.id), "price_cents_per_night": cheapest.price_cents_per_night}


def get_spot(db: Session, spot_id) -> ParkingSpot | None:
    return db.get(ParkingSpot, spot_id)


def update_spot(
    db: Session,
    spot: ParkingSpot,
    price_cents_per_night: int | None = None,
    active: bool | None = None,
) -> ParkingSpot:
    # owner self-serve edits (M6-FR1): re-price or pause/resume a listing. A paused
    # spot drops out of bookable_near (it filters active) but keeps its history.
    if price_cents_per_night is not None:
        spot.price_cents_per_night = price_cents_per_night
    if active is not None:
        spot.active = active
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
#
# AI-CONTEXT: §13.2 names "booking failed" as a P0 and there was no such event to
# report. `book()` has exactly one failure — `SpotUnavailable` on a double-book —
# raised inside the driver's own request, which §12.4 answers with error copy on the
# screen they are already looking at. Pushing a P0 about it would tell someone what
# they are reading. The Stripe seam that could fail asynchronously is deferred.
#
# The real money event a driver is NOT looking at is this one, and it had been written
# and left unreachable: the whole refund engine below had no endpoint calling it.
# A spot the driver reserved being taken away is money moving without them.
#
# THE RULE, shared with M9's "claim paid" (§23 entry 108): a P0 announces money that
# moved WITHOUT you. A driver who cancels their own booking is told nothing, because
# they already know; the property owner cancelling theirs is exactly what a P0 is for.
BOOKING_CANCELED_CATEGORY = "booking_canceled"
# §13.5: the screen that describes a canceled booking. It pointed at /book/<spot> — the
# CHECKOUT flow — until entry 110 gave the driver somewhere to see their bookings at all.
BOOKINGS_DEEP_LINK = "/bookings"


def cancel(
    db: Session,
    booking: Booking,
    now: datetime,
    actor_account_id=None,
    gateway=None,
) -> Booking:
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
    _notify_driver_of_cancellation(db, booking, refund_total, actor_account_id, gateway, now)
    return booking


def _notify_driver_of_cancellation(db, booking, refund_cents, actor_account_id, gateway, now):
    if gateway is None or actor_account_id == booking.driver_account_id:
        return None
    spot = db.get(ParkingSpot, booking.spot_id)
    prop = db.get(ParkingProperty, spot.property_id)
    # §12.2/§12.6: lead with the figure when there is one. A cancellation inside the
    # free window refunds in full; one after it refunds half; a $0 refund is not a
    # figure worth leading with and the title says only what happened.
    #
    # The $0 branch is unreachable through `book()` today and is deliberately kept:
    # F7 rejects a posting of zero, so a spot cheap enough to round its half-refund
    # down to nothing cannot be booked in the first place. It costs one line and
    # stops a future free or promotional spot printing "· $0 refunded".
    if refund_cents > 0:
        amount = refund_cents / 100
        figure = f"${amount:,.0f}" if refund_cents % 100 == 0 else f"${amount:,.2f}"
        title = f"Booking canceled · {figure} refunded"
    else:
        title = "Booking canceled"
    return notify.dispatch(
        db,
        booking.driver_account_id,
        notify.NotificationTier.P0,
        BOOKING_CANCELED_CATEGORY,
        title,
        f"{prop.name} canceled your spot. Book another nearby.",
        BOOKINGS_DEEP_LINK,
        gateway,
        now=now,
        subject_ref=str(booking.id),
    )


# --- Property-owner views (M6-FR5, the supply side) ---
def driver_bookings(db: Session, driver_account_id) -> list[dict]:
    """A driver's own bookings, newest first (§23 entry 110).

    AI-CONTEXT: `owner_bookings` has existed since M6 shipped and this had not, so the
    supply side could see every booking and the driver could see none of their own.
    A booking was write-only from the person who paid for it.

    Returns the property NAME and spot label, not just ids: a list of reservations that
    cannot say WHERE is not a list a driver can act on, and resolving it per row in the
    client would be one request per booking against an endpoint built to avoid exactly
    that (§23 entry 98).
    """
    rows = db.scalars(
        select(Booking)
        .where(Booking.driver_account_id == driver_account_id)
        .order_by(Booking.start_at.desc())
    ).all()
    if not rows:
        return []
    spots = {
        s.id: s
        for s in db.scalars(
            select(ParkingSpot).where(ParkingSpot.id.in_({b.spot_id for b in rows}))
        )
    }
    props = {
        p.id: p
        for p in db.scalars(
            select(ParkingProperty).where(
                ParkingProperty.id.in_({s.property_id for s in spots.values()})
            )
        )
    }
    out = []
    for b in rows:
        spot = spots.get(b.spot_id)
        prop = props.get(spot.property_id) if spot is not None else None
        out.append(
            {
                "id": str(b.id),
                "property_name": prop.name if prop is not None else "",
                "spot_label": spot.label if spot is not None else "",
                "spot_id": str(b.spot_id),
                "nights": b.nights,
                "start_at": b.start_at.isoformat(),
                "end_at": b.end_at.isoformat(),
                "price_cents": b.price_cents,
                "state": b.state.value,
                "refunded": b.refund_entry_ref is not None,
            }
        )
    return out


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

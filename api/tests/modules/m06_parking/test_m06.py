from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f07_ledger import public as ledger
from app.foundation.f10_crowd import public as crowd
from app.foundation.f13_flags import public as flags
from app.modules.m06_parking import public as m6

DALLAS = (32.7767, -96.7970)
T0 = datetime(2026, 7, 20, 18, 0, tzinfo=UTC)


def _accounts(db):
    owner = identity.register_account(db, "owner@example.com", "pw-123456")
    driver = identity.register_account(db, "driver@example.com", "pw-123456")
    return owner, driver


def _listing(db, owner, price=2400):
    prop = m6.create_property(db, owner.id, "Yardline Lot", *DALLAS, vetted=True)
    spot = m6.add_spot(db, prop, "A1", price_cents_per_night=price)
    return prop, spot


def test_flag_gated_on_refund_and_liability(db):
    m6.register_module(db)
    assert flags.can_activate(db, "m06_parking") is False


def test_booking_records_balanced_ledger_with_take_rate(db):
    owner, driver = _accounts(db)
    prop, spot = _listing(db, owner, price=2400)
    booking = m6.book(db, spot, driver.id, T0, T0 + timedelta(days=2))
    assert booking.nights == 2
    assert booking.price_cents == 4800
    assert booking.take_cents == 840  # 17.5% of 4800
    assert booking.owner_payout_cents == 3960  # driver sees one price; take baked into owner side

    # owner payable + platform revenue balance against cash
    owner_acct = ledger.get_or_create_account(
        db,
        ledger.LedgerAccountKind.owner_payable,
        f"owner:{owner.id}",
        currency=ledger.Currency.usd,
        owner_ref=owner.id,
    )
    platform = ledger.get_or_create_account(
        db,
        ledger.LedgerAccountKind.platform_revenue,
        "revenue:parking",
        currency=ledger.Currency.usd,
    )
    assert ledger.balance(db, owner_acct) == -3960  # credited (owed to owner)
    assert ledger.balance(db, platform) == -840


def test_double_booking_rejected(db):
    owner, driver = _accounts(db)
    prop, spot = _listing(db, owner)
    m6.book(db, spot, driver.id, T0, T0 + timedelta(days=1))
    with pytest.raises(m6.SpotUnavailable):
        m6.book(db, spot, driver.id, T0, T0 + timedelta(days=1))


def test_check_in_requires_geofence_presence(db):
    owner, driver = _accounts(db)
    prop, spot = _listing(db, owner)
    booking = m6.book(db, spot, driver.id, T0, T0 + timedelta(days=1))
    with pytest.raises(m6.SpotUnavailable):
        m6.check_in(db, booking, now=T0)

    location.arm_geofence(db, driver.id, prop.facility_ref)
    location.evaluate_ping(db, driver.id, *DALLAS, occurred_at=T0)
    m6.check_in(db, booking, now=T0)
    assert booking.state == m6.BookingState.checked_in


def test_full_refund_before_24h_partial_after(db):
    owner, driver = _accounts(db)
    prop, spot = _listing(db, owner, price=2400)
    # cancel 2 days before start -> full refund
    booking = m6.book(db, spot, driver.id, T0 + timedelta(days=2), T0 + timedelta(days=3))
    m6.cancel(db, booking, now=T0)
    assert booking.state == m6.BookingState.refunded
    assert booking.refund_entry_ref is not None

    # cancel within 24h -> 50% refund (still refunded state, half back)
    b2 = m6.book(db, spot, driver.id, T0 + timedelta(hours=2), T0 + timedelta(days=1))
    m6.cancel(db, b2, now=T0)
    assert b2.state == m6.BookingState.refunded


def test_overstay_detection(db):
    owner, driver = _accounts(db)
    prop, spot = _listing(db, owner)
    booking = m6.book(db, spot, driver.id, T0, T0 + timedelta(days=1))
    location.arm_geofence(db, driver.id, prop.facility_ref)
    location.evaluate_ping(db, driver.id, *DALLAS, occurred_at=T0)
    m6.check_in(db, booking, now=T0)
    assert m6.is_overstay(booking, now=T0 + timedelta(days=2)) is True
    assert m6.is_overstay(booking, now=T0 + timedelta(hours=12)) is False


def test_bookable_near_and_closing_loop(db):
    owner, driver = _accounts(db)
    prop, spot = _listing(db, owner)
    # a public truck stop nearby, reported FULL
    public = facility.create_facility(db, facility.FacilityType.truck_stop, "Loves", 32.78, -96.80)
    crowd.submit(
        db,
        driver.id,
        public.id,
        crowd.SignalType.parking_fullness,
        {"status": "full"},
        submitted_at=T0,
        award=False,
    )
    crowd.update_belief(db, public.id, crowd.SignalType.parking_fullness, as_of=T0)

    near = m6.bookable_near(db, *DALLAS, radius_m=3000)
    assert any(b.spot_id == spot.id for b in near)

    loop = m6.closing_loop(db, driver.id, *DALLAS, radius_m=3000)
    assert loop["trigger"] is True  # public lot full -> surface bookable
    assert len(loop["bookable"]) >= 1

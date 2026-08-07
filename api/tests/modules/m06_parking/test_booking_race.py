"""F-13 — the double-booking race, and it posted money twice.

`_overlaps` is a Python read of committed rows, so two concurrent requests for the same
spot and window both passed it and both inserted — each posting its own BALANCED journal
entry, crediting the owner twice for one night. Every invariant in the ledger held.

The tests that matter here deliberately defeat `_overlaps`, because a test that only
exercises the pre-check proves nothing about the race the pre-check cannot see.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.foundation.f01_identity import public as identity
from app.foundation.f07_ledger import public as ledger
from app.modules.m06_parking import public as m6
from app.modules.m06_parking.domain import service as m6_service
from app.modules.m06_parking.domain.enums import BookingState
from app.modules.m06_parking.domain.models import Booking

DALLAS = (32.7767, -96.7970)
T0 = datetime(2026, 7, 20, 18, 0, tzinfo=UTC)


def _listing(db):
    owner = identity.register_account(db, "owner@example.com", "pw-123456")
    driver = identity.register_account(db, "driver@example.com", "pw-123456")
    prop = m6.create_property(db, owner.id, "Yardline Lot", *DALLAS, vetted=True)
    spot = m6.add_spot(db, prop, "A1", price_cents_per_night=2400)
    return owner, driver, spot


def _raw_booking(spot, driver, start, end, state=BookingState.booked):
    return Booking(
        spot_id=spot.id,
        driver_account_id=driver.id,
        start_at=start,
        end_at=end,
        nights=1,
        price_cents=2400,
        take_cents=420,
        owner_payout_cents=1980,
        state=state,
    )


def test_the_database_refuses_an_overlapping_booking_with_no_application_help(db):
    _, driver, spot = _listing(db)
    db.add(_raw_booking(spot, driver, T0, T0 + timedelta(days=2)))
    db.flush()
    db.add(_raw_booking(spot, driver, T0 + timedelta(days=1), T0 + timedelta(days=3)))
    with pytest.raises(IntegrityError):
        db.flush()


def test_book_still_raises_spot_unavailable_when_the_precheck_cannot_see_the_clash(
    db, monkeypatch
):
    # this is the race, made deterministic: _overlaps returns False exactly as it would
    # for a row a concurrent transaction has not committed yet. The API contract must be
    # unchanged — callers catch SpotUnavailable, not IntegrityError.
    _, driver, spot = _listing(db)
    m6.book(db, spot, driver.id, T0, T0 + timedelta(days=2))
    monkeypatch.setattr(m6_service, "_overlaps", lambda *a, **k: False)
    with pytest.raises(m6.SpotUnavailable):
        m6.book(db, spot, driver.id, T0 + timedelta(days=1), T0 + timedelta(days=3))


def test_the_loser_of_the_race_moves_no_money(db, monkeypatch):
    # the reason the reorder matters. Posting the entry before claiming the row meant the
    # losing request had already credited the owner by the time it discovered it had lost.
    owner, driver, spot = _listing(db)
    m6.book(db, spot, driver.id, T0, T0 + timedelta(days=2))
    owner_acct = ledger.get_or_create_account(
        db,
        ledger.LedgerAccountKind.owner_payable,
        f"owner:{owner.id}",
        currency=ledger.Currency.usd,
        owner_ref=owner.id,
    )
    credited_once = ledger.balance(db, owner_acct)

    monkeypatch.setattr(m6_service, "_overlaps", lambda *a, **k: False)
    with pytest.raises(m6.SpotUnavailable):
        m6.book(db, spot, driver.id, T0 + timedelta(days=1), T0 + timedelta(days=3))

    assert ledger.balance(db, owner_acct) == credited_once


def test_a_canceled_booking_frees_the_window(db):
    # the constraint's WHERE clause: canceled and refunded bookings are not live claims
    _, driver, spot = _listing(db)
    booking = m6.book(db, spot, driver.id, T0, T0 + timedelta(days=2))
    m6.cancel(db, booking, now=T0 - timedelta(hours=48))
    again = m6.book(db, spot, driver.id, T0, T0 + timedelta(days=2))
    assert again.id != booking.id


def test_adjacent_windows_are_not_an_overlap(db):
    # tstzrange is half-open, so a checkout at T and a check-in at T do not collide
    _, driver, spot = _listing(db)
    m6.book(db, spot, driver.id, T0, T0 + timedelta(days=2))
    nxt = m6.book(db, spot, driver.id, T0 + timedelta(days=2), T0 + timedelta(days=4))
    assert nxt.id is not None


def test_the_booking_entry_carries_a_ref_the_ledger_can_deduplicate(db):
    # F-13 noted post_entry was called here with NO external_ref at all, so F-05's
    # constraint could not have caught the double credit even once it existed
    _, driver, spot = _listing(db)
    booking = m6.book(db, spot, driver.id, T0, T0 + timedelta(days=2))
    entry = db.get(ledger.JournalEntry, booking.entry_ref)
    assert entry.external_ref == f"booking:{booking.id}"

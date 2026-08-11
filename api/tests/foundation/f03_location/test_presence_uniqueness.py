"""F3-2 — one active presence per (account, facility), refused by Postgres itself.

Deliberately below the service layer. The ENTER branch's own guard is a read, and a read
cannot see a row a concurrent transaction has not committed — which is the entire defect.
A test that only exercises that guard would prove nothing about the race it is there for.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location.domain.models import GeofencePresence

DALLAS = (32.7767, -96.7970)
T0 = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)


def _account_and_dock(db, email="oo@example.com"):
    account = identity.register_account(db, email, "pw-123456")
    dock = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Dock", *DALLAS)
    return account, dock


def _presence(account, dock, active=True, entered_at=T0):
    return GeofencePresence(
        account_id=account.id,
        facility_id=dock.id,
        entered_at=entered_at,
        last_tick_at=entered_at,
        active=active,
    )


def test_the_database_refuses_a_second_active_presence(db):
    account, dock = _account_and_dock(db)
    db.add(_presence(account, dock))
    db.flush()

    db.add(_presence(account, dock))
    with pytest.raises(IntegrityError):
        db.flush()


def test_a_closed_visit_does_not_block_the_next_one(db):
    """The predicate is `WHERE active` — a dock is visited many times, legitimately."""
    account, dock = _account_and_dock(db)
    db.add(_presence(account, dock, active=False))
    db.add(_presence(account, dock, active=False))
    db.flush()

    db.add(_presence(account, dock, active=True))
    db.flush()  # allowed alongside any number of closed ones

    assert db.query(GeofencePresence).filter_by(account_id=account.id).count() == 3


def test_two_drivers_at_one_dock_are_not_each_others_problem(db):
    account, dock = _account_and_dock(db)
    other, _ = _account_and_dock(db, email="other@example.com")
    db.add(_presence(account, dock))
    db.add(_presence(other, dock))

    db.flush()  # the key is (account, facility), not the facility alone


def test_the_streak_column_starts_at_zero(db):
    """The exit debounce's counter. Defaulted so an existing row needs no backfill."""
    account, dock = _account_and_dock(db)
    presence = _presence(account, dock)
    db.add(presence)
    db.flush()

    assert presence.outside_streak == 0

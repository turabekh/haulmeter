"""AI-CONTEXT: a driver who said "I am here" is not overruled by an impossible fix.

Reproduces the owner's report of 2026-08-19 (§23 entry 227), measured on production
first: a stop attested at 07:56 was closed 76 seconds later by a device fix ~17,000 km
from the dock — because the driver is in Perth and the dock is in America. The geofence
was correct about its own data; the product was wrong to prefer it to the person.
"""

from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location

DALLAS = (32.7767, -96.7970)
PERTH = (-31.9, 115.9)  # Perth, deliberately coarse: a public repo needs the
#                          continent, not a person's street
NEAR_DALLAS = (32.7900, -96.8000)  # ~1.5 km away — a real departure
T0 = datetime(2026, 8, 19, 7, 56, tzinfo=UTC)


def _ping(db, account, lat, lon, at):
    """`now` is passed explicitly: F3 refuses pings FROM THE FUTURE, and a fixture that
    reaches past the wall clock is refused for that reason rather than the one under
    test — which is how the first draft of this file 'proved' a departure never closes."""
    return location.evaluate_ping(db, account.id, lat, lon, occurred_at=at, now=at)


def _armed(db, email):
    account = identity.register_account(db, email, "pw-12345")
    dock = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Dock", *DALLAS)
    location.arm_geofence(db, account.id, dock.id)
    return account, dock


def test_a_fix_on_the_other_side_of_the_world_does_not_end_an_attested_stop(db):
    """The reported case, to the second: attested at 07:56, contradicted at 07:57:16."""
    account, dock = _armed(db, "attested-perth@example.com")
    location.assert_presence(db, account.id, dock.id, T0, *PERTH)

    _ping(db, account, *PERTH, at=T0 + timedelta(seconds=76))

    arrival, departure = location.visit_window(db, account.id, dock.id, T0)
    assert arrival is not None, "the attested visit must still be open"
    assert departure is None, "an impossible fix closed a stop the driver was standing on"


def test_a_real_departure_still_ends_an_attested_stop(db):
    """The rule must not trap a driver in a visit they genuinely left."""
    account, dock = _armed(db, "attested-real@example.com")
    location.assert_presence(db, account.id, dock.id, T0, *DALLAS)

    # 1.5 km in an hour is a truck pulling off a dock, not a teleport
    _ping(db, account, *NEAR_DALLAS, at=T0 + timedelta(hours=1))

    _arrival, departure = location.visit_window(db, account.id, dock.id, T0)
    assert departure is not None, "a plausible exit must still close the visit"


def test_an_unattested_visit_is_untouched(db):
    """The geofence opened it, so the geofence closes it — exactly as before."""
    account, dock = _armed(db, "attested-none@example.com")
    _ping(db, account, *DALLAS, at=T0)  # ENTER by sensor

    _ping(db, account, *PERTH, at=T0 + timedelta(seconds=76))

    _arrival, departure = location.visit_window(db, account.id, dock.id, T0)
    assert departure is not None, "an unattested visit keeps the old behaviour"


def test_the_visit_closes_once_enough_time_has_passed_to_have_travelled(db):
    """Not a permanent trap: the same distance is plausible given enough hours."""
    account, dock = _armed(db, "attested-later@example.com")
    location.assert_presence(db, account.id, dock.id, T0, *PERTH)

    # 17,000 km is impossible in 76 seconds and unremarkable in a fortnight
    _ping(db, account, *PERTH, at=T0 + timedelta(days=14))

    _arrival, departure = location.visit_window(db, account.id, dock.id, T0)
    assert departure is not None

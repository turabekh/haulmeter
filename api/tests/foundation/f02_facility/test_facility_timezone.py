"""F-14 / F-22's prerequisite: a facility knows what calendar it keeps.

The audit could not answer this from a dump and named it the change that unblocks both
findings. It did not exist: F2 carried no timezone column, and `DriverProfile.
home_timezone` is written by nothing outside the tests, so the product's only notion of
local time was inert and every calendar-day question was asked of a UTC instant.
"""

from datetime import UTC, date, datetime

import pytest

from app.foundation.f02_facility import public as facility

# one per US zone the product spans, plus the two that break naive implementations
PLACES = [
    ("Tampa FL", 27.9506, -82.4572, "America/New_York"),
    ("Dallas TX", 32.7767, -96.7970, "America/Chicago"),
    ("Denver CO", 39.7392, -104.9903, "America/Denver"),
    ("Los Angeles CA", 34.0522, -118.2437, "America/Los_Angeles"),
    # Arizona does not observe DST — a longitude approximation gets this wrong for half
    # the year, which is why the lookup is a real dataset and not arithmetic
    ("Phoenix AZ", 33.4484, -112.0740, "America/Phoenix"),
]


@pytest.mark.parametrize(("name", "lat", "lon", "expected"), PLACES)
def test_a_facility_resolves_its_own_zone(db, name, lat, lon, expected):
    fac = facility.create_facility(db, facility.FacilityType.truck_stop, name, lat, lon)
    assert facility.facility_timezone(db, fac) == expected


def test_the_zone_is_stored_on_first_use_and_reused(db):
    fac = facility.create_facility(
        db, facility.FacilityType.truck_stop, "Loves", 32.7767, -96.7970
    )
    assert fac.timezone is None, "nothing pays for the lookup until something asks"
    assert facility.facility_timezone(db, fac) == "America/Chicago"
    assert fac.timezone == "America/Chicago", "the answer is persisted, not recomputed"


def test_local_date_is_the_facilitys_calendar_day_not_utcs(db):
    # the audit's own worked example, and the whole of F-22: an 8pm Dallas arrival is
    # already the NEXT UTC day, so a UTC comparison sees one day where a driver saw two
    fac = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "Dock", 32.7767, -96.7970
    )
    arrival = datetime(2026, 8, 8, 1, 0, tzinfo=UTC)  # 8pm Aug 7 in Dallas (CDT, UTC-5)
    assert arrival.date() == date(2026, 8, 8), "the UTC calendar day, and the defect"
    assert facility.local_date(db, fac, arrival) == date(2026, 8, 7)


def test_even_the_middle_of_the_atlantic_resolves(db):
    # written expecting None and a UTC fallback; the lookup covers oceans with nautical
    # Etc/GMT± zones, so the fallback is genuinely a last resort rather than a common
    # path. Recorded because "there is no coordinate this cannot place" is the property
    # that makes the UTC branch below defensive instead of load-bearing.
    fac = facility.create_facility(db, facility.FacilityType.truck_stop, "Nowhere", 0.0, -30.0)
    assert facility.facility_timezone(db, fac) == "Etc/GMT+2"


def test_a_coordinate_the_lookup_cannot_place_falls_back_to_utc_visibly(db, monkeypatch):
    # the defensive branch, exercised directly since no real coordinate reaches it. UTC
    # is exactly today's behaviour, so it is never worse than what it replaces — and it
    # is STORED, so it reads as a facility whose timezone is literally "UTC" rather than
    # as a silent assumption nobody can see.
    from app.foundation.f02_facility.domain import service as f02

    class _Blind:
        def timezone_at(self, **_kwargs):
            return None

    monkeypatch.setattr(f02, "_timezone_finder", lambda: _Blind())
    fac = facility.create_facility(db, facility.FacilityType.truck_stop, "Unplaceable", 1.0, 1.0)
    assert facility.facility_timezone(db, fac) == "UTC"
    assert fac.timezone == "UTC"

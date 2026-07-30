"""AI-CONTEXT: §13.3's quiet hours were INVERTED for every driver (§23 entry 115).

"Default 22:00-06:00 **local** (driver-adjustable)". `in_quiet_hours` honours that
faithfully — it converts server time into `prefs.timezone` — and `prefs.timezone`
defaults to "UTC" and **was written by nothing in the tree**. There was no route, no
client call and no screen; the column existed and nobody could reach it.

So the window landed on the wrong eight hours for everyone. This product is for US truck
drivers exclusively, and the shipped default silenced them through the working afternoon
and evening while leaving them reachable at 03:00:

    America/Los_Angeles   silenced 15:00-23:00
    America/Denver        silenced 16:00-24:00
    America/Chicago       silenced 17:00-24:00 (+ 00:00-01:00)
    America/New_York      silenced 18:00-24:00 (+ 00:00-02:00)

P0 never suffered — `dispatch` sends it before the quiet-hours branch — so no detention
alert was ever swallowed. Every P1 was: the free-time warning, doc expiry,
`protection_gap`, and the lot-status prompt that only became reachable the day before.

`test_the_shipped_default_is_wrong_for_every_us_driver` is the one to read: it asserts
the CORRECTED behaviour for four real zones, and it is the assertion that was red.
"""

from datetime import UTC, datetime
from datetime import time as dt_time
from zoneinfo import ZoneInfo

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f08_notifications import public as notify

US_ZONES = [
    "America/Los_Angeles",
    "America/Denver",
    "America/Chicago",
    "America/New_York",
]


def _driver(db, email, timezone=None):
    account = identity.register_account(db, email, "pw-123456")
    if timezone:
        notify.set_prefs(db, account.id, timezone=timezone)
    return account


def _send_at(db, account, local_hour, zone):
    """Dispatch a P1 at a wall-clock hour in the driver's own zone."""
    when = datetime(2026, 7, 31, local_hour, 0, tzinfo=ZoneInfo(zone)).astimezone(UTC)
    return notify.dispatch(
        db,
        account.id,
        notify.NotificationTier.P1,
        "free_time_warning",
        "30 minutes of free time left",
        "Arrived 09:12",
        "/load",
        notify.RecordingNotificationGateway(),
        now=when,
    )


@pytest.mark.parametrize("zone", US_ZONES)
def test_the_shipped_default_is_wrong_for_every_us_driver(db, zone):
    """19:00 local — evening, hours before §13.3's window opens, and the driver is very
    likely still rolling. **It was silenced in all four zones**, which is why this hour
    and not a friendlier-sounding one: 17:00 happened to survive in New_York, so a test
    written there would have been green in the zone with the smallest offset and taught
    us nothing.

    This is the whole defect in one assertion: the driver's own timezone has to reach the
    server, or "local" means nothing and the window lands wherever UTC happens to put it.
    """
    account = _driver(db, f"evening-{zone.replace('/', '-')}@example.com", timezone=zone)

    note = _send_at(db, account, 19, zone)

    assert note.status == notify.NotificationStatus.sent, (
        f"a driver in {zone} was silenced at 19:00 local"
    )
    assert note.suppress_reason is None


@pytest.mark.parametrize("zone", US_ZONES)
def test_the_night_is_still_quiet_in_every_zone(db, zone):
    """The other half. Fixing the inversion must not simply disable quiet hours —
    23:00 local is inside §13.3's window and stays held."""
    account = _driver(db, f"night-{zone.replace('/', '-')}@example.com", timezone=zone)

    note = _send_at(db, account, 23, zone)

    assert note.status == notify.NotificationStatus.suppressed
    assert note.suppress_reason == notify.SuppressReason.quiet_hours


@pytest.mark.parametrize("zone", US_ZONES)
def test_the_window_is_2200_to_0600_local_in_every_zone(db, zone):
    """The measured table from §23 entry 115, asserted rather than described."""
    account = _driver(db, f"table-{zone.replace('/', '-')}@example.com", timezone=zone)
    prefs = notify.get_or_create_prefs(db, account.id)

    quiet = [
        hour
        for hour in range(24)
        if notify.in_quiet_hours(
            prefs, datetime(2026, 7, 31, hour, 0, tzinfo=ZoneInfo(zone)).astimezone(UTC)
        )
    ]

    assert quiet == [0, 1, 2, 3, 4, 5, 22, 23], f"{zone} is quiet at the wrong hours"


def test_p0_was_never_affected(db):
    """Worth pinning: the inversion could not have swallowed a detention alert, because
    `dispatch` sends P0 before it ever looks at quiet hours. If that order changes, the
    blast radius of a bug like this one changes with it."""
    account = _driver(db, "p0@example.com", timezone="America/Denver")
    when = datetime(2026, 7, 31, 3, 0, tzinfo=ZoneInfo("America/Denver")).astimezone(UTC)

    note = notify.dispatch(
        db,
        account.id,
        notify.NotificationTier.P0,
        "detention_started",
        "Detention started · $75/h",
        "Notice ready to send",
        "/load",
        notify.RecordingNotificationGateway(),
        now=when,
    )

    assert note.status == notify.NotificationStatus.sent


# --- the driver's own window (§13.3 "driver-adjustable") ---


def test_a_driver_can_move_their_window(db):
    """A night-shift driver sleeps in the day, and §13.3 says they may say so."""
    account = _driver(db, "nightshift@example.com", timezone="America/Chicago")
    notify.set_prefs(db, account.id, quiet_start=dt_time(9, 0), quiet_end=dt_time(17, 0))

    assert _send_at(db, account, 11, "America/Chicago").suppress_reason == (
        notify.SuppressReason.quiet_hours
    )
    assert _send_at(db, account, 23, "America/Chicago").status == notify.NotificationStatus.sent


def test_an_empty_window_means_no_quiet_hours(db):
    """`in_quiet_hours` compares `start <= local < end`, so start == end can contain no
    hour. That is a real state a driver can choose, not an accident — the tests have
    relied on it for months and the copy now says so out loud."""
    # a fresh driver per hour, because §13.1's 2/day budget would suppress the third
    # send for a reason that has nothing to do with the rule under test — the first
    # version of this test read `budget` as a quiet-hours failure
    for hour in (3, 11, 23):
        account = _driver(db, f"always-{hour}@example.com", timezone="America/Denver")
        notify.set_prefs(db, account.id, quiet_start=dt_time(3, 0), quiet_end=dt_time(3, 0))

        assert _send_at(db, account, hour, "America/Denver").status == (
            notify.NotificationStatus.sent
        ), f"{hour}:00 was held despite an empty quiet window"


def test_setting_one_field_leaves_the_others_alone(db):
    """The boot-time timezone sync must not clobber a window the driver set — it PUTs
    the zone alone on every sign-in, and a full-object write would silently undo them."""
    account = _driver(db, "partial@example.com")
    notify.set_prefs(db, account.id, quiet_start=dt_time(9, 0), quiet_end=dt_time(17, 0))

    notify.set_prefs(db, account.id, timezone="America/New_York")

    prefs = notify.get_or_create_prefs(db, account.id)
    assert prefs.timezone == "America/New_York"
    assert prefs.quiet_start == dt_time(9, 0)
    assert prefs.quiet_end == dt_time(17, 0)


def test_an_unknown_timezone_is_refused(db):
    """Validated by `ZoneInfo`'s own lookup rather than a hand-kept list, which is the
    only version that stays true as tzdata changes."""
    account = _driver(db, "badzone@example.com")

    with pytest.raises(notify.UnknownTimezone):
        notify.set_prefs(db, account.id, timezone="Mars/Olympus_Mons")

    assert notify.get_or_create_prefs(db, account.id).timezone == "UTC"

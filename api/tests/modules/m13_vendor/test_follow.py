"""AI-CONTEXT: "follow this cook" — the event the food loop was missing.

Before this, the ONLY vendor notification was a cancellation, sent to drivers who
had previously *confirmed* that vendor's presence. That heuristic was doing two jobs
at once: standing in for CONSENT and for GEOGRAPHY. The result was a loop closed to
people who had already found the cook for themselves.

A follow supplies real consent — which removes the geographic stand-in and makes the
class's long-declared `route_relevant_only` something that has to actually be
enforced. These tests are that enforcement:

· a follower too far away is not notified
· a follower F3 cannot currently PLACE is not notified — a stale ping is not a
  location, and guessing is worse than staying quiet
· the class caps are untouched by following; consent to be told is never permission
  to be told twice
· when several followed cooks publish the same day, the ONE push the cap allows goes
  to the nearest, not to whoever the loop reached first
"""

from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f08_notifications import public as notify
from app.modules.m13_vendor import public as m13

DALLAS = (32.7767, -96.7970)
NEARBY = (32.9000, -96.7970)  # ~14 km
FAR = (40.7128, -74.0060)  # New York — well beyond any sane radius
T0 = datetime(2026, 7, 25, 17, 0, tzinfo=UTC)
MENU = [m13.OfferingIn("Osh", 1200)]


def _account(db, email):
    return identity.register_account(db, email, "pw-123456")


def _facility(db, name="Loves 212", coords=DALLAS):
    return facility.create_facility(db, facility.FacilityType.truck_stop, name, *coords)


def _vendor(db, email="cook@example.com", name="Osh Express"):
    account = _account(db, email)
    return m13.register_vendor(
        db,
        account.id,
        name,
        m13.VendorType.food_mobile,
        metro="dallas-tx",
        languages=["uz", "ru"],
        halal_answered=True,
    )


def _driver_at(db, email, coords, ping_age=timedelta(minutes=30)):
    driver = _account(db, email)
    location.record_ping(db, driver.id, *coords, occurred_at=T0 - ping_age)
    return driver


def _publish(db, vendor, fac, gateway=None, start=T0 + timedelta(hours=2)):
    return m13.publish_appearance(
        db, vendor, fac.id, start, start + timedelta(hours=4), MENU, now=T0, gateway=gateway
    )


def _gateway():
    return notify.RecordingNotificationGateway()


def test_a_follower_nearby_hears_that_a_cook_published(db):
    vendor, fac = _vendor(db), _facility(db)
    driver = _driver_at(db, "near@example.com", NEARBY)
    m13.follow_vendor(db, driver.id, vendor.id)

    gateway = _gateway()
    _publish(db, vendor, fac, gateway)

    sent = [n for n in db.query(notify.Notification).all() if n.account_id == driver.id]
    assert len(sent) == 1
    assert sent[0].status == notify.NotificationStatus.queued
    assert vendor.name in sent[0].title
    # §13.5: every notification deep-links to the exact thing it describes
    assert sent[0].deep_link == f"/vendor/{vendor.id}"


def test_a_follower_far_away_is_not_interrupted(db):
    """Following a cook in Dallas must not push to a driver in New York. This is the
    gate that finally makes `route_relevant_only` true rather than declared."""
    vendor, fac = _vendor(db), _facility(db)
    driver = _driver_at(db, "far@example.com", FAR)
    m13.follow_vendor(db, driver.id, vendor.id)

    _publish(db, vendor, fac, _gateway())

    assert [n for n in db.query(notify.Notification).all() if n.account_id == driver.id] == []


def test_a_follower_we_cannot_place_is_left_alone(db):
    """A ping from three days ago is a place the driver has long left. Targeting an
    interruption on it would be confidently wrong, so nothing is sent at all."""
    vendor, fac = _vendor(db), _facility(db)
    stale = _driver_at(db, "stale@example.com", NEARBY, ping_age=timedelta(days=3))
    never = _account(db, "neverpinged@example.com")
    m13.follow_vendor(db, stale.id, vendor.id)
    m13.follow_vendor(db, never.id, vendor.id)

    _publish(db, vendor, fac, _gateway())

    everyone = db.query(notify.Notification).all()
    assert [n for n in everyone if n.account_id in (stale.id, never.id)] == []


def test_someone_who_never_followed_hears_nothing_about_a_publish(db):
    """The old audience — anyone who once confirmed presence — is NOT consent. A
    crowd contribution is a contribution, not a request to be notified."""
    vendor, fac = _vendor(db), _facility(db)
    passer_by = _driver_at(db, "passerby@example.com", NEARBY)
    m13.confirm_presence(db, passer_by.id, vendor.id, fac.id, True, now=T0)

    _publish(db, vendor, fac, _gateway())

    assert [n for n in db.query(notify.Notification).all() if n.account_id == passer_by.id] == []


def test_a_cancellation_reaches_followers_AND_past_confirmers(db):
    """A follower who planned a stop has the strongest claim on hearing it is off —
    but someone who confirmed the cook an hour ago may be driving there too."""
    vendor, fac = _vendor(db), _facility(db)
    follower = _driver_at(db, "cx-follower@example.com", NEARBY)
    confirmer = _driver_at(db, "cx-confirmer@example.com", NEARBY)
    m13.follow_vendor(db, follower.id, vendor.id)
    m13.confirm_presence(db, confirmer.id, vendor.id, fac.id, True, now=T0)
    # the confirmer turned the class on in More but follows nobody. Opt-in was
    # always required to reach them, before this change and after it — following is
    # a second, narrower consent, never a replacement for the first.
    notify.set_class_opt_in(db, confirmer.id, m13.VENDOR_ALERT, True)

    appearance = _publish(db, vendor, fac)[0]
    m13.cancel_appearance(db, appearance, gateway=_gateway(), now=T0)

    reached = {
        n.account_id
        for n in db.query(notify.Notification).all()
        if n.status == notify.NotificationStatus.queued and "cancelled" in n.title
    }
    assert follower.id in reached
    assert confirmer.id in reached


def test_following_does_not_buy_a_second_push(db):
    """Consent to be told is never permission to be told twice. The class cap is one
    a day and a follower is subject to it exactly like anyone else."""
    first, second = _vendor(db), _vendor(db, "cook2@example.com", "Samsa House")
    fac = _facility(db)
    driver = _driver_at(db, "capped@example.com", NEARBY)
    m13.follow_vendor(db, driver.id, first.id)
    m13.follow_vendor(db, driver.id, second.id)

    _publish(db, first, fac, _gateway())
    _publish(db, second, fac, _gateway())

    mine = [n for n in db.query(notify.Notification).all() if n.account_id == driver.id]
    sent = [n for n in mine if n.status == notify.NotificationStatus.queued]
    suppressed = [n for n in mine if n.status == notify.NotificationStatus.suppressed]
    assert len(sent) == 1
    assert len(suppressed) == 1
    assert suppressed[0].suppress_reason == notify.SuppressReason.budget


def test_the_one_push_that_survives_the_cap_goes_to_the_nearest(db):
    """Two followed cooks publish the same day and the cap allows one. Ordering the
    audience by distance means the survivor is the useful one rather than whichever
    the loop happened to reach first."""
    vendor = _vendor(db)
    close_lot = _facility(db, "Close Lot", NEARBY)
    far_lot = _facility(db, "Far Lot", FAR)
    driver = _driver_at(db, "nearest@example.com", NEARBY)
    m13.follow_vendor(db, driver.id, vendor.id)

    # the distant lot is published FIRST — order of publication must not decide it
    _publish(db, vendor, far_lot, _gateway())
    _publish(db, vendor, close_lot, _gateway())

    sent = [
        n
        for n in db.query(notify.Notification).all()
        if n.account_id == driver.id and n.status == notify.NotificationStatus.queued
    ]
    assert len(sent) == 1
    assert "Close Lot" in sent[0].body


def test_a_weekly_series_announces_itself_once_not_once_per_occurrence(db):
    """A driver asked about a cook, not about a calendar. A four-week schedule is one
    publish, not one push per Tuesday between now and the horizon."""
    vendor, fac = _vendor(db), _facility(db)
    driver = _driver_at(db, "weekly@example.com", NEARBY)
    m13.follow_vendor(db, driver.id, vendor.id)

    start = T0 + timedelta(hours=2)
    created = m13.publish_appearance(
        db,
        vendor,
        fac.id,
        start,
        start + timedelta(hours=4),
        MENU,
        weekly=[start.weekday()],
        now=T0,
        gateway=_gateway(),
    )

    assert len(created) > 1  # the series really did materialise several occurrences
    mine = [n for n in db.query(notify.Notification).all() if n.account_id == driver.id]
    assert len(mine) == 1


def test_muting_after_following_still_silences(db):
    vendor, fac = _vendor(db), _facility(db)
    driver = _driver_at(db, "muted@example.com", NEARBY)
    m13.follow_vendor(db, driver.id, vendor.id)
    notify.mute_subject(db, driver.id, m13.VENDOR_ALERT, str(vendor.id))

    _publish(db, vendor, fac, _gateway())

    mine = [n for n in db.query(notify.Notification).all() if n.account_id == driver.id]
    assert all(n.status == notify.NotificationStatus.suppressed for n in mine)
    assert mine[0].suppress_reason == notify.SuppressReason.muted


def test_unfollowing_ends_it(db):
    vendor, fac = _vendor(db), _facility(db)
    driver = _driver_at(db, "gone@example.com", NEARBY)
    m13.follow_vendor(db, driver.id, vendor.id)
    assert m13.is_following_vendor(db, driver.id, vendor.id) is True

    m13.unfollow_vendor(db, driver.id, vendor.id)
    assert m13.is_following_vendor(db, driver.id, vendor.id) is False

    _publish(db, vendor, fac, _gateway())
    assert [n for n in db.query(notify.Notification).all() if n.account_id == driver.id] == []


def test_publishing_without_a_gateway_notifies_nobody_and_still_publishes(db):
    """Most callers (tests, admin tooling, backfills) pass no gateway. That must be a
    quiet no-op, never a crash and never a silent failure to publish."""
    vendor, fac = _vendor(db), _facility(db)
    driver = _driver_at(db, "nogw@example.com", NEARBY)
    m13.follow_vendor(db, driver.id, vendor.id)

    created = _publish(db, vendor, fac)

    assert len(created) == 1
    assert db.query(notify.Notification).count() == 0

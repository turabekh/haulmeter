"""AI-CONTEXT: the P0 §13.2 calls "booking failed", built against the event that
actually exists (§23 entry 108).

`book()` has exactly one failure — `SpotUnavailable` on a double-book — raised inside
the driver's own request and answered by §12.4 error copy on the screen they are
already reading. A push about that would tell someone what they are looking at.

The real money event a driver is NOT looking at is a booking being taken away, and the
whole refund engine had been written and left with no endpoint calling it. These tests
cover that engine reaching daylight, and the rule that decides who hears about it: a P0
announces money that moved WITHOUT you.
"""

from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f08_notifications import public as notify
from app.modules.m06_parking import public as m6

DALLAS = (32.7767, -96.7970)


def _booking(db, start_in=timedelta(days=3), price=2400):
    owner = identity.register_account(db, "owner@example.com", "pw-123456")
    driver = identity.register_account(db, "driver@example.com", "pw-123456")
    prop = m6.create_property(db, owner.id, "Riverside Lot", *DALLAS, vetted=True)
    spot = m6.add_spot(db, prop, "A1", price_cents_per_night=price)
    now = datetime.now(UTC)
    booking = m6.book(db, spot, driver.id, now + start_in, now + start_in + timedelta(days=1))
    return owner, driver, spot, booking, now


# --- the engine reaching daylight ---
def test_a_booking_can_finally_be_canceled(db):
    owner, driver, spot, booking, now = _booking(db)

    m6.cancel(db, booking, now, actor_account_id=driver.id)

    assert booking.state == m6.BookingState.refunded
    assert booking.refund_entry_ref is not None


def test_a_late_cancellation_refunds_half(db):
    owner, driver, spot, booking, now = _booking(db, start_in=timedelta(hours=2), price=2400)
    gw = notify.RecordingNotificationGateway()

    m6.cancel(db, booking, now, actor_account_id=owner.id, gateway=gw)

    assert booking.state == m6.BookingState.refunded
    assert gw.sent[0].subject == "Booking canceled · $12 refunded"


# --- who hears about it ---
def test_the_driver_who_canceled_is_told_nothing(db):
    owner, driver, spot, booking, now = _booking(db)
    gw = notify.RecordingNotificationGateway()

    m6.cancel(db, booking, now, actor_account_id=driver.id, gateway=gw)

    assert gw.sent == []
    assert notify.inbox(db, driver.id) == []


def test_the_owner_canceling_reaches_the_driver_as_a_p0(db):
    owner, driver, spot, booking, now = _booking(db, price=2400)
    gw = notify.RecordingNotificationGateway()

    m6.cancel(db, booking, now, actor_account_id=owner.id, gateway=gw)

    rows = notify.inbox(db, driver.id)
    assert len(rows) == 1
    sent = rows[0]
    assert sent.tier == notify.NotificationTier.P0
    assert sent.status == notify.NotificationStatus.sent
    assert sent.title == "Booking canceled · $24 refunded"
    assert sent.body == "Riverside Lot canceled your spot. Book another nearby."


def test_the_p0_deep_links_to_the_spot_not_a_tab_root(db):
    owner, driver, spot, booking, now = _booking(db)
    gw = notify.RecordingNotificationGateway()

    m6.cancel(db, booking, now, actor_account_id=owner.id, gateway=gw)

    assert notify.inbox(db, driver.id)[0].deep_link == f"/book/{spot.id}"


def test_the_owner_is_not_told_about_their_own_action(db):
    owner, driver, spot, booking, now = _booking(db)
    gw = notify.RecordingNotificationGateway()

    m6.cancel(db, booking, now, actor_account_id=owner.id, gateway=gw)

    assert notify.inbox(db, owner.id) == []


def test_booking_canceled_is_not_an_opt_in_class(db):
    assert notify.get_class(m6.BOOKING_CANCELED_CATEGORY) is None


def test_cancelling_without_a_gateway_still_cancels(db):
    """The refund is the transaction; the notification rides on top and must never be
    what a cancellation depends on."""
    owner, driver, spot, booking, now = _booking(db)

    m6.cancel(db, booking, now, actor_account_id=owner.id, gateway=None)

    assert booking.state == m6.BookingState.refunded

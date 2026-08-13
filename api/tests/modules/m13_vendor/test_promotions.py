"""AI-CONTEXT: M13-FR6 — promotions (PRD §17 Q10, resolved 2026-07-25).

The constitutional line these tests hold: **promotions never touch organic order.**
Q-3 says pay-to-rank in discovery is out, and the way that survives contact with a
growing codebase is for the ranking function to have no promotion input at all. So
this file asserts the ranked list is byte-identical with and without a promotion
live, and the Session-A grep-test on `rank_entries` keeps passing UNMODIFIED.

Everything else here is the anti-spam envelope: promotions ride the existing
`vendor_alert` caps rather than getting their own softer ones.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f08_notifications import public as notify
from app.modules.m13_vendor import public as m13

DALLAS = (32.7767, -96.7970)
T0 = datetime(2026, 7, 26, 14, 0, tzinfo=UTC)  # outside quiet hours
MENU = [m13.OfferingIn("Osh", 1200)]


def _account(db, email):
    return identity.register_account(db, email, "pw-123456")


def _vendor(db, email="cook@example.com", name="Osh Express", **kwargs):
    account = _account(db, email)
    defaults = {"languages": ["uz"], "halal_answered": True, "metro": "dallas-tx"}
    return m13.register_vendor(
        db, account.id, name, m13.VendorType.food_mobile, **{**defaults, **kwargs}
    )


def _facility(db, name="Loves 212"):
    return facility.create_facility(db, facility.FacilityType.truck_stop, name, *DALLAS)


def _publish(db, vendor, fac, start=T0):
    return m13.publish_appearance(
        db, vendor, fac.id, start, start + timedelta(hours=4), MENU, now=start
    )[0]


def _promo(db, vendor, text="Free chai with any plate", start=T0, hours=6, **kwargs):
    return m13.create_promotion(
        db, vendor, text, start, start + timedelta(hours=hours), now=start, **kwargs
    )


def _confirm(db, vendor, fac, email, now=T0):
    driver = _account(db, email)
    location.arm_geofence(db, driver.id, fac.id)
    location.evaluate_ping(db, driver.id, *DALLAS, occurred_at=now)
    m13.confirm_presence(db, driver.id, vendor.id, fac.id, True, now=now)
    return driver


# --- Q-3: the constitutional line ---
def test_a_promotion_does_not_change_organic_order(db):
    fac = _facility(db)
    first = _vendor(db, "a@x.com", "Alpha Kitchen")
    second = _vendor(db, "b@x.com", "Beta Kitchen", metro="austin-tx")
    _publish(db, first, fac)
    _publish(db, second, fac)
    at = T0 + timedelta(minutes=30)

    before = [e.vendor.id for e in m13.vendors_at_facility(db, fac.id, now=at, limit=0)]
    _promo(db, second)  # the LOWER-ranked vendor buys nothing by promoting
    after = [e.vendor.id for e in m13.vendors_at_facility(db, fac.id, now=at, limit=0)]

    assert before == after


def test_promotions_are_returned_by_a_separate_call_entirely(db):
    # they cannot be folded into discovery by accident, because discovery never
    # sees them — different function, different return type
    fac = _facility(db)
    vendor = _vendor(db)
    _publish(db, vendor, fac)
    _promo(db, vendor)
    at = T0 + timedelta(minutes=30)

    ranked = m13.vendors_at_facility(db, fac.id, now=at)
    slots = m13.promotions_for_facility(db, fac.id, now=at)

    assert all(not hasattr(e, "promotion") for e in ranked)
    assert [s["text"] for s in slots] == ["Free chai with any plate"]
    assert slots[0]["promoted"] is True  # the label the client must render


def test_the_ranking_function_still_has_no_promotion_input(db):
    # the Session-A guarantee, re-asserted from Session B: if someone ever adds a
    # promotion term to rank_entries, this fails here as well as there
    import inspect

    from app.modules.m13_vendor.domain import service as m13_service

    source = inspect.getsource(m13_service.rank_entries)
    for forbidden in ("promo", "promotion", "sponsor", "paid", "bid", "boost"):
        assert forbidden not in source.lower()


# --- rendering scope ---
def test_a_promotion_travels_with_the_vendors_appearances(db):
    fac = _facility(db)
    vendor = _vendor(db)
    _publish(db, vendor, fac)
    _promo(db, vendor)

    assert len(m13.promotions_for_facility(db, fac.id, now=T0 + timedelta(minutes=30))) == 1


def test_a_promotion_does_not_appear_where_the_vendor_is_not(db):
    elsewhere = facility.create_facility(
        db, facility.FacilityType.truck_stop, "Far Stop", 40.0, -100.0
    )
    fac = _facility(db)
    vendor = _vendor(db)
    _publish(db, vendor, fac)
    _promo(db, vendor)

    assert m13.promotions_for_facility(db, elsewhere.id, now=T0 + timedelta(minutes=30)) == []


def test_a_suspended_vendor_promotes_nothing(db):
    fac = _facility(db)
    vendor = _vendor(db)
    _publish(db, vendor, fac)
    _promo(db, vendor)
    vendor.publish_suspended = True

    assert m13.promotions_for_facility(db, fac.id, now=T0 + timedelta(minutes=30)) == []


# --- Q-1 spirit: nothing dead stays visible ---
def test_an_expired_promotion_vanishes(db):
    fac = _facility(db)
    vendor = _vendor(db)
    _publish(db, vendor, fac, start=T0)
    _promo(db, vendor, hours=2)

    later = T0 + timedelta(hours=3)
    assert m13.promotions_for_facility(db, fac.id, now=later) == []
    assert m13.sweep_promotions(db, now=later) == 1


def test_a_promotion_cannot_be_published_already_dead(db):
    vendor = _vendor(db)
    with pytest.raises(m13.InvalidPromotion):
        m13.create_promotion(
            db, vendor, "Yesterday", T0 - timedelta(days=2), T0 - timedelta(days=1), now=T0
        )


def test_a_cancelled_promotion_disappears(db):
    fac = _facility(db)
    vendor = _vendor(db)
    _publish(db, vendor, fac)
    promo = _promo(db, vendor)
    m13.cancel_promotion(db, promo)

    assert m13.promotions_for_facility(db, fac.id, now=T0 + timedelta(minutes=30)) == []


@pytest.mark.parametrize("text", ["", "   ", "x" * 141])
def test_empty_or_overlong_promotion_text_is_refused(db, text):
    vendor = _vendor(db)
    with pytest.raises(m13.InvalidPromotion):
        m13.create_promotion(db, vendor, text, T0, T0 + timedelta(hours=2), now=T0)


# --- push rides the Session-A caps, unloosened ---
def test_a_promotion_push_needs_the_opt_in(db):
    fac = _facility(db)
    vendor = _vendor(db)
    _publish(db, vendor, fac)
    _confirm(db, vendor, fac, "silent@x.com")
    promo = _promo(db, vendor)
    gateway = notify.RecordingNotificationGateway()

    m13.notify_promotion(db, promo, gateway, now=T0 + timedelta(minutes=30))
    assert gateway.sent == []  # never opted in = never consented


def test_an_opted_in_driver_gets_one_promotion(db):
    fac = _facility(db)
    vendor = _vendor(db)
    _publish(db, vendor, fac)
    driver = _confirm(db, vendor, fac, "keen@x.com")
    notify.set_class_opt_in(db, driver.id, m13.VENDOR_ALERT, True)
    promo = _promo(db, vendor)
    gateway = notify.RecordingNotificationGateway()

    m13.notify_promotion(db, promo, gateway, now=T0 + timedelta(minutes=30))
    # the push_delivery sweep is what hands a queued notification to the
    # push service; the request only decides (§13.1 laws included)
    notify.deliver_queued_notifications(db, lambda _a: gateway)
    assert len(gateway.sent) == 1
    assert promo.pushed_at is not None


def test_the_one_a_day_cap_still_bites_across_promotions(db):
    # FR6's cap is per DRIVER per day, not per promotion — two promotions in one day
    # must not become two pushes
    fac = _facility(db)
    vendor = _vendor(db)
    _publish(db, vendor, fac)
    driver = _confirm(db, vendor, fac, "capped@x.com")
    notify.set_class_opt_in(db, driver.id, m13.VENDOR_ALERT, True)
    gateway = notify.RecordingNotificationGateway()

    m13.notify_promotion(db, _promo(db, vendor, "First"), gateway, now=T0 + timedelta(minutes=30))
    m13.notify_promotion(db, _promo(db, vendor, "Second"), gateway, now=T0 + timedelta(hours=2))

    # the push_delivery sweep is what hands a queued notification to the
    # push service; the request only decides (§13.1 laws included)
    notify.deliver_queued_notifications(db, lambda _a: gateway)
    assert len(gateway.sent) == 1


def test_muting_a_vendor_stops_its_promotions(db):
    fac = _facility(db)
    vendor = _vendor(db)
    _publish(db, vendor, fac)
    driver = _confirm(db, vendor, fac, "muted@x.com")
    notify.set_class_opt_in(db, driver.id, m13.VENDOR_ALERT, True)
    notify.mute_subject(db, driver.id, m13.VENDOR_ALERT, str(vendor.id))
    gateway = notify.RecordingNotificationGateway()

    m13.notify_promotion(db, _promo(db, vendor), gateway, now=T0 + timedelta(minutes=30))
    assert gateway.sent == []


def test_quiet_hours_hold_for_promotions(db):
    fac = _facility(db)
    vendor = _vendor(db)
    _publish(db, vendor, fac)
    driver = _confirm(db, vendor, fac, "night@x.com")
    notify.set_class_opt_in(db, driver.id, m13.VENDOR_ALERT, True)
    night = datetime(2026, 7, 26, 23, 30, tzinfo=UTC)
    promo = _promo(db, vendor, start=T0, hours=12)
    gateway = notify.RecordingNotificationGateway()

    m13.notify_promotion(db, promo, gateway, now=night)
    assert gateway.sent == []


def test_a_reported_promotion_hides_pending_review(db):
    fac = _facility(db)
    vendor = _vendor(db)
    _publish(db, vendor, fac)
    promo = _promo(db, vendor)
    reporter = _account(db, "flag@x.com")

    m13.report_content(
        db,
        m13.CONTENT_PROMOTION,
        promo.id,
        vendor.id,
        reporter.id,
        m13.ModerationReason.false_information,
        now=T0,
    )

    assert promo.status == m13.PromotionStatus.hidden_pending
    assert m13.promotions_for_facility(db, fac.id, now=T0 + timedelta(minutes=30)) == []


def test_there_is_no_price_or_bid_anywhere_on_a_promotion(db):
    # Q10: free in Phase A. Paid placement is a future owner decision, and building
    # a price column now would be speculative scaffolding for it.
    columns = {c.name for c in m13.Promotion.__table__.columns}
    assert not columns & {"price_cents", "bid", "budget", "amount", "cost", "billing_ref"}

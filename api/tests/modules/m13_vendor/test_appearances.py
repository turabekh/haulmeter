"""AI-CONTEXT: M13-FR2 — appearances, schedules, and the quality laws that keep the
food layer from becoming a classifieds board.

Q-4 (publish floor): an appearance a driver cannot act on must not publish.
Q-1 (no dead content): windows expire, "not here" lapses, silence deactivates.
Q-2 (accountability): no-shows demote, three in a row suspend publishing.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f08_notifications import public as notify
from app.foundation.f13_flags import public as flags
from app.foundation.f14_admin import public as admin
from app.modules.m13_vendor import public as m13

DALLAS = (32.7767, -96.7970)
T0 = datetime(2026, 7, 25, 17, 0, tzinfo=UTC)  # a Saturday evening
MENU = [m13.OfferingIn("Osh", 1200, portions=40), m13.OfferingIn("Somsa", 400)]


def _account(db, email):
    return identity.register_account(db, email, "pw-123456")


def _facility(db, name="Loves 212"):
    return facility.create_facility(db, facility.FacilityType.truck_stop, name, *DALLAS)


def _vendor(db, email="cook@example.com", name="Osh Express", **kwargs):
    account = _account(db, email)
    defaults = {"languages": ["uz", "ru"], "halal_answered": True}
    return m13.register_vendor(
        db,
        account.id,
        name,
        m13.VendorType.food_mobile,
        metro="dallas-tx",
        **{**defaults, **kwargs},
    )


def _publish(db, vendor, fac, start=T0, hours=4, **kwargs):
    return m13.publish_appearance(
        db, vendor, fac.id, start, start + timedelta(hours=hours), MENU, now=start, **kwargs
    )


def _confirm(db, vendor, fac, email, present=True, now=T0):
    driver = _account(db, email)
    location.arm_geofence(db, driver.id, fac.id)
    location.evaluate_ping(db, driver.id, *DALLAS, occurred_at=now)
    m13.confirm_presence(db, driver.id, vendor.id, fac.id, present, now=now)
    return driver


# --- Q-4: listing completeness floor ---
def test_publishing_needs_an_offering_with_a_price(db):
    # "food available" is not actionable — a driver cannot decide to detour on it
    vendor, fac = _vendor(db), _facility(db)
    with pytest.raises(m13.ListingIncomplete) as exc:
        m13.publish_appearance(db, vendor, fac.id, T0, T0 + timedelta(hours=3), [], now=T0)
    assert "offering_with_price" in exc.value.missing


def test_publishing_needs_a_complete_profile(db):
    vendor, fac = _vendor(db, languages=[], halal_answered=False), _facility(db)
    with pytest.raises(m13.ListingIncomplete) as exc:
        _publish(db, vendor, fac)
    assert set(exc.value.missing) >= {"languages", "halal_disclosure"}


def test_declining_to_claim_halal_is_a_complete_answer(db):
    # "none" is valid, blank is not — a vendor must be able to honestly not claim it
    vendor = _vendor(db, halal_answered=True, halal_disclosure=None)
    assert m13.profile_complete(vendor) is True


def test_publishing_needs_a_real_facility_and_a_forward_window(db):
    vendor, fac = _vendor(db), _facility(db)
    with pytest.raises(m13.ListingIncomplete) as exc:
        m13.publish_appearance(db, vendor, fac.id, T0, T0 - timedelta(hours=1), MENU, now=T0)
    assert "time_window" in exc.value.missing


def test_a_complete_listing_publishes(db):
    vendor, fac = _vendor(db), _facility(db)
    created = _publish(db, vendor, fac, property_approved=True)

    assert len(created) == 1
    assert created[0].status == m13.AppearanceStatus.scheduled
    assert [o.name for o in created[0].offerings] == ["Osh", "Somsa"]
    assert vendor.last_published_at is not None


# --- FR2: recurrence ---
def test_a_weekly_schedule_materializes_concrete_occurrences(db):
    # concrete rows, not a rule expanded at read time: Q-1 marks occurrences lapsed
    # and Q-2 scores them, and neither can act on a rule
    vendor, fac = _vendor(db), _facility(db)
    created = _publish(db, vendor, fac, weekly=[T0.weekday()])

    assert len(created) == 4  # 28-day horizon / weekly
    assert len({a.series_id for a in created}) == 1
    assert all(a.recurrence == {"weekly": [T0.weekday()]} for a in created)
    assert all(len(a.offerings) == 2 for a in created)


def test_the_recurrence_horizon_is_tunable(db):
    vendor, fac = _vendor(db), _facility(db)
    flags.set_config(db, m13.CONFIG_RECURRENCE_HORIZON_DAYS, 7)
    created = _publish(db, vendor, fac, weekly=[T0.weekday()])
    assert len(created) == 1


def test_cancelling_a_series_stops_every_future_occurrence(db):
    vendor, fac = _vendor(db), _facility(db)
    created = _publish(db, vendor, fac, weekly=[T0.weekday()])

    m13.cancel_appearance(db, created[0], now=T0, whole_series=True)

    assert all(a.status == m13.AppearanceStatus.cancelled for a in created)


# --- FR2: cancellation is the one Session-A vendor_alert event ---
def test_cancelling_alerts_drivers_who_confirmed_this_vendor(db):
    vendor, fac = _vendor(db), _facility(db)
    appearance = _publish(db, vendor, fac)[0]
    driver = _confirm(db, vendor, fac, "watcher@example.com")
    notify.set_class_opt_in(db, driver.id, m13.VENDOR_ALERT, True)
    gateway = notify.RecordingNotificationGateway()

    m13.cancel_appearance(db, appearance, gateway=gateway, now=T0)

    # the push_delivery sweep is what hands a queued notification to the
    # push service; the request only decides (§13.1 laws included)
    notify.deliver_queued_notifications(db, lambda _a: gateway)
    assert len(gateway.sent) == 1
    assert "cancelled" in gateway.sent[0].subject


def test_cancellation_alerts_still_obey_the_opt_in(db):
    # M13 never bypasses the class gate: a driver who never opted in hears nothing
    vendor, fac = _vendor(db), _facility(db)
    appearance = _publish(db, vendor, fac)[0]
    _confirm(db, vendor, fac, "silent@example.com")
    gateway = notify.RecordingNotificationGateway()

    m13.cancel_appearance(db, appearance, gateway=gateway, now=T0)

    assert gateway.sent == []


# --- Q-1: no dead content, ever ---
def test_a_window_that_ended_is_done_and_leaves_discovery(db):
    vendor, fac = _vendor(db), _facility(db)
    appearance = _publish(db, vendor, fac)[0]
    after = T0 + timedelta(hours=5)

    m13.sweep_appearances(db, now=after)

    assert appearance.status == m13.AppearanceStatus.done
    assert m13.vendors_at_facility(db, fac.id, now=after) == []


def test_a_live_appearance_lapses_on_a_sustained_not_here_belief(db):
    vendor, fac = _vendor(db), _facility(db)
    appearance = _publish(db, vendor, fac)[0]
    during = T0 + timedelta(hours=1)
    m13.sweep_appearances(db, now=during)
    assert appearance.status == m13.AppearanceStatus.live

    _confirm(db, vendor, fac, "nope1@example.com", present=False, now=during)
    _confirm(db, vendor, fac, "nope2@example.com", present=False, now=during)
    m13.sweep_appearances(db, now=during)

    assert appearance.status == m13.AppearanceStatus.lapsed
    assert m13.vendors_at_facility(db, fac.id, now=during) == []


def test_one_lone_not_here_report_does_not_erase_a_vendor(db):
    # a single driver who couldn't find the truck must not delete a real listing
    vendor, fac = _vendor(db), _facility(db)
    appearance = _publish(db, vendor, fac)[0]
    during = T0 + timedelta(hours=1)
    m13.sweep_appearances(db, now=during)
    _confirm(db, vendor, fac, "lonely@example.com", present=False, now=during)

    m13.sweep_appearances(db, now=during)
    assert appearance.status == m13.AppearanceStatus.live


def test_a_vendor_silent_for_28_days_leaves_discovery_but_keeps_its_profile(db):
    vendor, fac = _vendor(db), _facility(db)
    _publish(db, vendor, fac)
    later = T0 + timedelta(days=29)

    assert m13.in_discovery(db, vendor, now=later) is False
    assert vendor.status == m13.VendorStatus.active  # dormancy, not deletion
    assert m13.resolve_vendor(db, vendor.id) is not None


def test_publishing_again_reactivates_a_dormant_vendor(db):
    vendor, fac = _vendor(db), _facility(db)
    _publish(db, vendor, fac)
    later = T0 + timedelta(days=29)
    assert m13.in_discovery(db, vendor, now=later) is False

    _publish(db, vendor, fac, start=later)
    assert m13.in_discovery(db, vendor, now=later) is True


# --- Q-2: reliability is public and load-bearing ---
def test_show_up_rate_counts_confirmed_over_published(db):
    vendor, fac = _vendor(db), _facility(db)
    for day in range(3):
        start = T0 + timedelta(days=day)
        _publish(db, vendor, fac, start=start)
        if day < 2:
            _confirm(db, vendor, fac, f"d{day}@example.com", now=start + timedelta(hours=1))
        m13.sweep_appearances(db, now=start + timedelta(hours=6))

    score = m13.reliability(db, vendor.id)
    assert (score.confirmed, score.published) == (2, 3)


def test_a_vendor_with_no_history_is_neither_trusted_nor_punished(db):
    vendor = _vendor(db)
    assert m13.reliability(db, vendor.id).rate == 1.0


def test_three_consecutive_no_shows_suspend_publishing_pending_review(db):
    vendor, fac = _vendor(db), _facility(db)
    for day in range(m13.NO_SHOW_STRIKES):
        start = T0 + timedelta(days=day)
        _publish(db, vendor, fac, start=start)
        m13.sweep_appearances(db, now=start + timedelta(hours=6))

    assert vendor.consecutive_no_shows == m13.NO_SHOW_STRIKES
    assert vendor.publish_suspended is True
    assert any(i.content_kind == "vendor_no_shows" for i in admin.list_pending_moderation(db))

    with pytest.raises(m13.PublishSuspended):
        _publish(db, vendor, fac, start=T0 + timedelta(days=5))


def test_one_confirmed_show_up_clears_the_strike_count(db):
    # the counter is CONSECUTIVE — a vendor who shows up is not haunted by old misses
    vendor, fac = _vendor(db), _facility(db)
    _publish(db, vendor, fac)
    m13.sweep_appearances(db, now=T0 + timedelta(hours=6))
    assert vendor.consecutive_no_shows == 1

    start = T0 + timedelta(days=1)
    _publish(db, vendor, fac, start=start)
    _confirm(db, vendor, fac, "showed@example.com", now=start + timedelta(hours=1))
    m13.sweep_appearances(db, now=start + timedelta(hours=6))

    assert vendor.consecutive_no_shows == 0
    assert vendor.publish_suspended is False

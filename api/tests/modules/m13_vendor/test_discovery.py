"""AI-CONTEXT: M13-FR3/FR4 — discovery order, noise budget, empty states, and the
honesty of a confirmation.

Q-3 (ranking): deterministic and incorruptible; there is no promotion input at all.
Q-6 (noise budget): two vendors on a card, three on a corridor — food enriches the
     map, it never decorates it.
Q-7 (empty states): nothing to show renders nothing, never filler.
§11.7: a vendor's own "I've arrived" is attributed to the vendor and must NEVER be
     counted or rendered as "N drivers".
"""

import inspect
from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.modules.m13_vendor import public as m13
from app.modules.m13_vendor.domain import service as m13_service

DALLAS = (32.7767, -96.7970)
AHEAD = (32.95, -96.7970)  # due north of the origin
T0 = datetime(2026, 7, 25, 17, 0, tzinfo=UTC)
MENU = [m13.OfferingIn("Osh", 1200)]


def _account(db, email):
    return identity.register_account(db, email, "pw-123456")


def _facility(db, name="Loves 212", coords=DALLAS):
    return facility.create_facility(db, facility.FacilityType.truck_stop, name, *coords)


def _vendor(db, email, name, **kwargs):
    account = _account(db, email)
    defaults = {"languages": ["uz"], "halal_answered": True, "metro": "dallas-tx"}
    return m13.register_vendor(
        db, account.id, name, m13.VendorType.food_mobile, **{**defaults, **kwargs}
    )


def _publish(db, vendor, fac, start=T0, hours=4, **kwargs):
    return m13.publish_appearance(
        db, vendor, fac.id, start, start + timedelta(hours=hours), MENU, now=start, **kwargs
    )[0]


def _confirm(db, vendor, fac, email, present=True, now=T0, coords=DALLAS):
    driver = _account(db, email)
    location.arm_geofence(db, driver.id, fac.id)
    location.evaluate_ping(db, driver.id, *coords, occurred_at=now)
    m13.confirm_presence(db, driver.id, vendor.id, fac.id, present, now=now)
    return driver


# --- Q-3: deterministic, incorruptible ranking ---
def test_live_and_confirmed_outranks_merely_live(db):
    fac = _facility(db)
    confirmed = _vendor(db, "a@x.com", "Alpha Kitchen")
    unconfirmed = _vendor(db, "b@x.com", "Beta Kitchen", metro="austin-tx")
    _publish(db, confirmed, fac)
    _publish(db, unconfirmed, fac)
    during = T0 + timedelta(hours=1)
    _confirm(db, confirmed, fac, "driver@x.com", now=during)

    order = m13.vendors_at_facility(db, fac.id, now=during, limit=0)
    assert [e.vendor.name for e in order] == ["Alpha Kitchen", "Beta Kitchen"]
    assert order[0].bucket == m13.BUCKET_LIVE_CONFIRMED
    assert order[1].bucket == m13.BUCKET_LIVE


def test_live_outranks_upcoming_today_outranks_this_week(db):
    fac = _facility(db)
    live = _vendor(db, "l@x.com", "Live Cook")
    today = _vendor(db, "t@x.com", "Later Today", metro="austin-tx")
    week = _vendor(db, "w@x.com", "Next Week", metro="houston-tx")
    _publish(db, live, fac, start=T0)
    _publish(db, today, fac, start=T0 + timedelta(hours=3))
    _publish(db, week, fac, start=T0 + timedelta(days=3))

    order = m13.vendors_at_facility(db, fac.id, now=T0 + timedelta(minutes=30), limit=0)
    assert [e.vendor.name for e in order] == ["Live Cook", "Later Today", "Next Week"]


def test_verification_tier_breaks_a_tie(db):
    fac = _facility(db)
    verified = _vendor(db, "v@x.com", "Verified Cook")
    plain = _vendor(db, "p@x.com", "Plain Cook", metro="austin-tx")
    m13.set_verification(db, verified, m13.VendorVerifyStatus.verified)
    _publish(db, plain, fac)
    _publish(db, verified, fac)

    order = m13.vendors_at_facility(db, fac.id, now=T0 + timedelta(minutes=1), limit=0)
    assert order[0].vendor.name == "Verified Cook"


def test_property_approval_breaks_a_tie_below_verification(db):
    fac = _facility(db)
    approved = _vendor(db, "ap@x.com", "Approved Cook")
    other = _vendor(db, "un@x.com", "Unapproved Cook", metro="austin-tx")
    _publish(db, other, fac, property_approved=False)
    _publish(db, approved, fac, property_approved=True)

    order = m13.vendors_at_facility(db, fac.id, now=T0 + timedelta(minutes=1), limit=0)
    assert order[0].vendor.name == "Approved Cook"


def test_reliability_breaks_a_tie_below_property_approval(db):
    fac = _facility(db)
    reliable = _vendor(db, "r@x.com", "Reliable Cook")
    flaky = _vendor(db, "f@x.com", "Flaky Cook", metro="austin-tx")
    # give each a closed history: one showed up, the other didn't
    past = T0 - timedelta(days=2)
    _publish(db, reliable, fac, start=past)
    _confirm(db, reliable, fac, "hist@x.com", now=past + timedelta(hours=1))
    _publish(db, flaky, fac, start=past)
    m13.sweep_appearances(db, now=past + timedelta(hours=6))

    _publish(db, reliable, fac, start=T0)
    _publish(db, flaky, fac, start=T0)
    order = m13.vendors_at_facility(db, fac.id, now=T0 + timedelta(minutes=1), limit=0)

    assert order[0].vendor.name == "Reliable Cook"


def test_ranking_is_pure_and_repeatable(db):
    # same input, same order, every time — no clock, no randomness, no hidden state
    fac = _facility(db)
    first = _vendor(db, "1@x.com", "One")
    second = _vendor(db, "2@x.com", "Two", metro="austin-tx")
    _publish(db, first, fac)
    _publish(db, second, fac)

    runs = [
        [
            e.vendor.id
            for e in m13.vendors_at_facility(db, fac.id, now=T0 + timedelta(minutes=1), limit=0)
        ]
        for _ in range(3)
    ]
    assert runs[0] == runs[1] == runs[2]


def test_ranking_has_no_promotion_or_payment_input(db):
    # Q-3 is constitutional: pay-to-rank in discovery does not exist, and the way to
    # keep it that way is for the ordering function to have no such term to reach for
    source = inspect.getsource(m13_service.rank_entries)
    for forbidden in ("promo", "promotion", "sponsor", "paid", "bid", "boost", "price"):
        assert forbidden not in source.lower()


# --- Q-6: driver-side noise budget ---
def test_a_facility_card_shows_at_most_two_vendors(db):
    fac = _facility(db)
    for i in range(4):
        vendor = _vendor(db, f"n{i}@x.com", f"Cook {i}", metro=f"metro-{i}")
        _publish(db, vendor, fac)

    assert len(m13.vendors_at_facility(db, fac.id, now=T0 + timedelta(minutes=1))) == 2
    # the rest stay reachable behind "all vendors" in the sheet
    assert len(m13.vendors_at_facility(db, fac.id, now=T0 + timedelta(minutes=1), limit=0)) == 4


def test_the_corridor_shows_at_most_three_vendors(db):
    driver = _account(db, "corridor@x.com")
    for i in range(5):
        fac = _facility(db, f"Stop {i}", coords=(AHEAD[0] + i * 0.01, AHEAD[1]))
        vendor = _vendor(db, f"c{i}@x.com", f"Corridor Cook {i}", metro=f"m{i}")
        _publish(db, vendor, fac)

    ahead = m13.corridor_vendors(
        db, driver.id, *DALLAS, heading_deg=0, now=T0 + timedelta(minutes=1)
    )
    assert len(ahead) == m13.MAX_CORRIDOR_VENDORS


def test_the_corridor_only_looks_ahead(db):
    driver = _account(db, "behind@x.com")
    behind = _facility(db, "Behind", coords=(32.60, -96.7970))  # south of the origin
    vendor = _vendor(db, "bh@x.com", "Behind Cook")
    _publish(db, vendor, behind)

    ahead = m13.corridor_vendors(
        db, driver.id, *DALLAS, heading_deg=0, now=T0 + timedelta(minutes=1)
    )
    assert ahead == []


# --- Q-7: clean empty states ---
def test_a_facility_with_no_vendors_returns_nothing_to_render(db):
    fac = _facility(db)
    assert m13.vendors_at_facility(db, fac.id, now=T0) == []


def test_a_cancelled_appearance_disappears_immediately(db):
    fac = _facility(db)
    vendor = _vendor(db, "x@x.com", "Cancelled Cook")
    appearance = _publish(db, vendor, fac)
    m13.cancel_appearance(db, appearance, now=T0)

    assert m13.vendors_at_facility(db, fac.id, now=T0 + timedelta(minutes=1)) == []


def test_an_empty_viewport_returns_an_empty_list(db):
    assert m13.appearances_in_bbox(db, 40.0, -100.0, 41.0, -99.0, now=T0) == []


# --- FR3: the bbox feed behind the map badge ---
def test_the_bbox_feed_returns_vendors_in_view(db):
    fac = _facility(db)
    vendor = _vendor(db, "bb@x.com", "Bbox Cook")
    _publish(db, vendor, fac)

    found = m13.appearances_in_bbox(db, 32.0, -97.5, 33.5, -96.0, now=T0 + timedelta(minutes=1))
    assert [e.vendor.name for e in found] == ["Bbox Cook"]


# --- FR4: confirmation honesty (§11.7) ---
def test_a_driver_confirmation_is_a_crowd_reading(db):
    fac = _facility(db)
    vendor = _vendor(db, "cr@x.com", "Crowd Cook")
    _publish(db, vendor, fac)
    _confirm(db, vendor, fac, "d1@x.com", now=T0 + timedelta(minutes=10))

    belief = m13.presence(db, vendor.id, fac.id)
    assert belief.present is True
    assert belief.source == "crowd"
    assert belief.sample_size == 1


def test_a_vendors_own_arrival_is_attributed_to_the_vendor_not_to_drivers(db):
    # THE §11.7 line: the vendor saying "I'm here" is a real, timestamped, sourced
    # claim — but it is not a driver, and the UI must never print "1 driver" for it
    fac = _facility(db)
    vendor = _vendor(db, "self@x.com", "Self Cook")
    _publish(db, vendor, fac)

    m13.vendor_self_report(db, vendor, fac.id, arrived=True, now=T0 + timedelta(minutes=5))

    belief = m13.presence(db, vendor.id, fac.id)
    assert belief.present is True
    assert belief.source == "vendor"  # the UI renders "vendor says", never a count


def test_a_vendor_cannot_confirm_its_own_show_up_rate(db):
    # accountability is a CROWD measure: self-reporting must not inflate reliability,
    # or the show-up rate would be worth nothing
    fac = _facility(db)
    vendor = _vendor(db, "cheat@x.com", "Cheating Cook")
    _publish(db, vendor, fac)
    m13.vendor_self_report(db, vendor, fac.id, arrived=True, now=T0 + timedelta(minutes=5))

    m13.sweep_appearances(db, now=T0 + timedelta(hours=6))

    score = m13.reliability(db, vendor.id)
    assert (score.confirmed, score.published) == (0, 1)


def test_sold_out_is_visible_on_the_entry(db):
    fac = _facility(db)
    vendor = _vendor(db, "so@x.com", "Sold Out Cook")
    _publish(db, vendor, fac)
    driver = _account(db, "hungry@x.com")
    location.arm_geofence(db, driver.id, fac.id)
    location.evaluate_ping(db, driver.id, *DALLAS, occurred_at=T0)
    m13.report_sold_out(db, driver.id, vendor.id, fac.id, now=T0 + timedelta(minutes=20))

    entries = m13.vendors_at_facility(db, fac.id, now=T0 + timedelta(minutes=30))
    assert entries[0].sold_out is True


def test_vendor_detail_carries_the_sheet_payload(db):
    fac = _facility(db)
    vendor = _vendor(db, "sheet@x.com", "Sheet Cook", halal_disclosure="Halal butcher, Dallas")
    _publish(db, vendor, fac)

    detail = m13.vendor_detail(db, vendor.id, now=T0 + timedelta(minutes=1))

    assert detail["vendor"].halal_disclosure == "Halal butcher, Dallas"
    assert len(detail["appearances"]) == 1
    assert detail["reliability"].published == 0
    assert detail["in_discovery"] is True


def test_a_merged_vendor_resolves_to_its_canonical_sheet(db):
    canonical = _vendor(db, "can@x.com", "Canonical Cook")
    dupe = _vendor(db, "dup@x.com", "Dupe Cook", metro="tulsa-ok")
    m13.merge_vendors(db, canonical, dupe)

    assert m13.vendor_detail(db, dupe.id, now=T0)["vendor"].id == canonical.id

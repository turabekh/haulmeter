"""AI-CONTEXT: Full-platform synthetic end-to-end — the whole product as one
driver's day, exercising M1–M12 through their public interfaces only. If this
stays green, the twelve modules integrate as a single product, not just as
parts: the map surfaces intel, a spot is booked, fuel is bought at a net price,
a detention clock is armed → accrued → filed → recovered, a settlement is
audited, decisions are computed, points are earned and a spot is handed off,
voice routes over the driver's own data, and a fleet rolls it all up — with the
North Star (Driver Dollars Delivered) reflecting the journey end to end.
"""

from datetime import UTC, date, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f05_load import public as loads
from app.foundation.f07_ledger import public as ledger
from app.foundation.f09_ai_gateway import public as ai
from app.modules.m01_map import public as m1
from app.modules.m02_facility_intel import public as m2
from app.modules.m03_detention import public as m3
from app.modules.m04_accessorial import public as m4
from app.modules.m05_protection import public as m5
from app.modules.m06_parking import public as m6
from app.modules.m07_fuel import public as m7
from app.modules.m08_intelligence import public as m8
from app.modules.m09_money import public as m9
from app.modules.m10_community import public as m10
from app.modules.m11_voice import public as m11
from app.modules.m12_fleet import public as m12
from app.modules.m13_vendor import public as m13

RECEIVER = (32.7767, -96.7970)
TRUCKSTOP = (32.80, -96.7970)
FUEL = (32.82, -96.7970)
AWAY = (32.90, -96.8000)
T0 = datetime(2026, 7, 21, 8, 0, tzinfo=UTC)
MONTH = date(2026, 7, 1)


def test_full_platform_synthetic_end_to_end(db):
    # every module registers together (F13 flags + F14 admin views + F9 prompts)
    for mod in (m1, m2, m3, m4, m5, m6, m7, m8, m9, m10, m11, m12, m13):
        mod.register_module(db)

    # --- F1/F2: an owner-operator (can invoice) + the day's facilities ---
    driver = identity.register_account(db, "owneroperator@example.com", "pw-123456")
    identity.attach_role(db, driver, identity.Role.driver)
    identity.upsert_driver_profile(
        db, driver, authority_type=identity.AuthorityType.own_mc, home_timezone="America/Chicago"
    )
    receiver = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "Dallas Receiver", *RECEIVER
    )
    truckstop = facility.create_facility(
        db, facility.FacilityType.truck_stop, "Loves #212", *TRUCKSTOP
    )
    fuel_station = facility.create_facility(
        db, facility.FacilityType.fuel_station, "TA Center", *FUEL
    )

    # --- M1: the daily-open map shows facilities around the driver ---
    pins = m1.map_overlay(db, driver.id, *RECEIVER, 20000, preset=m1.Preset.drive)
    assert any(p.facility_id == truckstop.id for p in pins)

    # --- M6: book a private parking spot; the F7 ledger stays balanced ---
    owner = identity.register_account(db, "lotowner@example.com", "pw-123456")
    prop = m6.create_property(db, owner.id, "Yardline", 32.83, -96.7970, vetted=True)
    spot = m6.add_spot(db, prop, "A1", price_cents_per_night=2400)
    booking = m6.book(db, spot, driver.id, T0, T0 + timedelta(days=1))
    assert booking.price_cents == 2400
    assert booking.take_cents + booking.owner_payout_cents == booking.price_cents

    # --- M7: fuel network net price -> pump code -> settle; the driver saves ---
    merchant = m7.register_merchant(db, "FuelCo")
    m7.set_station_pricing(
        db,
        fuel_station.id,
        419,
        discount_cents_per_gal=25,
        spread_cents_per_gal=4,
        merchant_id=merchant.id,
    )
    corridor = m7.corridor_fuel(
        db, driver.id, *RECEIVER, heading_deg=0, max_distance_m=40000, gallons=100
    )
    assert corridor and corridor[0].net_cents_per_gal == 394
    m7.settle(db, m7.issue_pump_code(db, driver.id, fuel_station.id, gallons=100))
    fuel_saved = m7.driver_analytics(db, driver.id).savings_cents
    assert fuel_saved == 2500  # 25c/gal * 100 gal

    # --- Load loop (F5/F3/M3): arrive -> accrue -> file -> recover ---
    load = loads.create_load(
        db, driver.id, detention_rate_cents_per_hour=7500, free_time_minutes=120
    )
    stop = loads.add_stop(
        db,
        load,
        receiver.id,
        loads.StopType.delivery,
        free_time_minutes=120,
        detention_rate_cents_per_hour=7500,
    )
    loads.arm_stop(db, stop)
    location.evaluate_ping(db, driver.id, *RECEIVER, occurred_at=T0)  # ENTER = arrival
    location.evaluate_ping(
        db, driver.id, *AWAY, occurred_at=T0 + timedelta(hours=3)
    )  # EXIT = departure
    location.disarm_geofence(db, driver.id, receiver.id, occurred_at=T0 + timedelta(hours=3))
    claim = m3.start_claim(db, stop)
    m3.generate_pack(db, claim, now=T0 + timedelta(hours=4))
    assert claim.amount_cents == 7500  # 3h dwell - 2h free = 1h detention @ $75
    assert claim.receivable_ref is not None
    detention_receivable = next(
        r for r in ledger.list_receivables(db, driver.id) if r.id == claim.receivable_ref
    )
    ledger.transition_receivable(
        db, detention_receivable, ledger.ReceivableState.recovered
    )  # collected

    # --- M2/M8: the receiver's dwell history feeds decisions ---
    dwell = m2.dwell_stats(db, receiver.id)
    assert dwell.overall["sample_size"] == 1
    risk = m8.detention_risk_flag(db, receiver.id, free_time_minutes=120)
    assert risk.exceed_rate == 1.0  # our one tracked stop ran past free time
    profit = m8.true_profit(
        db,
        driver.id,
        revenue_cents=200000,
        loaded_miles=500,
        mpg=6.0,
        tolls_cents=3000,
        receiver_facility_id=receiver.id,
        free_time_minutes=120,
        rate_cents_per_hour=7500,
        origin_lat=RECEIVER[0],
        origin_lon=RECEIVER[1],
        heading_deg=0,
        max_distance_m=40000,
    )
    assert profit.fuel_net_cents_per_gal == 394
    assert profit.expected_detention_cents == 7500
    plan = m8.where_to_sleep(db, driver.id, *RECEIVER, heading_deg=0, hos_minutes_remaining=120)
    assert plan.stops  # a place to sleep within HOS range

    # --- M9: an owed layover the carrier settlement missed -> flagged; then DDD ---
    ledger.create_receivable(db, driver.id, ledger.ReceivableKind.layover, 20000)  # owed
    settlement = m9.upload_settlement(
        db,
        driver.id,
        "Acme Carrier",
        MONTH,
        date(2026, 7, 20),
        lines=[{"kind": "layover", "amount_cents": 0}],
    )
    discrepancies = m9.audit_settlement(db, settlement)
    assert any(d.kind == "layover" and d.missed_cents == 20000 for d in discrepancies)
    ddd = m9.earnings_dashboard(db, driver.id)
    assert ddd.recovered_cents == 7500  # the collected detention
    assert ddd.fuel_saved_cents == 2500
    assert ddd.flagged_cents == 20000  # the missed layover
    assert ddd.ddd_cents == 7500 + 2500 + 20000  # North Star reflects the whole day

    # --- M10: earn points, hand off a spot, answer a question ---
    m10.award_contribution(db, driver.id, "review", T0)
    location.arm_geofence(db, driver.id, truckstop.id)
    location.evaluate_ping(db, driver.id, *TRUCKSTOP, occurred_at=T0 + timedelta(hours=5))
    handoff = m10.broadcast_handoff(
        db, driver.id, truckstop.id, T0 + timedelta(hours=5, minutes=15), T0 + timedelta(hours=5)
    )
    taker = identity.register_account(db, "taker@example.com", "pw-123456")
    m10.claim_handoff(db, handoff, taker.id, T0 + timedelta(hours=5))
    location.arm_geofence(db, taker.id, truckstop.id)
    location.evaluate_ping(
        db, taker.id, *TRUCKSTOP, occurred_at=T0 + timedelta(hours=5, minutes=10)
    )
    m10.confirm_handoff(db, handoff, T0 + timedelta(hours=5, minutes=10))
    assert handoff.state == m10.HandoffState.confirmed
    assert m10.points_balance(db, taker.id) == 10  # the claimer earned on arrival

    # --- M11: voice routes over the driver's OWN data; ghostwriter drafts English ---
    resp = m11.route(db, driver.id, "what am I owed")
    assert resp.intent == "money_owed"
    draft = m11.draft_counterparty_message(
        db, ai.FakeModelProvider(), driver.id, "detention notice", "1h past free time", tone="firm"
    )
    assert "ENGLISH" in draft

    # --- M12: a fleet rolls up the consented driver's recovered dollars ---
    fleet, _ = m12.create_fleet(db, owner.id, "Acme Fleet", now=T0)
    m12.accept_invite(db, m12.invite_driver(db, fleet.id, driver.id), now=T0)
    report = m12.fleet_report(db, fleet.id)
    assert report.driver_count == 2  # owner + the consented driver
    assert report.recovered_cents == 7500  # the driver's collected detention rolls up
    assert report.fuel_saved_cents == 2500
    m12.subscribe_data(db, "lane-analyst")
    bench = m12.dwell_benchmark(db, receiver.id, subscriber_ref="lane-analyst")
    assert bench is None  # one sample is below the privacy floor — suppressed, never leaked
    tms_load = m12.push_load(db, driver.id, external_ref="TMS-42", rate_cents=200000)
    assert tms_load.source == loads.LoadSource.tms_push

    # --- M13: a cook schedules -> the driver finds him on the corridor ahead ->
    # confirms he's there -> the show-up rate that makes the next detour
    # trustworthy actually moves. Discovery only: no money changes hands. ---
    cook_account = identity.register_account(db, "cook@example.com", "pw-123456")
    cook = m13.register_vendor(
        db,
        cook_account.id,
        "Osh Express",
        m13.VendorType.food_mobile,
        metro="dallas-tx",
        languages=["uz", "ru"],
        halal_disclosure="Halal butcher in Dallas",
        halal_answered=True,
    )
    dinner = T0 + timedelta(hours=6)
    appearance = m13.publish_appearance(
        db,
        cook,
        truckstop.id,
        dinner,
        dinner + timedelta(hours=4),
        [m13.OfferingIn("Osh", 1200, portions=40), m13.OfferingIn("Somsa", 400)],
        property_approved=True,
        now=dinner,
    )[0]

    # the truck stop is due north of the receiver, so a northbound driver sees it
    ahead = m13.corridor_vendors(db, driver.id, *RECEIVER, heading_deg=0, now=dinner)
    assert [e.vendor.id for e in ahead] == [cook.id]
    assert ahead[0].offerings[0].price_cents == 1200

    # the driver is already geofence-present at the truck stop from the M10 handoff
    location.evaluate_ping(db, driver.id, *TRUCKSTOP, occurred_at=dinner + timedelta(minutes=30))
    m13.confirm_presence(
        db, driver.id, cook.id, truckstop.id, True, now=dinner + timedelta(minutes=30)
    )
    belief = m13.presence(db, cook.id, truckstop.id)
    assert belief.present is True
    assert belief.source == "crowd"  # a driver said it, so it counts as drivers (§11.7)

    # confirmed-and-live now outranks everything else at that facility (Q-3)
    at_stop = m13.vendors_at_facility(db, truckstop.id, now=dinner + timedelta(hours=1))
    assert at_stop[0].bucket == m13.BUCKET_LIVE_CONFIRMED

    # the window closes and the crowd's confirmation becomes public reliability (Q-2)
    m13.sweep_appearances(db, now=dinner + timedelta(hours=5))
    assert appearance.status == m13.AppearanceStatus.done
    score = m13.reliability(db, cook.id)
    assert (score.confirmed, score.published) == (1, 1)
    assert cook.consecutive_no_shows == 0
    # and Q-1 holds: a finished dinner is off the map
    assert m13.vendors_at_facility(db, truckstop.id, now=dinner + timedelta(hours=5)) == []

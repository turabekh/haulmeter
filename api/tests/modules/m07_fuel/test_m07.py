from datetime import UTC, datetime

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f07_ledger import public as ledger
from app.foundation.f13_flags import public as flags
from app.modules.m07_fuel import public as m7

# Dallas origin; two fuel stations dead ahead (heading north) at increasing range.
ORIGIN = (32.7767, -96.7970)
NEAR = (32.80, -96.7970)
FAR = (32.86, -96.7970)
T0 = datetime(2026, 7, 20, 18, 0, tzinfo=UTC)


def _driver(db):
    return identity.register_account(db, "driver@example.com", "pw-123456")


def _station(db, name, lat, lon):
    return facility.create_facility(db, facility.FacilityType.fuel_station, name, lat, lon)


def test_flag_gated_on_merchant_and_payment(db):
    m7.register_module(db)
    assert flags.can_activate(db, "m07_fuel") is False


def test_net_price_is_gross_minus_driver_discount(db):
    station = _station(db, "Pilot", *NEAR)
    merchant = m7.register_merchant(db, "FuelCo")
    pricing = m7.set_station_pricing(
        db,
        station.id,
        gross_cents_per_gal=419,
        discount_cents_per_gal=25,
        spread_cents_per_gal=4,
        merchant_id=merchant.id,
    )
    assert m7.net_cents_per_gal(pricing) == 394  # 4.19 - 0.25 net


def test_corridor_ranks_by_net_price(db):
    driver = _driver(db)
    near = _station(db, "Nearer, dearer", *NEAR)
    far = _station(db, "Farther, cheaper", *FAR)
    merchant = m7.register_merchant(db, "FuelCo")
    # nearer station is more expensive net; farther one is cheapest net
    m7.set_station_pricing(
        db, near.id, 419, discount_cents_per_gal=10, spread_cents_per_gal=4, merchant_id=merchant.id
    )
    m7.set_station_pricing(
        db, far.id, 409, discount_cents_per_gal=20, spread_cents_per_gal=4, merchant_id=merchant.id
    )

    stops = m7.corridor_fuel(
        db, driver.id, *ORIGIN, heading_deg=0, max_distance_m=40000, gallons=100
    )
    assert [s.name for s in stops] == ["Farther, cheaper", "Nearer, dearer"]
    cheapest = stops[0]
    assert cheapest.net_cents_per_gal == 389  # 409 - 20
    assert cheapest.savings_cents_per_gal == 20
    assert cheapest.true_cost_cents == 38900  # 389c * 100 gal


def test_pump_code_only_for_network_stations(db):
    driver = _driver(db)
    station = _station(db, "Indie stop", *NEAR)
    m7.set_station_pricing(db, station.id, 429, source=m7.PriceSource.crowd)  # no merchant
    with pytest.raises(m7.NotAFuelPartner):
        m7.issue_pump_code(db, driver.id, station.id, gallons=100)


def test_purchase_settles_with_balanced_spread_entry(db):
    driver = _driver(db)
    station = _station(db, "Pilot", *NEAR)
    merchant = m7.register_merchant(db, "FuelCo")
    m7.set_station_pricing(
        db,
        station.id,
        419,
        discount_cents_per_gal=25,
        spread_cents_per_gal=4,
        merchant_id=merchant.id,
    )

    txn = m7.issue_pump_code(db, driver.id, station.id, gallons=100)
    assert txn.state == m7.FuelTxnState.code_issued
    assert len(txn.pump_code) == 8
    assert txn.net_cents == 39400  # 3.94 * 100
    assert txn.spread_cents == 400  # 0.04 * 100

    m7.settle(db, txn)
    assert txn.state == m7.FuelTxnState.settled
    assert txn.entry_ref is not None
    platform = ledger.get_or_create_account(
        db, ledger.LedgerAccountKind.platform_revenue, "revenue:fuel", ledger.Currency.usd
    )
    merchant_acct = ledger.get_or_create_account(
        db, ledger.LedgerAccountKind.fuel_clearing, f"merchant:{merchant.id}", ledger.Currency.usd
    )
    assert ledger.balance(db, platform) == -400  # spread retained
    assert ledger.balance(db, merchant_acct) == -39000  # net minus spread owed to merchant


def test_driver_savings_analytics(db):
    driver = _driver(db)
    station = _station(db, "Pilot", *NEAR)
    merchant = m7.register_merchant(db, "FuelCo")
    m7.set_station_pricing(
        db,
        station.id,
        419,
        discount_cents_per_gal=25,
        spread_cents_per_gal=4,
        merchant_id=merchant.id,
    )
    m7.settle(db, m7.issue_pump_code(db, driver.id, station.id, gallons=100))
    m7.settle(db, m7.issue_pump_code(db, driver.id, station.id, gallons=50))

    a = m7.driver_analytics(db, driver.id)
    assert a.txn_count == 2
    assert a.gallons_milli == 150000  # 150 gal
    assert a.savings_cents == round(25 * 150000 / 1000)  # 25c/gal * 150 gal = 3750
    assert a.spend_cents == round(394 * 150000 / 1000)


def test_crowd_confirmation_updates_non_network_price(db):
    driver = _driver(db)
    station = _station(db, "Indie stop", *NEAR)
    location.arm_geofence(db, driver.id, station.id)
    location.evaluate_ping(db, driver.id, *NEAR, occurred_at=T0)
    consensus = m7.confirm_price(
        db, driver.id, station.id, price_cents_per_gal=435, submitted_at=T0
    )
    assert consensus == 435

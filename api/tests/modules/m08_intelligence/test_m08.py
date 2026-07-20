from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f13_flags import public as flags
from app.modules.m06_parking import public as m6
from app.modules.m07_fuel import public as m7
from app.modules.m08_intelligence import public as m8

DALLAS = (32.7767, -96.7970)
FAR = (32.9000, -96.8000)
AHEAD = (32.82, -96.7970)
# 06:00 arrivals so by-hour buckets on hour 6
T6 = datetime(2026, 7, 20, 6, 0, tzinfo=UTC)


def _account(db, email="driver@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _dwell(db, account, fac, enter, exit_at):
    location.arm_geofence(db, account.id, fac.id)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=enter)
    location.evaluate_ping(db, account.id, *FAR, occurred_at=exit_at)
    location.disarm_geofence(db, account.id, fac.id, occurred_at=exit_at)


def _receiver(db):
    return facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "Dallas Receiver", *DALLAS
    )


def test_flag_registers(db):
    m8.register_module(db)
    assert flags.can_activate(db, "m08_intelligence") is True  # no external gates


def test_expected_detention_cost_averages_stop_history(db):
    fac = _receiver(db)
    a, b = _account(db, "a@x.com"), _account(db, "b@x.com")
    # 120 min free time, $75/h. a: 1h dwell (no detention); b: 3h dwell (1h over -> $75)
    _dwell(db, a, fac, T6, T6 + timedelta(hours=1))
    _dwell(db, b, fac, T6, T6 + timedelta(hours=3))
    cost, n = m8.expected_detention_cost(
        db, fac.id, free_time_minutes=120, rate_cents_per_hour=7500
    )
    assert n == 2
    assert cost == round((0 + 7500) / 2)  # avg of $0 and $75 = $37.50


def test_true_profit_nets_fuel_and_expected_detention(db):
    driver = _account(db)
    fac = _receiver(db)
    _dwell(db, driver, fac, T6, T6 + timedelta(hours=3))  # 1h over free time
    # a network fuel station on the corridor ahead
    station = facility.create_facility(db, facility.FacilityType.fuel_station, "Pilot", *AHEAD)
    merchant = m7.register_merchant(db, "FuelCo")
    m7.set_station_pricing(
        db,
        station.id,
        419,
        discount_cents_per_gal=25,
        spread_cents_per_gal=4,
        merchant_id=merchant.id,
    )

    result = m8.true_profit(
        db,
        driver.id,
        revenue_cents=200000,
        loaded_miles=500,
        mpg=6.0,
        tolls_cents=3000,
        receiver_facility_id=fac.id,
        free_time_minutes=120,
        rate_cents_per_hour=7500,
        origin_lat=DALLAS[0],
        origin_lon=DALLAS[1],
        heading_deg=0,
        max_distance_m=40000,
    )
    # fuel: 500/6 = 83.333 gal * 394c net = round(394*83333/1000) via corridor true cost
    assert result.fuel_net_cents_per_gal == 394
    assert result.expected_detention_cents == 7500  # one stop, 1h over
    assert result.net_cents == 200000 - result.fuel_cost_cents - 3000 - 7500
    assert result.rpm_after_cents == round(result.net_cents / 500)
    assert result.basis["detention_sample_size"] == 1


def test_appointment_hours_ranked_fastest_first(db):
    fac = _receiver(db)
    a, b = _account(db, "a@x.com"), _account(db, "b@x.com")
    # 06:00 quick (40m), 14:00 slow (3.5h)
    t14 = datetime(2026, 7, 20, 14, 0, tzinfo=UTC)
    _dwell(db, a, fac, T6, T6 + timedelta(minutes=40))
    _dwell(db, b, fac, t14, t14 + timedelta(hours=3, minutes=30))
    recs = m8.appointment_hours(db, fac.id)
    assert recs[0].hour == 6  # fastest-unloading hour leads
    assert recs[0].median_seconds == 40 * 60
    assert recs[0].confidence == "low"  # single sample


def test_detention_risk_flag_exceed_rate(db):
    fac = _receiver(db)
    a, b, c = _account(db, "a@x.com"), _account(db, "b@x.com"), _account(db, "c@x.com")
    _dwell(db, a, fac, T6, T6 + timedelta(hours=1))  # within free time
    _dwell(db, b, fac, T6, T6 + timedelta(hours=3))  # over
    _dwell(db, c, fac, T6, T6 + timedelta(hours=4))  # over
    flag = m8.detention_risk_flag(db, fac.id, free_time_minutes=120)
    assert flag.sample_size == 3
    assert abs(flag.exceed_rate - 2 / 3) < 1e-9
    assert flag.basis == "tracked_stops"


def test_detention_risk_flag_no_data(db):
    fac = _receiver(db)
    flag = m8.detention_risk_flag(db, fac.id, free_time_minutes=120)
    assert flag.exceed_rate is None
    assert flag.basis == "no_data"


def test_where_to_sleep_ranks_bookable_first_within_range(db):
    driver = _account(db)
    # a public truck stop and a bookable private lot ahead, both within HOS range
    facility.create_facility(db, facility.FacilityType.truck_stop, "Loves", *AHEAD)
    owner = _account(db, "owner@x.com")
    prop = m6.create_property(db, owner.id, "Yardline", 32.83, -96.7970, vetted=True)
    m6.add_spot(db, prop, "A1", price_cents_per_night=2400)

    plan = m8.where_to_sleep(
        db, driver.id, *DALLAS, heading_deg=0, hos_minutes_remaining=120, avg_speed_mph=55
    )
    assert plan.range_m > 0
    assert plan.stops  # candidates found within range
    assert plan.stops[0].guaranteed_bookable is True  # a guaranteed spot leads
    assert plan.guaranteed is not None  # cheapest bookable surfaced
    assert plan.guaranteed.price_cents_per_night == 2400

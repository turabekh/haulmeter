from datetime import UTC, date, datetime

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f05_load import public as loads
from app.foundation.f07_ledger import public as ledger
from app.foundation.f13_flags import public as flags
from app.modules.m12_fleet import public as m12

T0 = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
MONTH = date(2026, 7, 1)
DALLAS = (32.7767, -96.7970)
FAR = (32.9000, -96.8000)


def _acct(db, email):
    return identity.register_account(db, email, "pw-123456")


def test_flag_registers(db):
    m12.register_module(db)
    assert flags.can_activate(db, "m12_fleet") is True


def test_membership_is_consent_gated(db):
    owner = _acct(db, "owner@x.com")
    driver = _acct(db, "driver@x.com")
    fleet, _ = m12.create_fleet(db, owner.id, "Acme Fleet", now=T0)

    membership = m12.invite_driver(db, fleet.id, driver.id)
    # invited but not consented -> not in any fleet view yet (M12-FR1)
    assert driver.id not in [m.driver_account_id for m in m12.list_members(db, fleet.id)]

    m12.accept_invite(db, membership, now=T0)
    members = m12.list_members(db, fleet.id)
    ids = [m.driver_account_id for m in members]
    assert driver.id in ids and owner.id in ids  # both consented now


def test_fleet_report_rolls_up_consented_members_only(db):
    owner = _acct(db, "owner@x.com")
    a = _acct(db, "a@x.com")
    b = _acct(db, "b@x.com")
    fleet, _ = m12.create_fleet(db, owner.id, "Acme", now=T0)
    m12.accept_invite(db, m12.invite_driver(db, fleet.id, a.id), now=T0)
    # b is invited but NOT consented -> excluded from the rollup
    m12.invite_driver(db, fleet.id, b.id)

    rec = ledger.create_receivable(db, a.id, ledger.ReceivableKind.detention, 15000)
    ledger.transition_receivable(db, rec, ledger.ReceivableState.recovered)
    ledger.create_receivable(db, b.id, ledger.ReceivableKind.tonu, 99999)  # must NOT count

    report = m12.fleet_report(db, fleet.id)
    assert report.driver_count == 2  # owner + a (consented); b excluded
    assert report.recovered_cents == 15000
    assert all(m.driver_account_id != b.id for m in report.members)


def test_fleet_claims_desk_counterparty_analytics(db):
    owner = _acct(db, "owner@x.com")
    driver = _acct(db, "driver@x.com")
    fleet, _ = m12.create_fleet(db, owner.id, "Acme", now=T0)
    m12.accept_invite(db, m12.invite_driver(db, fleet.id, driver.id), now=T0)

    # counterparty_ref points at an F5 counterparty (as the real M3 flow sets it)
    broker = loads.create_counterparty(db, "Broker A", loads.CounterpartyKind.broker)
    r1 = ledger.create_receivable(
        db, driver.id, ledger.ReceivableKind.detention, 10000, counterparty_ref=broker.id
    )
    ledger.transition_receivable(db, r1, ledger.ReceivableState.recovered)
    ledger.create_receivable(
        db, driver.id, ledger.ReceivableKind.detention, 5000, counterparty_ref=broker.id
    )

    desk = m12.fleet_claims_desk(db, fleet.id)
    assert desk["recovered_cents"] == 10000
    assert desk["owed_cents"] == 5000
    cp = desk["by_counterparty"][str(broker.id)]
    assert cp["name"] == "Broker A"  # the desk resolves the UUID to the broker name
    assert cp["total"] == 15000
    assert cp["recovery_rate"] == round(10000 / 15000, 3)  # this broker pays 2/3


def test_parking_benefit_allowance(db):
    owner = _acct(db, "owner@x.com")
    driver = _acct(db, "driver@x.com")
    fleet, _ = m12.create_fleet(db, owner.id, "Acme", now=T0)
    m12.set_parking_benefit(db, fleet.id, monthly_allowance_cents=10000)
    assert m12.benefit_remaining(db, fleet.id, driver.id, MONTH) == 10000
    m12.record_benefit_usage(db, fleet.id, driver.id, MONTH, 2400)
    assert m12.benefit_remaining(db, fleet.id, driver.id, MONTH) == 7600


def test_data_product_requires_subscription_and_min_sample(db):
    fac = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Receiver", *DALLAS)
    with pytest.raises(m12.NotSubscribed):
        m12.dwell_benchmark(db, fac.id, subscriber_ref="analyst-1")

    m12.subscribe_data(db, "analyst-1")
    # below the minimum sample -> suppressed (never expose a small sample)
    assert m12.dwell_benchmark(db, fac.id, subscriber_ref="analyst-1") is None

    # >= MIN_BENCHMARK_SAMPLE tracked stops -> an aggregate benchmark is published
    for i in range(m12.MIN_BENCHMARK_SAMPLE):
        driver = _acct(db, f"d{i}@x.com")
        location.arm_geofence(db, driver.id, fac.id)
        location.evaluate_ping(db, driver.id, *DALLAS, occurred_at=T0)
        location.evaluate_ping(db, driver.id, *FAR, occurred_at=T0.replace(hour=14))
        location.disarm_geofence(db, driver.id, fac.id, occurred_at=T0.replace(hour=14))
    bench = m12.dwell_benchmark(db, fac.id, subscriber_ref="analyst-1")
    assert bench is not None
    assert bench.sample_size == m12.MIN_BENCHMARK_SAMPLE
    assert bench.basis == "aggregate"  # never per-driver


def test_tms_push_load_and_claim_status(db):
    driver = _acct(db, "driver@x.com")
    load = m12.push_load(
        db, driver.id, external_ref="TMS-778", rate_cents=200000, free_time_minutes=120
    )
    assert load.reference_number == "TMS-778"
    assert load.source == loads.LoadSource.tms_push

    ledger.create_receivable(db, driver.id, ledger.ReceivableKind.detention, 15000)
    status = m12.claim_status(db, driver.id)
    assert status[0]["kind"] == "detention"
    assert status[0]["state"] == "invoiced"

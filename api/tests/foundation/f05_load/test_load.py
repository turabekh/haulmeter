from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f04_evidence import public as evidence
from app.foundation.f05_load import public as loads

DALLAS = (32.7767, -96.7970)
T0 = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _account(db, email="oo@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _facility(db, name="Receiver Dock", coords=DALLAS):
    return facility.create_facility(db, facility.FacilityType.shipper_receiver, name, *coords)


def test_create_counterparty_and_payment_behavior(db):
    cp = loads.create_counterparty(
        db, "Acme Brokerage", loads.CounterpartyKind.broker, mc_number="MC123456"
    )
    loads.record_payment_observation(db, cp, 30)
    loads.record_payment_observation(db, cp, 40)
    assert cp.payment_behavior["avg_days_to_pay"] == 35
    loads.record_claim(db, cp)
    assert cp.claim_count == 1


def test_create_load_manual_with_terms(db):
    account = _account(db)
    cp = loads.create_counterparty(db, "Broker A", loads.CounterpartyKind.broker)
    load = loads.create_load(
        db,
        account.id,
        counterparty_id=cp.id,
        reference_number="L-1001",
        rate_cents=250000,
        detention_rate_cents_per_hour=7500,
        free_time_minutes=120,
    )
    assert load.source == loads.LoadSource.manual
    assert load.status == loads.LoadStatus.draft
    assert load.counterparty_id == cp.id


def test_create_load_from_parsed_terms_seam(db):
    account = _account(db)
    parsed = {
        "reference_number": "RC-77",
        "rate_cents": 300000,
        "detention_rate_cents_per_hour": 6000,
        "free_time_minutes": 120,
        "accessorial_terms": {"tonu": "50% of linehaul"},
    }
    load = loads.create_load_from_parsed_terms(db, account.id, parsed)
    assert load.source == loads.LoadSource.rate_con_parse
    assert load.accessorial_terms["tonu"] == "50% of linehaul"
    assert load.free_time_minutes == 120


def test_add_stops_ordered_and_facility_validated(db):
    account = _account(db)
    load = loads.create_load(db, account.id)
    pickup = _facility(db, "Shipper")
    delivery = _facility(db, "Receiver", coords=(32.9, -96.8))
    s0 = loads.add_stop(db, load, pickup.id, loads.StopType.pickup)
    s1 = loads.add_stop(db, load, delivery.id, loads.StopType.delivery)
    assert [s.sequence for s in loads.list_stops(db, load)] == [0, 1]
    assert s0.stop_type == loads.StopType.pickup
    assert s1.stop_type == loads.StopType.delivery


def test_add_stop_unknown_facility_raises(db):
    import uuid

    account = _account(db)
    load = loads.create_load(db, account.id)
    with pytest.raises(loads.FacilityNotFound):
        loads.add_stop(db, load, uuid.uuid4(), loads.StopType.delivery)


def test_effective_terms_stop_override_beats_load(db):
    account = _account(db)
    load = loads.create_load(
        db, account.id, detention_rate_cents_per_hour=7500, free_time_minutes=120
    )
    fac = _facility(db)
    stop = loads.add_stop(
        db, load, fac.id, loads.StopType.delivery, free_time_minutes=60
    )
    free_time, rate = loads.effective_detention_terms(db, stop)
    assert free_time == 60
    assert rate == 7500


def test_arm_stop_wires_geofence_and_evidence_log(db):
    account = _account(db)
    load = loads.create_load(db, account.id)
    fac = _facility(db)
    stop = loads.add_stop(
        db, load, fac.id, loads.StopType.delivery, appointment_start=T0
    )

    loads.arm_stop(db, stop)
    assert stop.geofence_armed is True
    assert stop.status == loads.StopStatus.armed
    assert stop.evidence_log_id is not None

    log = db.get(evidence.EvidenceLog, stop.evidence_log_id)
    assert log is not None
    assert log.stop_ref == stop.id

    events = location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0)
    assert [e.event_type for e in events] == [location.GeofenceEventType.ENTER]


def test_disarm_stop_stops_evaluation(db):
    account = _account(db)
    load = loads.create_load(db, account.id)
    fac = _facility(db)
    stop = loads.add_stop(db, load, fac.id, loads.StopType.delivery)
    loads.arm_stop(db, stop)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0)

    loads.disarm_stop(db, stop, occurred_at=T0 + timedelta(minutes=5))
    assert stop.geofence_armed is False
    after = location.evaluate_ping(
        db, account.id, *DALLAS, occurred_at=T0 + timedelta(minutes=30)
    )
    assert after == []


def test_load_status_transitions(db):
    account = _account(db)
    load = loads.create_load(db, account.id)
    loads.set_load_status(db, load, loads.LoadStatus.active)
    assert load.status == loads.LoadStatus.active
    loads.set_load_status(db, load, loads.LoadStatus.completed)
    assert load.status == loads.LoadStatus.completed
